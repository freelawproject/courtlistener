from cl.lib.bot_detector import is_bot
from cl.visualizations.models import SCOTUSMap

from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext


def view_visualization(request, pk, _):
    """A simple page for viewing a visualization."""
    viz = get_object_or_404(SCOTUSMap, pk=pk)
    if not is_bot(request):
        viz.view_count = F('view_count') + 1
        viz.save()

    status = None
    if viz.deleted:
        status = 410  # Gone
    else:
        if viz.published is False and viz.user != request.user:
            # Not deleted, unpublished and not the owner
            status = 401  # Unauthorized

    return render_to_response(
        'visualization.html',
        {
            'viz': viz,
            'private': False,
        },
        status=status,
        RequestContext(request),
    )

def mapper_homepage(request):
    pass

@login_required
def new_visualization(request):
    pass

@login_required
def visualization_profile_page(request):
    """TODO: Check what the appropriate decorators are for this."""
    pass
