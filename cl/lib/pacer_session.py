import pickle
import random
from typing import Union
from urllib.parse import urlparse

from django.conf import settings
from juriscraper.pacer import PacerSession
from redis import Redis
from requests.cookies import RequestsCookieJar

from cl.lib.redis_utils import get_redis_interface

session_key = "session:pacer:cookies:user.%s"


class ProxyPacerSession(PacerSession):
    """
    This class overrides the _prepare_login_request and post methods of the
    PacerSession class to achieve the following:

    - Sets the 'X-WhSentry-TLS' header to 'true' for all requests.
    - Replaces 'https://' with 'http://' in the URL before making the request.
    - Uses a proxy server for all requests.

    If the post method is called with a 'headers' argument, it merges the
    provided headers with the 'X-WhSentry-TLS' header set to 'true'. If no headers
    argument is provided, it adds a new dictionary with the 'X-WhSentry-TLS' header
    set to 'true' as the 'headers' argument.
    """

    def __init__(
        self,
        cookies=None,
        username=None,
        password=None,
        client_code=None,
        proxy=None,
    ):
        super().__init__(cookies, username, password, client_code)
        self.proxy_address = proxy if proxy else self._pick_proxy_connection()
        self.proxies = {
            "http": self.proxy_address,
        }
        self.headers["X-WhSentry-TLS"] = "true"

    def _pick_proxy_connection(self) -> str:
        """
        Picks a proxy connection string from available options.

        this function randomly chooses a string from the
        `settings.EGRESS_PROXY_HOSTS` list and returns it.

        Returns:
            str: The chosen proxy connection string.
        """
        return random.choice(settings.EGRESS_PROXY_HOSTS)

    def _change_protocol(self, url: str) -> str:
        """Converts a URL from HTTPS to HTTP protocol.

        By default, HTTP clients create a CONNECT tunnel when a proxy is
        configured and the target URL uses HTTPS. This doesn't provide the
        security benefits of initiating TLS from the proxy. To address this,
        Webhook Sentry provides way of proxying to HTTPS targets. We should:

        1. Change the protocol in the URL to HTTP.
        2. Set the `X-WhSentry-TLS` header in your request to instruct Webhook
           Sentry to initiate TLS with the target server.

        https://github.com/juggernaut/webhook-sentry?tab=readme-ov-file#https-target

        Args:
            url (str): The URL to modify.

        Returns:
            str: The URL with the protocol changed from HTTPS to HTTP.
        """
        new_url = urlparse(url)
        return new_url._replace(scheme="http").geturl()

    def _prepare_login_request(self, url, *args, **kwargs):
        return super(PacerSession, self).post(
            self._change_protocol(url), **kwargs
        )

    def post(self, url, *args, **kwargs):
        return super().post(self._change_protocol(url), **kwargs)

    def get(self, url, *args, **kwargs):
        return super().get(self._change_protocol(url), **kwargs)


def log_into_pacer(
    username: str,
    password: str,
    client_code: str | None = None,
) -> tuple[RequestsCookieJar, str]:
    """Log into PACER and return the cookie jar

    :param username: A PACER username
    :param password: A PACER password
    :param client_code: A PACER client_code
    :return: A tuple containing the Request.CookieJar and the proxy address
    """
    s = ProxyPacerSession(
        username=username,
        password=password,
        client_code=client_code,
    )
    s.login()
    return s.cookies, s.proxy_address


def get_or_cache_pacer_cookies(
    user_pk: Union[str, int],
    username: str,
    password: str,
    client_code: str | None = None,
    refresh: bool = False,
) -> tuple[RequestsCookieJar, str]:
    """Get PACER cookies for a user or create and cache fresh ones

    For the PACER Fetch API, we store users' PACER cookies in Redis with a
    short expiration timeout. This way, we never store their password, and
    we only store their cookies temporarily.

    This function attempts to get cookies for a user from Redis. If it finds
    them, it returns them. If not, it attempts to log the user in and then
    returns the fresh cookies and the proxy used to login(after caching them).

    :param user_pk: The PK of the user attempting to store their credentials.
    Needed to create the key in Redis.
    :param username: The PACER username of the user
    :param password: The PACER password of the user
    :param client_code: The PACER client code of the user
    :param refresh: If True, refresh the cookies even if they're already cached
    :return: A tuple containing the Request.CookieJar and the proxy address
    """
    r = get_redis_interface("CACHE", decode_responses=False)
    cookies_data = get_pacer_cookie_from_cache(user_pk, r=r)
    ttl_seconds = r.ttl(session_key % user_pk)
    if cookies_data and ttl_seconds >= 300 and not refresh:
        # cookies were found in cache and ttl >= 5 minutes, return them
        if isinstance(cookies_data, tuple):
            return cookies_data
        return cookies_data, settings.EGRESS_PROXY_HOSTS[0]

    # Unable to find cookies in cache, are about to expire or refresh needed
    # Login and cache new values.
    cookies, proxy = log_into_pacer(username, password, client_code)
    cookie_expiration = 60 * 60
    r.set(
        session_key % user_pk,
        pickle.dumps((cookies, proxy)),
        ex=cookie_expiration,
    )
    return cookies, proxy


def get_pacer_cookie_from_cache(
    user_pk: Union[str, int],
    r: Redis | None = None,
):
    """Get the cookie for a user from the cache.

    :param user_pk: The ID of the user, can be a string or an ID
    :param r: A redis interface. If not provided, a fresh one is used. This is
    a performance enhancement.
    :return Either None if no cache cookies or the cookies if they're found.
    """
    if not r:
        r = get_redis_interface("CACHE", decode_responses=False)
    pickled_cookie = r.get(session_key % user_pk)
    if pickled_cookie:
        return pickle.loads(pickled_cookie)


def delete_pacer_cookie_from_cache(
    user_pk: Union[str, int],
    r: Redis | None = None,
):
    """Deletes the cookie for a user from the cache.

    :param user_pk: The ID of the user, can be a string or an ID
    :param r: A redis interface. If not provided, a fresh one is used. This is
    a performance enhancement.
    :return Either None if no cache cookies or the cookies if they're found.
    """
    if not r:
        r = get_redis_interface("CACHE", decode_responses=False)
    r.delete(session_key % user_pk)
