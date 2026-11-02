from collections.abc import Awaitable, Callable
from http import HTTPStatus
from inspect import iscoroutinefunction
from typing import cast

from asgiref.sync import markcoroutinefunction, sync_to_async
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from waffle import flag_is_active, switch_is_active

from cl.search.forms import CorpusSearchForm

# Templates a view returns on their own (htmx partials) live under this
# prefix. .github/scripts/frontend_checks.py mirrors it in is_v2_partial.
V2_PARTIALS_PREFIX = "v2_includes/"


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

    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: Callable[
            [HttpRequest], HttpResponseBase | Awaitable[HttpResponseBase]
        ],
    ):
        self.get_response: Callable[
            [HttpRequest], HttpResponseBase | Awaitable[HttpResponseBase]
        ] = get_response
        self.async_mode: bool = iscoroutinefunction(self.get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(
        self, request: HttpRequest
    ) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self.async_mode:
            return self.__acall__(request)
        response = self.get_response(request)
        return response

    async def __acall__(self, request: HttpRequest) -> HttpResponseBase:
        response = await cast(
            Awaitable[HttpResponseBase], self.get_response(request)
        )
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


class IncrementalNewTemplateMiddleware:
    """
    Checks waffle flag for new design and changes the old template
    with the new one if it exists.

    To identify the new template we prepend "v2_" to the old template name.
    Note this means if the old template_name includes a dir, like
    "help/index.html", the new template should be in "v2_help/index.html"
    and NOT in "help/v2_index.html".

    v2 templates that do not have a legacy counterpart are assumed to be
    available for **everyone**.

    TODO: Remove this middleware once new design is completely rolled out.
    """

    def __init__(
        self, get_response: Callable[[HttpRequest], HttpResponseBase]
    ):
        self.get_response: Callable[[HttpRequest], HttpResponseBase] = (
            get_response
        )

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        return response

    @staticmethod
    def template_exists(template_name: str) -> bool:
        """Check if a template is resolvable by the configured loaders."""
        try:
            get_template(template_name)
        except TemplateDoesNotExist:
            return False
        return True

    def process_template_response(
        self, request: HttpRequest, response: HttpResponseBase
    ) -> HttpResponseBase | TemplateResponse:
        if not isinstance(response, TemplateResponse) or response.is_rendered:
            return response

        # {response.template_name} could return a list if TemplateView is used directly
        old_template = response.template_name
        if isinstance(old_template, (list, tuple)):
            # Check if the first template exists anywhere in the project
            try:
                get_template(old_template[0])
                old_template = old_template[0]
            except TemplateDoesNotExist:
                old_template = (
                    old_template[1]
                    if len(old_template) > 1
                    else old_template[0]
                )

        if not isinstance(old_template, str):
            return response

        # Checking flag_is_active hits the db, so be sure to short-circuit for cheaper
        # evaluations first
        if self.template_exists(old_template) and not flag_is_active(
            request, "use_new_design"
        ):
            return response

        new_template_name = f"v2_{old_template}"

        if not self.template_exists(new_template_name):
            return response

        response.template_name = new_template_name

        # Partials never render the header, so the search form it needs would
        # only be wasted work for them. The name decides, not the HX-Request
        # header: the server knows what it renders, and a boosted full-page
        # request must still get the form.
        if not new_template_name.startswith(V2_PARTIALS_PREFIX):
            # pyrefly:ignore[unsupported-operation] False positive based on Django docs
            response.context_data["search_form"] = CorpusSearchForm()

        return response


MAINTENANCE_MODE_SWITCH = "maintenance-mode"
# Seconds clients and crawlers are told to wait before retrying.
MAINTENANCE_MODE_RETRY_AFTER = "3600"


def maintenance_mode_is_active() -> bool:
    """Check whether the maintenance-mode Waffle switch is active."""
    return switch_is_active(MAINTENANCE_MODE_SWITCH)


class MaintenanceModeMiddleware:
    """Return 503 responses while maintenance mode is enabled.

    This middleware runs before SessionMiddleware to avoid database work
    for requests blocked by maintenance mode.

    The admin remains accessible so maintenance mode can be disabled.
    The monitoring prefix is also exempt to keep ALB health checks and
    Prometheus scrapes working. Otherwise, failing health checks would
    cause the ALB to remove pods from service, delaying recovery.

    Behind CloudFront, the response body is replaced by the static S3
    5xx page. The response defined here is therefore only visible on
    direct or local access.
    """

    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: Callable[
            [HttpRequest], HttpResponseBase | Awaitable[HttpResponseBase]
        ],
    ):
        self.get_response: Callable[
            [HttpRequest], HttpResponseBase | Awaitable[HttpResponseBase]
        ] = get_response
        self.async_mode: bool = iscoroutinefunction(self.get_response)
        if self.async_mode:
            markcoroutinefunction(self)
        # Resolve these paths here so the URLconf can load lazily.
        # Exempt the entire monitoring prefix, not just the health check.
        monitoring_root = reverse("health_check").strip("/").split("/")[0]
        self.exempt_prefixes: tuple[str, ...] = (
            reverse("admin:index"),
            f"/{monitoring_root}/",
        )

    def __call__(
        self, request: HttpRequest
    ) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self.async_mode:
            return self.__acall__(request)

        if self._is_exempt(request) or not maintenance_mode_is_active():
            return self.get_response(request)

        return self._unavailable()

    async def __acall__(self, request: HttpRequest) -> HttpResponseBase:
        if (
            self._is_exempt(request)
            or not await sync_to_async(maintenance_mode_is_active)()
        ):
            return await cast(
                Awaitable[HttpResponseBase], self.get_response(request)
            )

        return self._unavailable()

    def _is_exempt(self, request: HttpRequest) -> bool:
        """Check whether the request is exempt from maintenance mode."""
        return request.path.startswith(self.exempt_prefixes)

    @staticmethod
    def _unavailable() -> HttpResponse:
        """Build the 503 response returned during maintenance."""
        response = HttpResponse(
            "CourtListener is down for maintenance. Please try again shortly.",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="text/plain",
            headers={"Retry-After": MAINTENANCE_MODE_RETRY_AFTER},
        )
        add_never_cache_headers(response)
        return response
