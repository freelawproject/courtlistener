from http import HTTPStatus

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import aget_object_or_404
from django.template.response import TemplateResponse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import RedirectView

from cl.visualizations.models import SCOTUSMap

WIKI_VIZ_URL = (
    f"{settings.WIKI_API_BASE_URL}/rest/v4/visualizations#deprecation-notice"
)


class VisualizationDeprecationRedirectView(RedirectView):
    """Redirect deprecated visualization pages to wiki docs."""

    permanent = True

    def get_redirect_url(self, *args, **kwargs) -> str:
        return WIKI_VIZ_URL


@xframe_options_exempt
async def view_embedded_visualization(
    request: HttpRequest, pk: int
) -> HttpResponse:
    """Return the embedded network page.

    Exempts the default xframe options to allow embedding in iframes.
    """
    viz = await aget_object_or_404(SCOTUSMap, pk=pk)

    status = None
    if viz.deleted:
        status = HTTPStatus.GONE
        title = "Visualization Deleted by Creator"
    else:
        user = await User.objects.aget(pk=viz.user_id)
        if viz.published is False and user != await request.auser():
            # Not deleted, private and not the owner
            status = HTTPStatus.UNAUTHORIZED
            title = "Private Visualization"
        else:
            title = f"Network Graph of {viz.title}"

    return TemplateResponse(
        request,
        "visualization_embedded.html",
        {"viz": viz, "title": title, "private": False},
        status=status,
    )
