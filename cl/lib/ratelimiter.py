import functools
import hashlib
import socket
import sys
from collections.abc import Callable, Sequence
from inspect import iscoroutinefunction
from typing import Any

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.conf import settings
from django.core.cache import BaseCache, caches
from django.http import HttpRequest
from django_ratelimit import ALL, UNSAFE
from django_ratelimit.core import get_header, is_ratelimited
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from redis import ConnectionError

type RatelimitKey = Callable[[str, HttpRequest], str] | str
type RatelimitMethod = str | Sequence[str | None]
type View = Callable[..., Any]


def get_user_ip_from_cloudfront_headers(request: HttpRequest) -> str:
    """Make a good key to use for caching the request's IP

    CloudFront provides a header that returns the user's IP and port. Weirdly,
    the port seems to be random, so we need to strip it to make the user's IP
    a consistent key.

    So we go from something like:

        96.23.39.106:51396

    To:

        96.23.39.106

    The port is split off the right-hand side because an IPv6 address is
    colon-separated itself: splitting on the first colon would truncate
    2600:1f18::1234:51396 to "2600", lumping unrelated clients into one key.

    :param request: The HTTP request from the user
    :return: A simple key that can be used to throttle the user if needed. The
        empty string when CloudFront didn't send the header, as in local
        development, where callers need their own fallback.
    """
    header = get_header(request, "CloudFront-Viewer-Address")
    return header.rsplit(":", 1)[0]


def get_ip_for_ratelimiter(group: str, request: HttpRequest) -> str:
    """A wrapper to get the IP in a ratelimiter

    :param group: Unused: The group key from the ratelimiter
    :param request: The HTTP request from the user
    :return: A simple key that can be used to throttle the user if needed.
    """
    return get_user_ip_from_cloudfront_headers(request)


def get_path_to_make_key(group: str, request: HttpRequest) -> str:
    """Return a string representing the full path to the requested page. This
    helper makes a good key to create a global limit to throttle requests.

    :param group: Unused: The group key from the ratelimiter
    :param request: The HTTP request from the user
    :return: A key that can be used to throttle request to a single URL if needed.
    """
    return request.path


def make_ratelimiter(
    *,
    key: RatelimitKey,
    rate: str,
    method: RatelimitMethod = ALL,
) -> Callable[[View], View]:
    """Build a rate-limiting decorator that works on sync and async views.

    django-ratelimit's own decorator is sync-only. Wrapped around an async
    view it hands Django a coroutine that nothing awaits, and the request dies
    with "didn't return an HttpResponse object" instead of being throttled, so
    MUST NOT be used directly on an async view. Sync views get that decorator
    unchanged here; async views get an async wrapper around it.

    The counting deliberately runs through django-ratelimit's sync path in a
    worker thread rather than through Django's async cache API. Every Django
    cache backend inherits ``BaseCache.aincr``, which is a read-modify-write
    -- RedisCache does not override it -- so concurrent requests lose
    increments and the limit doesn't hold. The sync path gets Redis's atomic
    INCR.

    A throttled request raises ``Ratelimited``, which RatelimitMiddleware
    turns into the 429 page. Unlike django-ratelimit's decorator, the async
    path here ignores the ``RATELIMIT_EXCEPTION_CLASS`` setting, which we
    don't set.

    :param key: What to count by, as django-ratelimit's ``key`` argument: our
        key functions take (group, request) and return the string to count.
    :param rate: A django-ratelimit rate, like "10/m".
    :param method: Which HTTP methods to count. Defaults to all of them.
    :return: A decorator to apply to a view.
    """
    sync_decorator = ratelimit(key=key, rate=rate, method=method)

    def decorator(view: View) -> View:
        if not iscoroutinefunction(view):
            return sync_decorator(view)

        @functools.wraps(view)
        async def wrapper(request: HttpRequest, *args, **kwargs):
            # thread_sensitive=False: this only touches the cache, so it has
            # no reason to hold the main thread, where it would serialize
            # every throttled view behind one Redis round trip at a time.
            limited = await sync_to_async(
                is_ratelimited, thread_sensitive=False
            )(
                request=request,
                group=None,
                fn=view,
                key=key,
                rate=rate,
                method=method,
                increment=True,
            )
            # setattr because django-ratelimit hangs this on the request
            # too, and HttpRequest has no such attribute to assign to.
            setattr(  # noqa: B010
                request,
                "limited",
                limited or getattr(request, "limited", False),
            )
            if limited:
                raise Ratelimited
            return await view(request, *args, **kwargs)

        return wrapper

    return decorator


# Decorators can't easily be mocked, and we need to not trigger this decorator
# during tests or else the first test works and the rest are blocked. So,
# check if we're doing a test and adjust the decorator accordingly.
if "test" in sys.argv:
    ratelimiter_all_250_per_h = lambda func: func
    ratelimiter_all_2_per_m = lambda func: func
    ratelimiter_unsafe_3_per_m = lambda func: func
    ratelimiter_unsafe_5_per_d = lambda func: func
    ratelimiter_unsafe_10_per_m = lambda func: func
    ratelimiter_all_10_per_h = lambda func: func
    ratelimiter_unsafe_2000_per_h = lambda func: func
