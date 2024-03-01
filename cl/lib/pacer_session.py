import pickle
from typing import Union

from juriscraper.pacer import PacerSession
from redis import Redis
from requests.cookies import RequestsCookieJar

from cl.lib.redis_utils import get_redis_interface

session_key = "session:pacer:cookies:user.%s"


def log_into_pacer(
    username: str,
    password: str,
    client_code: str | None = None,
) -> RequestsCookieJar:
    """Log into PACER and return the cookie jar

    :param username: A PACER username
    :param password: A PACER password
    :param client_code: A PACER client_code
    :return: Request.CookieJar
    """
    s = PacerSession(
        username=username,
        password=password,
        client_code=client_code,
    )
    s.login()
    return s.cookies


def get_or_cache_pacer_cookies(
    user_pk: Union[str, int],
    username: str,
    password: str,
    client_code: str | None = None,
    refresh: bool = False,
) -> RequestsCookieJar:
    """Get PACER cookies for a user or create and cache fresh ones

    For the PACER Fetch API, we store users' PACER cookies in Redis with a
    short expiration timeout. This way, we never store their password, and
    we only store their cookies temporarily.

    This function attempts to get cookies for a user from Redis. If it finds
    them, it returns them. If not, it attempts to log the user in and then
    returns the fresh cookies (after caching them).

    :param user_pk: The PK of the user attempting to store their credentials.
    Needed to create the key in Redis.
    :param username: The PACER username of the user
    :param password: The PACER password of the user
    :param client_code: The PACER client code of the user
    :param refresh: If True, refresh the cookies even if they're already cached
    :return: Cookies for the PACER user
    """
    r = get_redis_interface("CACHE", decode_responses=False)
    cookies = get_pacer_cookie_from_cache(user_pk, r=r)
    ttl_seconds = r.ttl(session_key % user_pk)
    if cookies and ttl_seconds >= 300 and not refresh:
        # cookies were found in cache and ttl >= 5 minutes, return them
        return cookies

    # Unable to find cookies in cache, are about to expire or refresh needed
    # Login and cache new values.
    cookies = log_into_pacer(username, password, client_code)
    cookie_expiration = 60 * 60
    r.set(session_key % user_pk, pickle.dumps(cookies), ex=cookie_expiration)
    return cookies


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
