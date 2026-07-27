import sys

from django.http import HttpRequest
from django_ratelimit import UNSAFE
from django_ratelimit.core import get_header
from django_ratelimit.decorators import ratelimit


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
    ratelimiter_all_2_per_m = ratelimit(
        key=get_ip_for_ratelimiter,
        rate="2/m",
    )
    ratelimiter_unsafe_3_per_m = ratelimit(
        key=get_ip_for_ratelimiter,
        rate="3/m",
        method=UNSAFE,
    )
    ratelimiter_unsafe_5_per_d = ratelimit(
        key=get_ip_for_ratelimiter,
        rate="5/d",
        method=UNSAFE,
    )
    ratelimiter_unsafe_10_per_m = ratelimit(
        key=get_ip_for_ratelimiter,
        rate="10/m",
        method=UNSAFE,
    )
    ratelimiter_all_10_per_h = ratelimit(
        key=get_path_to_make_key,
        rate="10/h",
    )
    ratelimiter_unsafe_2000_per_h = ratelimit(
        key=get_path_to_make_key,
        rate="2000/h",
        method=UNSAFE,
    )


def parse_rate(rate: str) -> tuple[int, int]:
    """

    Given the request rate string, return a two tuple of:
    <allowed number of requests>, <period of time in seconds>

    (Stolen from Django Rest Framework.)
    """
    num, period = rate.split("/")
    num_requests = int(num)
    if len(period) > 1:
        # It takes the form of a 5d, or 10s, or whatever
        duration_multiplier = int(period[0:-1])
        duration_unit = period[-1]
    else:
        duration_multiplier = 1
        duration_unit = period[-1]
    duration_base = {"s": 1, "m": 60, "h": 3600, "d": 86400}[duration_unit]
    duration = duration_base * duration_multiplier
    return num_requests, duration
