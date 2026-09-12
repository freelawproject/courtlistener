import functools
import socket
import sys
from collections.abc import Callable, Sequence
from typing import Any

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.conf import settings
from django.core.cache import caches
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

    :param request: The HTTP request from the user
    :return: A simple key that can be used to throttle the user if needed.
    """
    header = get_header(request, "CloudFront-Viewer-Address")
    return header.split(":")[0]


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


ratelimiter_all_250_per_h = make_ratelimiter(
    key=get_ip_for_ratelimiter,
    rate="250/h",
)
# Decorators can't easily be mocked, and we need to not trigger this decorator
# during tests or else the first test works and the rest are blocked. So,
# check if we're doing a test and adjust the decorator accordingly.
if "test" in sys.argv:
    ratelimiter_all_2_per_m = lambda func: func
    ratelimiter_unsafe_3_per_m = lambda func: func
    ratelimiter_unsafe_5_per_d = lambda func: func
    ratelimiter_unsafe_10_per_m = lambda func: func
    ratelimiter_all_10_per_h = lambda func: func
    ratelimiter_unsafe_2000_per_h = lambda func: func
else:
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
            except Ratelimited as e:
                if await sync_to_async(is_allowlisted)(request):
                    return await view(request, *args, **kwargs)
                else:
                    raise e
            except ConnectionError:
                # Unable to connect to redis, let the view proceed this time.
                return await view(request, *args, **kwargs)

        return async_wrapper

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return ratelimited_view(request, *args, **kwargs)
        except Ratelimited as e:
            if is_allowlisted(request):
                return view(request, *args, **kwargs)
            else:
                raise e
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


def is_allowlisted(request: HttpRequest) -> bool:
    """Checks if the IP address is allowlisted due to belonging to an approved
    crawler.

    Returns True if so, else False.
    """
    cache_name = getattr(settings, "RATELIMIT_USE_CACHE", "default")
    cache = caches[cache_name]
    allowlist_cache_prefix = "rl:allowlist"
    ip_address = get_user_ip_from_cloudfront_headers(request)
    if ip_address is None:
        return False

    allowlist_key = f"{allowlist_cache_prefix}:{ip_address}"

    # Check if the ip address is in our allowlist.
    if cache.get(allowlist_key):
        return True

    # If not whitelisted, verify the IP address and add it to the cache for
    # future requests.
    approved_crawler = verify_ip_address(ip_address)

    if approved_crawler:
        # Add the IP to our cache with a one week expiration date
        a_week = 60 * 60 * 24 * 7
        cache.set(allowlist_key, ip_address, a_week)

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