else:
    ratelimiter_all_250_per_h = make_ratelimiter(
        key=get_ip_for_ratelimiter,
        rate="250/h",
    )
    ratelimiter_all_2_per_m = make_ratelimiter(
        key=get_ip_for_ratelimiter,
        rate="2/m",
    )
    ratelimiter_unsafe_3_per_m = make_ratelimiter(
        key=get_ip_for_ratelimiter,
        rate="3/m",
        method=UNSAFE,
    )
    ratelimiter_unsafe_5_per_d = make_ratelimiter(
        key=get_ip_for_ratelimiter,
        rate="5/d",
        method=UNSAFE,
    )
    ratelimiter_unsafe_10_per_m = make_ratelimiter(
        key=get_ip_for_ratelimiter,
        rate="10/m",
        method=UNSAFE,
    )
    ratelimiter_all_10_per_h = make_ratelimiter(
        key=get_path_to_make_key,
        rate="10/h",
    )
    ratelimiter_unsafe_2000_per_h = make_ratelimiter(
        key=get_path_to_make_key,
        rate="2000/h",
        method=UNSAFE,
    )

# See: https://www.bing.com/webmaster/help/how-to-verify-bingbot-3905dc26
# and: https://support.google.com/webmasters/answer/80553?hl=en
APPROVED_DOMAINS = [
    "google.com",
    "googlebot.com",
    "search.msn.com",
    "localhost",  # For dev.
]


def should_bypass_ratelimit(request: HttpRequest) -> bool:
    """Should a request that hit its limit be let through anyway?

    True for an approved crawler, and also when the cache can't be reached to
    find out: a Redis outage shouldn't turn the allowlist into a 500, so it
    fails open exactly like the rate-limit check itself does.

    :param request: The HTTP request from the user
    :return: True when the view should run despite the limit, else False.
    """
    try:
        return is_allowlisted(request)
    except ConnectionError:
        return True


def ratelimit_deny_list(view: View) -> View:
    """A wrapper for the ratelimit function that adds an allowlist for approved
    crawlers.

    Works on sync and async views alike. The allowlist check does a pair of
    DNS lookups, so on an async view it runs in a worker thread rather than on
    the event loop.
    """
    ratelimited_view = ratelimiter_all_250_per_h(view)

    if iscoroutinefunction(view):

        @functools.wraps(view)
        async def async_wrapper(request: HttpRequest, *args, **kwargs):
            try:
                return await ratelimited_view(request, *args, **kwargs)
            except Ratelimited:
                # thread_sensitive=False for the same reason as in
                # make_ratelimiter: this touches only the cache and DNS, and
                # the shared thread-sensitive worker is the wrong place to
                # wait on a name server.
                bypass = await sync_to_async(
                    should_bypass_ratelimit, thread_sensitive=False
                )(request)
                if not bypass:
                    raise
                return await view(request, *args, **kwargs)
            except ConnectionError:
                # Unable to connect to redis, let the view proceed this time.
                return await view(request, *args, **kwargs)

        return async_wrapper

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return ratelimited_view(request, *args, **kwargs)
        except Ratelimited:
            if not should_bypass_ratelimit(request):
                raise
            return view(request, *args, **kwargs)
        except ConnectionError:
            # Unable to connect to redis, let the view proceed this time.
            return view(request, *args, **kwargs)

    return wrapper


def get_host_from_IP(ip_address: str) -> str:
    """Get the host for an IP address by doing a reverse DNS lookup. Return
    the value as a string.
    """
    return socket.getfqdn(ip_address)


def get_ip_from_host(host: str) -> str:
    """Do a forward DNS lookup of the host found in step one."""
    return socket.gethostbyname(host)


def host_is_approved(host: str) -> bool:
    """Check whether the domain is in our approved allowlist."""
    return any(
        host.endswith(approved_domain) for approved_domain in APPROVED_DOMAINS
    )


def verify_ip_address(ip_address: str) -> bool:
    """Do authentication checks for the IP address requesting the page."""
    # First we do a rDNS lookup of the IP.
    host = get_host_from_IP(ip_address)

    #  Then we check the returned host to ensure it's an approved crawler
    if host_is_approved(host):
        # If it's approved, do a forward DNS lookup to get the IP from the host.
        # If that matches the original IP, we're good.
        if ip_address == get_ip_from_host(host):
            # Everything checks out!
            return True
    return False


def get_ratelimit_cache() -> BaseCache:
    """Return the cache backend that the rate limiters count in.

    :return: The cache named by the RATELIMIT_USE_CACHE setting, or the default
    cache if that setting is unset.
    """
    cache_name = getattr(settings, "RATELIMIT_USE_CACHE", "default")
    return caches[cache_name]


