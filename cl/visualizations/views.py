from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.urls import reverse
from django.db.models import Count
from django.http import (
    HttpResponseRedirect,
    HttpResponse,
    HttpResponseNotAllowed,
)
from django.shortcuts import render, get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status as statuses

from cl.lib.bot_detector import is_bot
from cl.lib.view_utils import increment_view_count
from cl.stats.utils import tally_stat
from cl.visualizations.forms import VizForm, VizEditForm
from cl.visualizations.models import SCOTUSMap, Referer
from cl.visualizations.tasks import get_title
from cl.visualizations.utils import message_dict, build_visualization
from cl.visualizations.network_utils import reverse_endpoints_if_needed


def render_visualization_page(request, pk, embed):
    viz = get_object_or_404(SCOTUSMap, pk=pk)
    increment_view_count(viz, request)

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
            referer_url = request.META.get("HTTP_REFERER")
            if referer_url is not None:
                referer, created = Referer.objects.get_or_create(
                    url=referer_url, map_id=viz.pk,
                )
                if created:
                    # Spawn a task to try to get the title of the page.
                    get_title.delay(referer.pk)
        template = "visualization_embedded.html"
    else:
        template = "visualization.html"
    return render(
        request, template, {"viz": viz, "private": False}, status=status
    )


@xframe_options_exempt
def view_embedded_visualization(request, pk):
    """Return the embedded network page.

    Exempts the default xframe options, and allows standard caching.
    """
    return render_visualization_page(request, pk, embed=True)


@never_cache
def view_visualization(request, pk, slug):
    """Return the network page.
    """
    return render_visualization_page(request, pk, embed=False)


@login_required
@never_cache
def new_visualization(request):
    demo_viz = (
        SCOTUSMap.objects.filter(published=True, deleted=False,)
        .annotate(Count("clusters"),)
        .filter(
            # Ensures that we only show good stuff on homepage
            clusters__count__gt=5,
            clusters__count__lt=15,
        )
        .order_by("-date_published", "-date_modified", "-date_created",)[:1]
    )

    context = {
        "SCDB_LATEST_CASE": settings.SCDB_LATEST_CASE.isoformat(),
        "demo_viz": demo_viz,
        "private": True,
    }
    if request.method == "POST":
        form = VizForm(request.POST)
        context["form"] = form
        if form.is_valid():
            # Process the data in form.cleaned_data
            cd = form.cleaned_data
            start, end = reverse_endpoints_if_needed(
                cd["cluster_start"], cd["cluster_end"]
            )

            viz = SCOTUSMap(
                user=request.user,
                cluster_start=start,
                cluster_end=end,
                title=cd["title"],
                notes=cd["notes"],
            )
            status, viz = build_visualization(viz)
            if status == "too_many_nodes":
                msg = message_dict[status]
                messages.add_message(request, msg["level"], msg["message"])
                return render(request, "new_visualization.html", context)
            elif status == "too_few_nodes":
                msg = message_dict[status]
                messages.add_message(request, msg["level"], msg["message"])
                return render(
                    request,
                    "new_visualization.html",
                    {"form": form, "private": True},
                )

            return HttpResponseRedirect(
                reverse(
                    "view_visualization",
                    kwargs={"pk": viz.pk, "slug": viz.slug},
                )
            )
    else:
        context["form"] = VizForm()
    return render(request, "new_visualization.html", context)


@login_required
def edit_visualization(request, pk):
    # This could apparently also be done with formsets? But they seem awful.
    viz = get_object_or_404(SCOTUSMap, pk=pk, user=request.user)
    if request.method == "POST":
        form_viz = VizEditForm(request.POST, instance=viz)
        if form_viz.is_valid():
            cd_viz = form_viz.cleaned_data

            viz.title = cd_viz["title"]
            viz.notes = cd_viz["notes"]
            viz.published = cd_viz["published"]
            viz.save()

            return HttpResponseRedirect(
                reverse(
                    "view_visualization",
                    kwargs={"pk": viz.pk, "slug": viz.slug},
                )
            )
    else:
        form_viz = VizEditForm(instance=viz)
    return render(
        request,
        "edit_visualization.html",
        {"form_viz": form_viz, "private": True},
    )


@ensure_csrf_cookie
@login_required
def delete_visualization(request):
    if request.is_ajax():
        v = SCOTUSMap.objects.get(pk=request.POST.get("pk"), user=request.user)
        v.deleted = True
        v.save()
        return HttpResponse("It worked.")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request",
        )


@ensure_csrf_cookie
@login_required
def restore_visualization(request):
    if request.is_ajax():
        v = SCOTUSMap.objects.get(pk=request.POST.get("pk"), user=request.user)
        v.deleted = False
        v.date_deleted = None
        v.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request",
        )


@ensure_csrf_cookie
@login_required
def share_visualization(request):
    if request.is_ajax():
        v = SCOTUSMap.objects.get(pk=request.POST.get("pk"), user=request.user)
        v.published = True
        v.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request",
        )


@ensure_csrf_cookie
@login_required
def privatize_visualization(request):
    if request.is_ajax():
        v = SCOTUSMap.objects.get(pk=request.POST.get("pk"), user=request.user)
        v.published = False
        v.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request",
        )


def mapper_homepage(request):
    if not is_bot(request):
        tally_stat("visualization.scotus_homepage_loaded")

    visualizations = (
        SCOTUSMap.objects.filter(published=True, deleted=False,)
        .annotate(Count("clusters"),)
        .filter(
            # Ensures that we only show good stuff on homepage
            clusters__count__gt=10,
        )
        .order_by("-date_published", "-date_modified", "-date_created",)[:2]
    )

    return render(
        request,
        "visualization_home.html",
        {"visualizations": visualizations, "private": False,},
    )


@never_cache
def gallery(request):
    visualizations = (
        SCOTUSMap.objects.filter(published=True, deleted=False,)
        .annotate(Count("clusters"),)
        .order_by("-date_published", "-date_modified", "-date_created",)
    )
    paginator = Paginator(visualizations, 5)
    page = request.GET.get("page", 1)
    try:
        paged_vizes = paginator.page(page)
    except PageNotAnInteger:
        paged_vizes = paginator.page(1)
    except EmptyPage:
        paged_vizes = paginator.page(paginator.num_pages)
    return render(
        request, "gallery.html", {"results": paged_vizes, "private": False,}
    )
