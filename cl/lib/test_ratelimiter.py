"""Tests for cl.lib.ratelimiter, which has to work on async views too.

The views and the URLconf below are the fixtures: the bug these guard against
(#2930) only shows up when a request goes through Django's real handler, which
is what decides whether a view is awaited or run in a thread. Calling a
decorated view directly would pass either way.
"""

import asyncio
from http import HTTPStatus

from asgiref.sync import iscoroutinefunction
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.test import override_settings
from django.urls import path

from cl.lib.ratelimiter import get_ip_for_ratelimiter, make_ratelimiter
from cl.tests.cases import SimpleTestCase

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
        "db_cache": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
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

    def test_a_decorated_async_view_is_still_a_coroutine_function(
        self,
    ) -> None:
        """Django decides how to call a view by asking this question.

        If the answer is no, it runs the view in a thread and never awaits
        what comes back, which is the whole of #2930.
        """
        self.assertTrue(iscoroutinefunction(async_view))
        self.assertFalse(iscoroutinefunction(sync_view))

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