def is_allowlisted(request: HttpRequest) -> bool:
    """Checks if the IP address is allowlisted due to belonging to an approved
    crawler.

    Both answers are cached, not just the "yes". Callers reach this only for
    an address that is already over its limit, so a "no" that wasn't stored
    would mean a fresh pair of blocking DNS lookups on every request from
    whoever is hammering us. The "no" gets a much shorter life than the "yes",
    so a crawler that moves to a new address is picked up soon after.

    May raise ``redis.ConnectionError`` when the cache is unreachable; callers
    that must not 500 should go through ``should_bypass_ratelimit`` instead.

    :param request: The HTTP request from the user
    :return: True when the request comes from an approved crawler, else False.
    """
    cache = get_ratelimit_cache()
    ip_address = get_user_ip_from_cloudfront_headers(request)
    if not ip_address:
        # No CloudFront header, as in local development. There's nothing to
        # look up, and getfqdn("") would answer for this host instead.
        return False

    allowlist_key = f"rl:allowlist:{ip_address}"

    # bool() rather than truthiness on the entry itself: a False is a real
    # cached answer, and entries written before this stored the IP string.
    if (cached := cache.get(allowlist_key)) is not None:
        return bool(cached)

    approved_crawler = verify_ip_address(ip_address)
    a_week = 60 * 60 * 24 * 7
    an_hour = 60 * 60
    cache.set(
        allowlist_key,
        approved_crawler,
        a_week if approved_crawler else an_hour,
    )

    return approved_crawler


def parse_rate(rate: str) -> tuple[int, int]:
    """
    Given the request rate string, return a two tuple of:
    <allowed number of requests>, <period of time in seconds>

    Supported forms:
      - "1/s", "60/min", "5000/hour", "100/day" — unit form (uses first letter)
      - "10/5s", "1/5m"                         — multiplier + single-letter

    (Stolen from Django Rest Framework.)
    """
    num, period = rate.split("/")
    num_requests = int(num)
    if len(period) > 1 and not period.isalpha():
        # It takes the form of a 5d, or 10s, or whatever
        duration_multiplier = int(period[0:-1])
        duration_unit = period[-1]
    else:
        duration_multiplier = 1
        duration_unit = period[0]
    duration_base = {"s": 1, "m": 60, "h": 3600, "d": 86400}[duration_unit]
    return num_requests, duration_base * duration_multiplier


####################################
# Failed sign-in throttling        #
####################################
FAILED_LOGIN_LIMIT = 10
FAILED_LOGIN_WINDOW = 60 * 15  # Seconds


def make_failed_login_key(identifier: str) -> str:
    """Build the cache key holding the failed sign-in count for an identifier.

    The identifier is lowercased before hashing, so varying the case of a
    username or email doesn't buy a fresh bucket. Hashing keeps the key a fixed,
    cache-safe length and keeps submitted email addresses out of the cache.

    :param identifier: The account identifier submitted on the sign-in form. It
    is whatever the person typed, not a resolved user, so that attempts against
    addresses with no account get counted too. Counting only resolved users
    would turn the throttle into an account-existence oracle.
    :return: The cache key to count that identifier's failures under.
    """
    digest = hashlib.blake2s(
        identifier.strip().lower().encode(), digest_size=16
    ).hexdigest()
    return f"rl:failed-login:{digest}"


def count_login_attempt(identifier: str) -> int:
    """Count one sign-in attempt against an identifier and report the total.

    Count the attempt *before* checking the password, and compare the return
    against FAILED_LOGIN_LIMIT to decide whether to go on. Reading the count and
    raising it separately would not hold under load: password checking is slow,
    so a burst of simultaneous attempts would all read the same pre-increment
    count and all be let through. Here each attempt gets a distinct number.

    Counting attempts rather than failures costs the caller nothing, because a
    successful sign-in clears the counter; what survives in it is failures.

    Call this exactly once per sign-in POST, no matter how many candidate
    accounts the submitted password has to be checked against, so the count
    tracks attempts rather than password hashes.

    The window is anchored to the first attempt in it: add() sets the expiry and
    incr() leaves it alone, so attempts made while over the limit raise the count
    without pushing the block out. Nobody can hold an account's owner out beyond
    the original window by continuing to guess, and nothing survives the expiry,
    so there is no state for staff to clear.

    Callers MUST reject an over-limit attempt with the same error a wrong
    password gets. A distinct message would tell an attacker they'd found a live
    account.

    :param identifier: The account identifier submitted on the sign-in form.
    :return: How many attempts are now counted in the current window.
    """
    if not identifier:
        return 0
    cache = get_ratelimit_cache()
    key = make_failed_login_key(identifier)
    if cache.add(key, 1, FAILED_LOGIN_WINDOW):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # The window lapsed between the add() and the incr(), so the count this
        # would have raised is gone. Start the next window instead of 500ing.
        cache.add(key, 1, FAILED_LOGIN_WINDOW)
        return 1


def reset_failed_login_count(identifier: str) -> None:
    """Forget an identifier's failed sign-ins after it authenticates.

    :param identifier: The account identifier submitted on the sign-in form.
    :return: None
    """
    if not identifier:
        return
    get_ratelimit_cache().delete(make_failed_login_key(identifier))
