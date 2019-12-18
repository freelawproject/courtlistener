import pickle
from juriscraper.pacer import PacerSession

from cl.lib.redis_utils import make_redis_interface

session_key = "session:pacer:cookies:user.%s"


def log_into_pacer(username, password):
    """Log into PACER and return the cookie jar

    :param username: A PACER username
    :param password: A PACER password
    :return: Request.CookieJar
    """
    s = PacerSession(username=username, password=password)
    s.login()
    return s.cookies


def get_or_cache_pacer_cookies(user_pk, username, password):
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
    :return: Cookies for the PACER user
    """
    r = make_redis_interface("CACHE")
    cookies = get_pacer_cookie_from_cache(user_pk, r=r)
    if cookies:
        return cookies

    # Unable to find cookies in cache. Login and cache new values.
    cookies = log_into_pacer(username, password)
    cookie_expiration = 60 * 60
    r.set(session_key % user_pk, pickle.dumps(cookies), ex=cookie_expiration)
    return cookies


def get_pacer_cookie_from_cache(user_pk, r=None):
    """Get the cookie for a user from the cache.

    :param r: A redis interface. If not provided, a fresh one is used. This is
    a performance enhancement.
    :return Either None if no cache cookies or the cookies if they're found.
    """
    if not r:
        r = make_redis_interface("CACHE")
    pickled_cookie = r.get(session_key % user_pk)
    if pickled_cookie:
        return pickle.loads(pickled_cookie)
