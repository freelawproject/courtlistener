import pickle
import random
from dataclasses import dataclass
from http.cookiejar import Cookie
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from httpx import URL, Cookies, Request, Response
from juriscraper.pacer import PacerSession
from redis import Redis

from cl.lib.redis_utils import get_redis_interface

session_key = "session:pacer:cookies:user.%s"


@dataclass
class SessionData:
    """
    The goal of this class is to encapsulate data required for PACER requests.

    This class serves as a lightweight container for PACER session data,
    excluding authentication details for efficient caching.

    Handles default values for the `proxy` attribute when not explicitly
    provided, indicating session data was not generated using the
    `ProxyPacerSession` class.
    """

    cookies: Cookies | None
    proxy_address: str = ""

    def __post_init__(self) -> None:
        """Normalize cached cookies and supply a default proxy."""
        if not self.proxy_address:
            self.proxy_address = settings.EGRESS_PROXY_HOSTS[0]
        if self.cookies is not None:
            if not isinstance(self.cookies, Cookies):
                self.cookies = Cookies(self.cookies)
            allow_insecure_cookie_transport(self.cookies)

    def __getstate__(self) -> dict[str, Any]:
        """Serialize cookies without HTTPX's unpicklable cookie-jar lock."""
        state = self.__dict__.copy()
        if self.cookies is not None:
            state["cookies"] = list(self.cookies.jar)
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore cookies, including older caches containing cookie jars."""
        if isinstance(state["cookies"], list):
            cookies = Cookies()
            for cookie in state["cookies"]:
                cookies.jar.set_cookie(cookie)
            state["cookies"] = cookies
        self.__dict__.update(state)
        self.__post_init__()


def allow_insecure_cookie_transport(cookies: Cookies) -> None:
    """Clear Secure flags so proxy-rewritten PACER requests send cookies."""
    for cookie in cookies.jar:
        if not isinstance(cookie, Cookie):
            raise TypeError(f"expected Cookie, got {type(cookie).__name__}")
        cookie.secure = False


class ProxyPacerSession(PacerSession):
    """
    Route PACER requests, including redirects, through Webhook Sentry.

    - Sets the 'X-WhSentry-TLS' header to 'true' for all requests.
    - Replaces 'https://' with 'http://' in the URL before making the request.
    - Uses a proxy server for all requests.

    Secure cookie flags are cleared because TLS is initiated by the proxy.
    """

    def __init__(
        self,
        cookies=None,
        username=None,
        password=None,
        client_code=None,
        proxy=None,
        *args,
        **kwargs,
    ):
        self.proxy_address = proxy if proxy else self._pick_proxy_connection()
        super().__init__(
            cookies,
            username,
            password,
            client_code,
            *args,
            proxy=self.proxy_address,
            **kwargs,
        )
        allow_insecure_cookie_transport(self.cookies)

    async def _send_single_request(self, request: Request) -> Response:
        """Apply proxy transport rules to each request in a redirect chain."""
        request.url = self._change_protocol(request.url)
        request.headers["X-WhSentry-TLS"] = "true"
        response = await super()._send_single_request(request)
        # HTTPX has extracted cookies here, but has not built a redirect yet.
        allow_insecure_cookie_transport(self.cookies)
        return response

    def _pick_proxy_connection(self) -> str:
        """
        Picks a proxy connection string from available options.

        this function randomly chooses a string from the
        `settings.EGRESS_PROXY_HOSTS` list and returns it.

        Returns:
            str: The chosen proxy connection string.
        """
        return random.choice(settings.EGRESS_PROXY_HOSTS)

    def _change_protocol(self, url: URL | str) -> URL:
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
            url (URL): The URL to modify.

        Returns:
            URL: The URL with the protocol changed from HTTPS to HTTP.
        """
        return URL(url, scheme="http")


async def log_into_pacer(
    username: str,
    password: str,
    client_code: str | None = None,
) -> SessionData:
    """Log into PACER and returns a SessionData object containing the session's
    cookies and proxy information.

    :param username: A PACER username
    :param password: A PACER password
    :param client_code: A PACER client_code
    :return: A SessionData object containing the session's cookies and proxy.
    """
    async with ProxyPacerSession(
        username=username,
        password=password,
        client_code=client_code,
    ) as s:
        await s.login()
        return SessionData(s.cookies, s.proxy_address)


async def get_or_cache_pacer_cookies(
    user_pk: str | int,
    username: str,
    password: str,
    client_code: str | None = None,
    refresh: bool = False,
) -> SessionData:
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
    :return: A SessionData object containing the session's cookies and proxy.
    """
    r = get_redis_interface("CACHE", decode_responses=False)
    cookies_data = await get_pacer_cookie_from_cache(user_pk, r=r)
    ttl_seconds = await sync_to_async(r.ttl)(session_key % user_pk)
    if cookies_data and ttl_seconds >= 300 and not refresh:
        # cookies were found in cache and ttl >= 5 minutes, return them
        return cookies_data

    # Unable to find cookies in cache, are about to expire or refresh needed
    # Login and cache new values.
    session_data = await log_into_pacer(username, password, client_code)
    cookie_expiration = 60 * 60
    await sync_to_async(r.set)(
        session_key % user_pk,
        pickle.dumps(session_data),
        ex=cookie_expiration,
    )
    return session_data


@sync_to_async
def get_pacer_cookie_from_cache(
    user_pk: str | int,
    r: Redis | None = None,
):
    """Get the cookie for a user from the cache.

    :param user_pk: The ID of the user, can be a string or an ID
    :param r: A redis interface. If not provided, a fresh one is used. This is
    a performance enhancement.
    :return: The cached session, or None if it is missing or invalid.
    """
    if not r:
        r = get_redis_interface("CACHE", decode_responses=False)
    pickled_cookie = r.get(session_key % user_pk)
    if pickled_cookie:
        try:
            session_data = pickle.loads(pickled_cookie)
            if isinstance(session_data, SessionData) and isinstance(
                session_data.cookies, Cookies
            ):
                return session_data
        except Exception:
            pass
        r.delete(session_key % user_pk)


@sync_to_async
def delete_pacer_cookie_from_cache(
    user_pk: str | int,
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
