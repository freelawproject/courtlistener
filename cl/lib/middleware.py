from http import HTTPStatus
from typing import Callable

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.utils.cache import add_never_cache_headers


class MaintenanceModeMiddleware:
    """Provides maintenance mode if requested in settings.

    This cribs heavily from:
      - https://github.com/fabiocaccamo/django-maintenance-mode

    But there are a few differences. First, we drop a lot of the functionality.
    For example, there's no distinction between staff and super users, there's
    no mechanism for enabling this by script or URL, etc.

    Second, we set this up so that it raises a MiddlewareNotUsed exception if
    maintenance mode is not enabled. Because this is in init instead of in the
    process_request method, it runs the logic once, when the code is
    initialized, instead of running it on every page request. This should make
    it (very slightly) faster.

    The third difference is that this provides is that it sets the maintenance
    mode page to never be cached.

    We also eschew using the code from Github to reduce our reliance on third-
    party code.
    """

    def __init__(self, get_response: Callable):
        if not settings.MAINTENANCE_MODE_ENABLED:
            raise MiddlewareNotUsed
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if hasattr(request, "user"):
            if settings.MAINTENANCE_MODE_ALLOW_STAFF and request.user.is_staff:
                return response

        r = render(
            request,
            "maintenance.html",
            {"private": True},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )
        add_never_cache_headers(r)
        return r


class RobotsHeaderMiddleware:
    """Adds x-robots-tag HTTP header to any request that has `private=True`

    There's some evidence and good logic to support the idea that using the
    x-robots-tag HTTP header uses less of a site's "crawl budget" than
    using the noindex HTML tag. Logically, this makes sense because crawlers
    can simply download the headers and stop, instead of downloading and
    parsing pages.

    Because we have good measures to make sure that the `private` context
    variable is set on every page, this middleware uses that variable to set
    the HTTP headers too.
    """

    def __init__(self, get_response: Callable):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        return response

    def process_template_response(
        self,
        request: HttpRequest,
        response: TemplateResponse,
    ) -> TemplateResponse:
        if getattr(response, "context_data", None) is None:
            return response

        private = False
        if response.context_data:
            private = response.context_data.get("private", False)
        if private:
            response.headers["X-Robots-Tag"] = (
                "noindex, noarchive, noimageindex"
            )
        return response
