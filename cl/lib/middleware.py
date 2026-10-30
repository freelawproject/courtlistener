from collections.abc import Awaitable, Callable
from inspect import iscoroutinefunction
from typing import cast

from asgiref.sync import markcoroutinefunction
from django.http import Http404, HttpRequest, HttpResponseBase
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.template.response import TemplateResponse
from waffle import flag_is_active

from cl.search.forms import CorpusSearchForm

# Templates a view returns on their own (htmx partials) live under this
# prefix. .github/scripts/frontend_checks.py mirrors it in is_v2_partial.
V2_PARTIALS_PREFIX = "v2_includes/"
# Unfinished redesign pages use this prefix instead of "v2_" and are only
# served to visitors with both "use_new_design" and this flag active.
# Promoting a page means renaming its template from this prefix to "v2_".
WIP_PROPS = {
    "flag": "use_wip_design",
    "prefix": "wip_",
    "partials_prefix": "wip_includes/",
}


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

    Unfinished pages use the WIP prefix (see WIP_PROPS) in place of "v2_".
    They are served only when both "use_new_design" and the WIP flag are
    active, and take precedence over a "v2_" version of the same page.

    WIP templates that do not have a legacy counterpart are available to
    **everyone** with both flags enabled, and raise Http404 for everyone
    else, since there is no template they are allowed to see.

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
        # evaluations first. Past this gate, either "use_new_design" is active or
        # the legacy template is missing, in which case the flag was never checked.
        old_template_exists = self.template_exists(old_template)
        if old_template_exists and not flag_is_active(
            request, "use_new_design"
        ):
            return response

        v2_template_name = f"v2_{old_template}"
        wip_template_name = f"{WIP_PROPS['prefix']}{old_template}"
        v2_template_exists = self.template_exists(v2_template_name)
        wip_template_exists = self.template_exists(wip_template_name)

        # The WIP flag only counts together with "use_new_design". When the
        # legacy template exists, the gate above already confirmed that flag;
        # otherwise it was skipped and has to be checked here. The WIP flag goes
        # last so pages without a WIP template never evaluate it.
        if (
            wip_template_exists
            and (
                old_template_exists
                or flag_is_active(request, "use_new_design")
            )
            and flag_is_active(request, WIP_PROPS["flag"])
        ):
            new_template_name = wip_template_name
        elif v2_template_exists:
            new_template_name = v2_template_name
        elif not old_template_exists and wip_template_exists:
            # WIP-only page and the visitor isn't opted in: there's no
            # template they're allowed to see. Rendering the missing legacy
            # template would be a 500, so answer as if the page didn't exist.
            raise Http404
        else:
            return response

        response.template_name = new_template_name

        # Partials never render the header, so the search form it needs would
        # only be wasted work for them. The name decides, not the HX-Request
        # header: the server knows what it renders, and a boosted full-page
        # request must still get the form.
        if not new_template_name.startswith(
            (V2_PARTIALS_PREFIX, WIP_PROPS["partials_prefix"])
        ):
            # pyrefly:ignore[unsupported-operation] False positive based on Django docs
            response.context_data["search_form"] = CorpusSearchForm()

        return response
