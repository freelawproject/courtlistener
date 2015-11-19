import json
import time

from django.contrib import messages

from cl.lib.bot_detector import is_bot
from cl.stats import tally_stat
from cl.visualizations.models import SCOTUSMap, JSONVersion
from cl.visualizations.forms import VizForm, VizEditForm, JSONEditForm
from cl.visualizations.utils import reverse_endpoints_if_needed, TooManyNodes
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.db.models import F
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.views.decorators.clickjacking import xframe_options_exempt

from rest_framework import status as statuses


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


@xframe_options_exempt
def view_embedded_visualization(request, pk):
    """Return the embedded visualization page.

    Exempts the default xframe options, and allows standard caching.
    """
    return render_visualization_page(request, pk, embed=True)


def view_visualization(request, pk, slug):
    """Return the visualization page.
    """
    return render_visualization_page(request, pk, embed=False)


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

            try:
                t1 = time.time()
                g = viz.build_nx_digraph(
                    parent_authority=end,
                    visited_nodes={},
                    good_nodes={},
                    max_hops=4,
                )
                t2 = time.time()
                viz.generation_time = t2 - t1
            except TooManyNodes, e:
                messages.add_message(
                    request,
                    messages.WARNING,
                    '<strong>Woah there, that network has too many nodes.'
                    '</strong> We were unable to create your visualization '
                    'because the finished product would contain more than 70 '
                    'nodes. We\'ve found that in practice, such networks are '
                    'difficult to read and take far too long for our servers '
                    'to build. Try building a smaller network.',
                )
                return render_to_response(
                    'new_visualization.html',
                    {'form': form, 'private': True},
                    RequestContext(request),
                )

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
        {'form': form, 'private': True},
        RequestContext(request),
    )

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


@login_required
def delete_visualization(request, pk):
    pass


def mapper_homepage(request):
    if not is_bot(request):
        tally_stat('search.visualization_scotus_homepage_loaded')

    return render_to_response(
        'visualization_home.html',
        {'private': True},
        RequestContext(request),
    )
