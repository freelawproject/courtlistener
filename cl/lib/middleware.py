from collections.abc import Awaitable, Callable
from inspect import iscoroutinefunction
from typing import cast

from asgiref.sync import markcoroutinefunction
from django.http import HttpRequest, HttpResponseBase
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.template.response import TemplateResponse
from waffle import flag_is_active

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

    htmx requests are swapped by the "X-CL-Design" header instead of the
    flag. `new_base.html` sends it with value "v2" on every htmx request
    from a v2 page, so a partial always matches the page that asked for it.
    A flagged user on a page that is still legacy gets the legacy partial.
    Endpoints called by both stacks should return the legacy template name
    and let this middleware swap it.

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
        if self.template_exists(old_template):
            if request.headers.get("Hx-Request"):
                # A partial must match the page already in the browser, and
                # only v2 pages mark their htmx requests (see new_base.html).
                expects_v2 = request.headers.get("X-CL-Design") == "v2"
            else:
                expects_v2 = flag_is_active(request, "use_new_design")

            if not expects_v2:
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
