from cl.lib.bot_detector import is_bot
from cl.visualizations.models import SCOTUSMap, JSONVersion
from cl.visualizations.forms import VizForm
from cl.visualizations.utils import reverse_endpoints_if_needed

from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.db.models import F
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext


def view_visualization(request, pk, slug):
    """A simple page for viewing a visualization."""
    viz = get_object_or_404(SCOTUSMap, pk=pk)

    if not is_bot(request):
        cached_value = viz.view_count
        viz.view_count = F('view_count') + 1
        viz.save()
        # To get the new value, you either need to get the item from the DB a
        # second time, or just manipuate it manually....
        viz.view_count = cached_value + 1

    status = None
    if viz.deleted:
        status = 410  # Gone
    else:
        if viz.published is False and viz.user != request.user:
            # Not deleted, unpublished and not the owner
            status = 401  # Unauthorized

    return render_to_response(
        'visualization.html',
        {'viz': viz, 'private': False},
        RequestContext(request),
        status=status,
    )


@login_required
def new_visualization(request):
    if request.method == 'POST':
        form = VizForm(request.POST)
        if form.is_valid():
            # Process the data in form.cleaned_data
            cd = form.cleaned_data
            start, end = reverse_endpoints_if_needed(cd['cluster_start'],
                                                     cd['cluster_end'])

            viz = SCOTUSMap(
                user=request.user,
                cluster_start=start,
                cluster_end=end,
                title=cd['title'],
                subtitle=cd['subtitle'],
                notes=cd['notes'],
            )
            viz.save()
            viz.add_clusters()
            j = viz.to_json()
            jv = JSONVersion(map=viz, json_data=j)
            jv.save()

            return HttpResponseRedirect(reverse(
                'view_visualization',
                kwargs={'pk': viz.pk, 'slug': viz.slug}
            ))
    else:
        form = VizForm()
    return render_to_response(
        'new_visualization.html',
        {'form': form, 'private': False},
        RequestContext(request),
    )

@login_required
def edit_visualization(request, pk):
    pass


@login_required
def delete_visualization(request, pk):
    pass


def mapper_homepage(request):
    """TODO: Make this page"""
    pass
