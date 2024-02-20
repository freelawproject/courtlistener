import datetime

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from django.shortcuts import aget_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status as statuses

from cl.lib.bot_detector import is_bot
from cl.lib.http import is_ajax
from cl.lib.view_utils import increment_view_count
from cl.stats.utils import tally_stat
from cl.visualizations.forms import VizEditForm, VizForm
from cl.visualizations.models import Referer, SCOTUSMap
from cl.visualizations.network_utils import reverse_endpoints_if_needed
from cl.visualizations.tasks import get_title
from cl.visualizations.utils import build_visualization, message_dict

# SCOTUS cases after this date aren't expected to have SCDB data.
SCDB_LATEST_CASE = datetime.datetime(2019, 6, 27)


async def render_visualization_page(
    request: HttpRequest,
    pk: int,
    embed: bool,
) -> HttpResponse:
    viz = await aget_object_or_404(SCOTUSMap, pk=pk)
    await increment_view_count(viz, request)

    status = None
    if viz.deleted:
        status = statuses.HTTP_410_GONE
        title = "Visualization Deleted by Creator"
    else:
        user = await User.objects.aget(pk=viz.user_id)
        if viz.published is False and user != await request.auser():
            # Not deleted, private and not the owner
            status = statuses.HTTP_401_UNAUTHORIZED
            title = "Private Visualization"
        else:
            title = f"Network Graph of {viz.title}"

    if embed:
        if all([viz.published is True, viz.deleted is False]):
            # Log the referer if it's set, and the item is live.
            referer_url = request.META.get("HTTP_REFERER")
            if referer_url is not None:
                referer, created = await Referer.objects.aget_or_create(
                    url=referer_url, map_id=viz.pk
                )
                if created:
                    # Spawn a task to try to get the title of the page.
                    get_title.delay(referer.pk)
        template = "visualization_embedded.html"
    else:
        template = "visualization.html"
    return TemplateResponse(
        request,
        template,
        {"viz": viz, "title": title, "private": False},
        status=status,
    )


@xframe_options_exempt
async def view_embedded_visualization(
    request: HttpRequest, pk: int
) -> HttpResponse:
    """Return the embedded network page.

    Exempts the default xframe options, and allows standard caching.
    """
    return await render_visualization_page(request, pk, embed=True)


@never_cache
async def view_visualization(
    request: HttpRequest,
    pk: int,
    slug: str,
) -> HttpResponse:
    """Return the network page."""
    return await render_visualization_page(request, pk, embed=False)


@sync_to_async
@login_required
@async_to_sync
@never_cache
async def new_visualization(request: HttpRequest) -> HttpResponse:
    demo_viz = (
        SCOTUSMap.objects.filter(published=True, deleted=False)
        .annotate(Count("clusters"))
        .filter(
            # Ensures that we only show good stuff on homepage
            clusters__count__gt=5,
            clusters__count__lt=15,
        )
        .order_by("-date_published", "-date_modified", "-date_created")[:1]
    )

    context = {
        "SCDB_LATEST_CASE": SCDB_LATEST_CASE.isoformat(),
        "demo_viz": demo_viz,
        "private": True,
    }
    if request.method == "POST":
        form = VizForm(request.POST)
        context["form"] = form
        if await sync_to_async(form.is_valid)():
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
            status, viz = await build_visualization(viz)
            if status == "too_many_nodes":
                msg = message_dict[status]
                messages.add_message(request, msg["level"], msg["message"])
                return TemplateResponse(
                    request, "new_visualization.html", context
                )
            elif status == "too_few_nodes":
                msg = message_dict[status]
                messages.add_message(request, msg["level"], msg["message"])
                return TemplateResponse(
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
    return TemplateResponse(request, "new_visualization.html", context)


@sync_to_async
@login_required
@async_to_sync
async def edit_visualization(request: HttpRequest, pk: int) -> HttpResponse:
    # This could apparently also be done with formsets? But they seem awful.
    viz = await aget_object_or_404(SCOTUSMap, pk=pk, user=request.user)
    if request.method == "POST":
        form_viz = VizEditForm(request.POST, instance=viz)
        if await sync_to_async(form_viz.is_valid)():
            cd_viz = form_viz.cleaned_data

            viz.title = cd_viz["title"]
            viz.notes = cd_viz["notes"]
            viz.published = cd_viz["published"]
            await viz.asave()

            return HttpResponseRedirect(
                reverse(
                    "view_visualization",
                    kwargs={"pk": viz.pk, "slug": viz.slug},
                )
            )
    else:
        form_viz = VizEditForm(instance=viz)
    return TemplateResponse(
        request,
        "edit_visualization.html",
        {"form_viz": form_viz, "private": True},
    )


@ensure_csrf_cookie
@sync_to_async
@login_required
@async_to_sync
async def delete_visualization(request: HttpRequest) -> HttpResponse:
    if is_ajax(request):
        v = await SCOTUSMap.objects.aget(
            pk=request.POST.get("pk"), user=request.user
        )
        v.deleted = True
        await v.asave()
        return HttpResponse("It worked.")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request"
        )


@ensure_csrf_cookie
@sync_to_async
@login_required
@async_to_sync
async def restore_visualization(request: HttpRequest) -> HttpResponse:
    if is_ajax(request):
        v = await SCOTUSMap.objects.aget(
            pk=request.POST.get("pk"), user=request.user
        )
        v.deleted = False
        v.date_deleted = None
        await v.asave()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request"
        )


@ensure_csrf_cookie
@sync_to_async
@login_required
@async_to_sync
async def share_visualization(request: HttpRequest) -> HttpResponse:
    if is_ajax(request):
        v = await SCOTUSMap.objects.aget(
            pk=request.POST.get("pk"), user=request.user
        )
        v.published = True
        await v.asave()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request"
        )


@ensure_csrf_cookie
@sync_to_async
@login_required
@async_to_sync
async def privatize_visualization(request: HttpRequest) -> HttpResponse:
    if is_ajax(request):
        v = await SCOTUSMap.objects.aget(
            pk=request.POST.get("pk"), user=request.user
        )
        v.published = False
        await v.asave()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request"
        )


async def mapper_homepage(request: HttpRequest) -> HttpResponse:
    if not is_bot(request):
        await tally_stat("visualization.scotus_homepage_loaded")

    visualizations = (
        SCOTUSMap.objects.filter(published=True, deleted=False)
        .annotate(Count("clusters"))
        .filter(
            # Ensures that we only show good stuff on homepage
            clusters__count__gt=10,
        )
        .order_by("-date_published", "-date_modified", "-date_created")[:2]
    )

    return TemplateResponse(
        request,
        "visualization_home.html",
        {"visualizations": visualizations, "private": False},
    )


@never_cache
async def gallery(request: HttpRequest) -> HttpResponse:
    visualizations = (
        SCOTUSMap.objects.filter(published=True, deleted=False)
        .annotate(Count("clusters"))
        .order_by("-date_published", "-date_modified", "-date_created")
    )
    paginator = Paginator(visualizations, 5)
    page = request.GET.get("page", 1)
    try:
        paged_vizes = await sync_to_async(paginator.page)(page)
    except PageNotAnInteger:
        paged_vizes = await sync_to_async(paginator.page)(1)
    except EmptyPage:
        paged_vizes = await sync_to_async(paginator.page)(paginator.num_pages)
    return TemplateResponse(
        request,
        "gallery.html",
        {"results": paged_vizes, "private": False},
    )
