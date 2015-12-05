import time

from cl.lib.bot_detector import is_bot
from cl.stats import tally_stat
from cl.visualizations.models import SCOTUSMap, JSONVersion, Referer
from cl.visualizations.forms import VizForm, VizEditForm
from cl.visualizations.tasks import get_title
from cl.visualizations.utils import (
    reverse_endpoints_if_needed, TooManyNodes, message_dict
)

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import F
from django.http import (
    HttpResponseRedirect, HttpResponse, HttpResponseNotAllowed
)
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
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
            # Not deleted, private and not the owner
            status = statuses.HTTP_401_UNAUTHORIZED

    if embed:
        if all([viz.published is True, viz.deleted is False]):
            # Log the referer if it's set, and the item is live.
            referer_url = request.META.get('HTTP_REFERER')
            if referer_url is not None:
                referer, created = Referer.objects.get_or_create(
                    url=referer_url, map_id=viz.pk,
                )
                if created:
                    # Spawn a task to try to get the title of the page.
                    get_title.delay(referer.pk)
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
    """Return the embedded network page.

    Exempts the default xframe options, and allows standard caching.
    """
    return render_visualization_page(request, pk, embed=True)


@permission_required('visualizations.has_beta_access')
@never_cache
def view_visualization(request, pk, slug):
    """Return the network page.
    """
    return render_visualization_page(request, pk, embed=False)


@permission_required('visualizations.has_beta_access')
@login_required
@never_cache
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
                    msg = message_dict['fewer_hops_delivered']
                    messages.add_message(request, msg['level'], msg['message'])
                except TooManyNodes:
                    # Still too many hops. Abort.
                    tally_stat('visualization.too_many_nodes_failure')
                    msg = message_dict['too_many_nodes']
                    messages.add_message(request, msg['level'], msg['message'])
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
        if form_viz.is_valid():
            cd_viz = form_viz.cleaned_data

            viz.title = cd_viz['title']
            viz.notes = cd_viz['notes']
            viz.published = cd_viz['published']
            viz.save()

            return HttpResponseRedirect(reverse(
                'view_visualization',
                kwargs={'pk': viz.pk, 'slug': viz.slug}
            ))
    else:
        form_viz = VizEditForm(instance=viz)
    return render_to_response(
        'edit_visualization.html',
        {'form_viz': form_viz,
         'private': True},
        RequestContext(request),
    )


@ensure_csrf_cookie
@permission_required('visualizations.has_beta_access')
@login_required
def delete_visualization(request):
    if request.is_ajax():
        v = SCOTUSMap.objects.get(pk=request.POST.get('pk'), user=request.user)
        v.deleted = True
        v.save()
        return HttpResponse("It worked.")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=['POST'],
            content="Not an ajax request",
        )


@ensure_csrf_cookie
@permission_required('visualizations.has_beta_access')
@login_required
def restore_visualization(request):
    if request.is_ajax():
        v = SCOTUSMap.objects.get(pk=request.POST.get('pk'), user=request.user)
        v.deleted = False
        v.date_deleted = None
        v.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=['POST'],
            content="Not an ajax request",
        )

@ensure_csrf_cookie
@permission_required('visualizations.has_beta_access')
@login_required
def share_visualization(request):
    if request.is_ajax():
        v = SCOTUSMap.objects.get(pk=request.POST.get('pk'), user=request.user)
        v.published = True
        v.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=['POST'],
            content="Not an ajax request",
        )


@ensure_csrf_cookie
@permission_required('visualizations.has_beta_access')
@login_required
def privatize_visualization(request):
    if request.is_ajax():
        v = SCOTUSMap.objects.get(pk=request.POST.get('pk'), user=request.user)
        v.published = False
        v.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
                permitted_methods=['POST'],
                content="Not an ajax request",
        )


@permission_required('visualizations.has_beta_access')
def mapper_homepage(request):
    if not is_bot(request):
        tally_stat('visualization.scotus_homepage_loaded')

    return render_to_response(
        'visualization_home.html',
        {'private': True},
        RequestContext(request),
    )


@permission_required('visualization.has_beta_access')
def gallery(request):
    visualizations = SCOTUSMap.objects.filter(
        published=True,
        deleted=False,
    ).order_by(
        '-date_published',
        '-date_modified',
        '-date_created',
    )
    paginator = Paginator(visualizations, 20)
    page = request.GET.get('page', 1)
    try:
        paged_vizes = paginator.page(page)
    except PageNotAnInteger:
        paged_vizes = paginator.page(1)
    except EmptyPage:
        paged_vizes = paginator.page(paginator.num_pages)
    return render_to_response(
        'gallery.html',
        {
            'results': paged_vizes,
            'private': False,
        },
        RequestContext(request)
    )

