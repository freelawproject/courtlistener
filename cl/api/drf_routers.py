"""DRF routers for the REST API.

These live apart from cl.api.utils because DRF's settings import that module,
and importing rest_framework.routers from it would be circular.
"""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import APIRootView, DefaultRouter
from waffle import flag_is_active


class WaffleFlaggedAPIRootView(APIRootView):
    """API root that leaves out routes whose waffle flag is off."""

    # Keep the title and description DRF's root shows in the browsable API,
    # which would otherwise come from this class's name and docstring.
    name = "Api Root"
    description = APIRootView.__doc__
    # Maps route prefixes to the waffle flag that must be on to list them.
    route_flags: dict[str, str] = {}

    def get(self, request: Request, *args, **kwargs) -> Response:
        """List the routes whose flag, if any, is active for the request."""
        self.api_root_dict = {
            prefix: url_name
            for prefix, url_name in (self.api_root_dict or {}).items()
            if (flag := self.route_flags.get(prefix)) is None
            or flag_is_active(request._request, flag)
        }
        return super().get(request, *args, **kwargs)


class WaffleFlagRouter(DefaultRouter):
    """Router whose API root hides viewsets that use ``WaffleFlagMixin``.

    The root view is built once, so the flags are read from the viewsets
    when the URLs are generated and evaluated on every root request.
    """

    APIRootView = WaffleFlaggedAPIRootView

    def get_api_root_view(self, api_urls=None):
        """Build the root view, telling it which routes are flagged."""
        list_name = self.routes[0].name
        api_root_dict = {}
        route_flags = {}
        for prefix, viewset, basename in self.registry:
            api_root_dict[prefix] = list_name.format(basename=basename)
            if flag := getattr(viewset, "waffle_flag", None):
                route_flags[prefix] = flag
        return self.APIRootView.as_view(
            api_root_dict=api_root_dict, route_flags=route_flags
        )
