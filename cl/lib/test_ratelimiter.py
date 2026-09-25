"""Tests for cl.lib.ratelimiter, which has to work on async views too.

The views and the URLconf below are the fixtures: the bug these guard against
(#2930) only shows up when a request goes through Django's real handler, which
is what decides whether a view is awaited or run in a thread. Calling a
decorated view directly would pass either way.
"""

import asyncio
import socket
from http import HTTPStatus
from unittest import mock

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import path
from django_ratelimit.exceptions import Ratelimited
from redis import ConnectionError

from cl.lib import ratelimiter
from cl.lib.ratelimiter import (
    View,
    get_ip_for_ratelimiter,
    host_is_approved,
    is_allowlisted,
    make_ratelimiter,
    ratelimit_deny_list,
    verify_ip_address,
)
from cl.tests.cases import SimpleTestCase

one_per_hour = make_ratelimiter(key=get_ip_for_ratelimiter, rate="1/h")
two_per_hour = make_ratelimiter(key=get_ip_for_ratelimiter, rate="2/h")
five_per_hour = make_ratelimiter(key=get_ip_for_ratelimiter, rate="5/h")


@two_per_hour
def sync_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


@two_per_hour
async def async_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


@five_per_hour
async def racing_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


def throttled(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Stand in for the real 429 page, which needs the full middleware stack.

    These tests are about who counts the request and whether the response is a
    response at all, not about what the page says.
    """
    return HttpResponse("throttled", status=HTTPStatus.TOO_MANY_REQUESTS)


urlpatterns = [
    path("sync/", sync_view),
    path("async/", async_view),
    path("racing/", racing_view),
]

VIEWER = {"CloudFront-Viewer-Address": "192.0.2.1:51396"}


@override_settings(
    ROOT_URLCONF="cl.lib.test_ratelimiter",
    MIDDLEWARE=["django_ratelimit.middleware.RatelimitMiddleware"],
    RATELIMIT_VIEW="cl.lib.test_ratelimiter.throttled",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            # Unique LOCATION so this cache is its own LocMemCache instance,
            # and process-local so a sibling --parallel worker clearing redis
            # can't reset our counters mid-test.
            "LOCATION": "ratelimiter-test",
        },
    },
)
class RateLimiterTest(SimpleTestCase):
    """Do the rate limiters throttle sync and async views alike?"""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()

    def test_a_sync_view_gets_throttled(self) -> None:
        for _ in range(2):
            r = self.client.get("/sync/", headers=VIEWER)
            self.assertEqual(r.status_code, HTTPStatus.OK)

        r = self.client.get("/sync/", headers=VIEWER)
        self.assertEqual(r.status_code, HTTPStatus.TOO_MANY_REQUESTS)

    async def test_an_async_view_gets_throttled(self) -> None:
        """Does an async view get a 429 rather than a 500?

        A sync decorator around an async view hands Django a coroutine nobody
        awaits, and the request dies with "didn't return an HttpResponse
        object" on the *first* request, before any limit is reached. See #2930.
        """
        for _ in range(2):
            r = await self.async_client.get("/async/", headers=VIEWER)
            self.assertEqual(r.status_code, HTTPStatus.OK)

        r = await self.async_client.get("/async/", headers=VIEWER)
        self.assertEqual(r.status_code, HTTPStatus.TOO_MANY_REQUESTS)

    async def test_simultaneous_async_requests_are_all_counted(self) -> None:
        """Does the limit hold when the requests arrive at once?

        Counting goes through the sync cache API on purpose: Django's async
        cache API increments with a read-modify-write, so racing requests
        overwrite each other's counts and sail past the limit.
        """
        responses = await asyncio.gather(
            *[
                self.async_client.get("/racing/", headers=VIEWER)
                for _ in range(20)
            ]
        )

        allowed = [r for r in responses if r.status_code == HTTPStatus.OK]
        self.assertEqual(len(allowed), 5)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "allowlist-test",
        },
    },
)
class AllowlistTest(SimpleTestCase):
    """Does the crawler allowlist answer, and remember, correctly?"""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.request = RequestFactory().get("/", headers=VIEWER)

    def test_a_yes_is_looked_up_once(self) -> None:
        with mock.patch.object(
            ratelimiter, "verify_ip_address", return_value=True
        ) as verify:
            self.assertTrue(is_allowlisted(self.request))
            self.assertTrue(is_allowlisted(self.request))

        self.assertEqual(verify.call_count, 1)

    def test_a_no_is_looked_up_once_too(self) -> None:
        """Is a rejection cached?

        Without this, an address that keeps hitting its limit pays for a pair
        of blocking DNS lookups on every single request.
        """
        with mock.patch.object(
            ratelimiter, "verify_ip_address", return_value=False
        ) as verify:
            self.assertFalse(is_allowlisted(self.request))
            self.assertFalse(is_allowlisted(self.request))

        self.assertEqual(verify.call_count, 1)

    def test_an_entry_from_the_old_format_still_counts_as_a_yes(self) -> None:
        """Entries written before this stored the IP string, not a bool."""
        cache.set("rl:allowlist:192.0.2.1", "192.0.2.1", 60)

        with mock.patch.object(ratelimiter, "verify_ip_address") as verify:
            self.assertTrue(is_allowlisted(self.request))

        verify.assert_not_called()

    def test_a_request_without_the_header_is_not_looked_up(self) -> None:
        """getfqdn("") answers for this host, so there is nothing to ask."""
        with mock.patch.object(ratelimiter, "verify_ip_address") as verify:
            self.assertFalse(is_allowlisted(RequestFactory().get("/")))

        verify.assert_not_called()


class CrawlerVerificationTest(SimpleTestCase):
    """Does the reverse-then-forward DNS check accept only real crawlers?"""

    def test_only_approved_domains_and_their_subdomains_match(self) -> None:
        """A look-alike domain must not pass for an approved one.

        The forward lookup only proves the requester controls the zone the
        PTR record names, so whoever registers "notgooglebot.com" controls
        that zone and would sail through a plain suffix match.
        """
        cases = {
            "crawl-66-249-66-1.googlebot.com": True,
            "googlebot.com": True,
            "rate-limited-proxy-66-249-90-77.google.com": True,
            "msnbot-157-55-39-1.search.msn.com": True,
            "CRAWL-1.GOOGLEBOT.COM.": True,
            "notgooglebot.com": False,
            "crawl.notgooglebot.com": False,
            "evilgoogle.com": False,
            "googlebot.com.evil.example": False,
            "notlocalhost": False,
        }
        for host, expected in cases.items():
            with self.subTest(host=host):
                self.assertEqual(host_is_approved(host), expected)

    def test_a_failed_forward_lookup_is_not_approved(self) -> None:
        """Is a DNS error on the forward lookup a "no" rather than a crash?

        socket.gethostbyname raises gaierror on NXDOMAIN, SERVFAIL or a
        timeout, and UnicodeError for a label over 63 characters, which
        whoever controls the PTR record can hand us.
        """
        for error in (socket.gaierror, UnicodeError):
            with (
                self.subTest(error=error.__name__),
                mock.patch.object(
                    ratelimiter,
                    "get_host_from_IP",
                    return_value="crawl-66-249-66-1.googlebot.com",
                ),
                mock.patch.object(
                    ratelimiter, "get_ip_from_host", side_effect=error
                ),
            ):
                self.assertFalse(verify_ip_address("66.249.66.1"))


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "deny-list-test",
        },
    },
)
class DenyListTest(SimpleTestCase):
    """What happens to a request that has already hit the crawler cap?"""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.request = RequestFactory().get("/", headers=VIEWER)

    @staticmethod
    def _decorate(view: View) -> View:
        """Wrap a view in a deny list whose limiter really counts.

        ratelimiter_all_1000_per_h no-ops under test, which would leave nothing
        for the allowlist to be asked about.
        """
        with mock.patch.object(
            ratelimiter, "ratelimiter_all_1000_per_h", one_per_hour
        ):
            return ratelimit_deny_list(view)

    def test_a_stranger_over_the_cap_is_refused(self) -> None:
        wrapped = self._decorate(lambda request: HttpResponse("ok"))

        self.assertEqual(wrapped(self.request).status_code, HTTPStatus.OK)
        with (
            mock.patch.object(
                ratelimiter, "verify_ip_address", return_value=False
            ),
            self.assertRaises(Ratelimited),
        ):
            wrapped(self.request)

    async def test_an_async_stranger_over_the_cap_is_refused(self) -> None:
        """Does the async wrapper re-raise from inside its except clause?"""

        async def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("ok")

        wrapped = self._decorate(view)

        response = await wrapped(self.request)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        with (
            mock.patch.object(
                ratelimiter, "verify_ip_address", return_value=False
            ),
            self.assertRaises(Ratelimited),
        ):
            await wrapped(self.request)

    def test_a_crawler_over_the_cap_gets_through(self) -> None:
        wrapped = self._decorate(lambda request: HttpResponse("ok"))

        self.assertEqual(wrapped(self.request).status_code, HTTPStatus.OK)
        with mock.patch.object(
            ratelimiter, "verify_ip_address", return_value=True
        ):
            self.assertEqual(wrapped(self.request).status_code, HTTPStatus.OK)

    def test_a_dead_cache_during_the_allowlist_check_is_not_a_500(
        self,
    ) -> None:
        """Does a Redis hiccup inside `except Ratelimited` fail open?

        The neighboring `except ConnectionError` only guards the try body, so
        an error raised while checking the allowlist would otherwise escape.
        """
        wrapped = self._decorate(lambda request: HttpResponse("ok"))

        self.assertEqual(wrapped(self.request).status_code, HTTPStatus.OK)
        with mock.patch.object(
            ratelimiter, "is_allowlisted", side_effect=ConnectionError
        ):
            self.assertEqual(wrapped(self.request).status_code, HTTPStatus.OK)

    def test_a_dns_failure_during_the_allowlist_check_is_not_a_500(
        self,
    ) -> None:
        """Does a broken forward lookup get the request refused, not crashed?"""
        wrapped = self._decorate(lambda request: HttpResponse("ok"))

        self.assertEqual(wrapped(self.request).status_code, HTTPStatus.OK)
        with (
            mock.patch.object(
                ratelimiter,
                "get_host_from_IP",
                return_value="crawl-66-249-66-1.googlebot.com",
            ),
            mock.patch.object(
                ratelimiter, "get_ip_from_host", side_effect=socket.gaierror
            ),
            self.assertRaises(Ratelimited),
        ):
            wrapped(self.request)

    async def test_a_dead_cache_is_not_a_500_on_an_async_view(self) -> None:
        async def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("ok")

        wrapped = self._decorate(view)

        response = await wrapped(self.request)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        with mock.patch.object(
            ratelimiter, "is_allowlisted", side_effect=ConnectionError
        ):
            response = await wrapped(self.request)

        self.assertEqual(response.status_code, HTTPStatus.OK)
