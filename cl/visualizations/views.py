import json
import time

from django.conf import settings
from django.contrib import messages

from cl.lib.bot_detector import is_bot
from cl.stats import tally_stat
from cl.visualizations.models import SCOTUSMap, JSONVersion
from cl.visualizations.forms import VizForm, VizEditForm, JSONEditForm
from cl.visualizations.utils import reverse_endpoints_if_needed, TooManyNodes
from django.contrib.auth.decorators import login_required, permission_required
from django.core.urlresolvers import reverse
from django.db.models import F
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import status as statuses


@permission_required('visualizations.has_beta_access')
def render_visualization_page(request, pk, embed):
    viz = get_object_or_404(SCOTUSMap, pk=pk)

    if not is_bot(request):
        cached_value = viz.view_count
        viz.view_count = F('view_count') + 1
        viz.save()
        # To get the new value, you either need to get the item from the DB a
        # second time, or just manipulate it manually....
        viz.view_count = cached_value + 1

    status = None
    if viz.deleted:
        status = statuses.HTTP_410_GONE
    else:
        if viz.published is False and viz.user != request.user:
            # Not deleted, unpublished and not the owner
            status = statuses.HTTP_401_UNAUTHORIZED

    if embed:
        template = 'visualization_embedded.html'
    else:
        template = 'visualization.html'
    return render_to_response(
        template,
        {'viz': viz, 'private': True},
        RequestContext(request),
        status=status,
    )


@permission_required('visualizations.has_beta_access')
@xframe_options_exempt
def view_embedded_visualization(request, pk):
    """Return the embedded visualization page.

    Exempts the default xframe options, and allows standard caching.
    """
    return render_visualization_page(request, pk, embed=True)


@permission_required('visualizations.has_beta_access')
def view_visualization(request, pk, slug):
    """Return the visualization page.
    """
    return render_visualization_page(request, pk, embed=False)


def make_viz_msg(key, request):
    if key == 'too_many_nodes':
        messages.add_message(
            request,
            messages.WARNING,
            '<strong>That network has too many nodes.</strong> We '
            'were unable to create your visualization because the '
            'finished product would contain too  many nodes. '
            'We\'ve found that in practice, such networks are '
            'difficult to read and take far too long for our '
            'servers to create. Try building a smaller network by '
            'selecting different cases.',
        )
    elif key == 'fewer_hops_delivered':
        messages.add_message(
            request,
            messages.SUCCESS,
            "We were unable to build your network with three "
            "degrees of separation because it grew too large. "
            "The network below was built with two degrees of "
            "separation."
        )


@permission_required('visualizations.has_beta_access')
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
                notes=cd['notes'],
            )

            build_kwargs = {
                'parent_authority': end,
                'visited_nodes': {},
                'good_nodes': {},
                'max_hops': 3,
            }
            t1 = time.time()
            try:
                g = viz.build_nx_digraph(**build_kwargs)
            except TooManyNodes:
                try:
                    # Try with fewer hops.
                    build_kwargs['max_hops'] = 2
                    g = viz.build_nx_digraph(**build_kwargs)
                    make_viz_msg('fewer_hops_delivered', request)
                except TooManyNodes:
                    # Still too many hops. Abort.
                    tally_stat('visualization.too_many_nodes_failure')
                    make_viz_msg('too_many_nodes', request)
                    return render_to_response(
                        'new_visualization.html',
                        {'form': form, 'private': True},
                        RequestContext(request),
                    )
            t2 = time.time()
            viz.generation_time = t2 - t1

            viz.save()
            viz.add_clusters(g)
            j = viz.to_json(g)
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
        {
            'form': form,
            'SCDB_LATEST_CASE': settings.SCDB_LATEST_CASE.isoformat(),
            'private': True
        },
        RequestContext(request),
    )


@permission_required('visualizations.has_beta_access')
@login_required
def edit_visualization(request, pk):
    # This could apparently also be done with formsets? But they seem awful.
    viz = get_object_or_404(SCOTUSMap, pk=pk, user=request.user)
    if request.method == 'POST':
        form_viz = VizEditForm(request.POST, instance=viz)
        form_json = JSONEditForm(request.POST)
        if form_viz.is_valid() and form_json.is_valid():
            cd_viz = form_viz.cleaned_data
            cd_json = form_json.cleaned_data

            viz.title = cd_viz['title']
            viz.notes = cd_viz['notes']
            viz.published = cd_viz['published']
            viz.save()

            if json.loads(viz.json) != json.loads(cd_json['json_data']):
                # Save a new version of the JSON
                jv = JSONVersion(map=viz, json_data=cd_json['json_data'])
                jv.save()

            return HttpResponseRedirect(reverse(
                'view_visualization',
                kwargs={'pk': viz.pk, 'slug': viz.slug}
            ))
    else:
        form_viz = VizEditForm(instance=viz)
        form_json = JSONEditForm(instance=viz.json_versions.all()[0])
    return render_to_response(
        'edit_visualization.html',
        {'form_viz': form_viz,
         'form_json': form_json,
         'private': True},
        RequestContext(request),
    )


@permission_required('visualizations.has_beta_access')
@login_required
def delete_visualization(request, pk):
    pass


@permission_required('visualizations.has_beta_access')
def mapper_homepage(request):
    if not is_bot(request):
        tally_stat('visualization.scotus_homepage_loaded')

    return render_to_response(
        'visualization_home.html',
        {'private': True},
        RequestContext(request),
    )
