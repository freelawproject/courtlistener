from asgiref.sync import sync_to_async
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseServerError,
)
from django.shortcuts import aget_object_or_404, redirect
from django.template.response import TemplateResponse
from django.utils.datastructures import MultiValueDictKeyError
from django.views.decorators.http import require_http_methods

from cl.favorites.forms import NoteForm
from cl.favorites.models import DocketTag, Note, Prayer, UserTag
from cl.favorites.utils import (
    create_prayer,
    delete_prayer,
    get_existing_prayers_in_bulk,
    get_lifetime_prayer_stats,
    get_top_prayers,
    get_user_prayer_history,
    get_user_prayers,
    prayer_eligible,
)
from cl.lib.http import is_ajax
from cl.lib.view_utils import increment_view_count
from cl.search.models import RECAPDocument
from cl.users.models import UserProfile


async def get_note(request: HttpRequest) -> HttpResponse:
    audio_pk = request.POST.get("audio_id")
    cluster_pk = request.POST.get("cluster_id")
    docket_pk = request.POST.get("docket_id")
    recap_doc_pk = request.POST.get("recap_doc_id")
    user = await request.auser()
    if audio_pk and audio_pk != "undefined":
        try:
            note = await Note.objects.aget(audio_id=audio_pk, user=user)
        except ObjectDoesNotExist:
            note = Note()
    elif cluster_pk and cluster_pk != "undefined":
        try:
            note = await Note.objects.aget(cluster_id=cluster_pk, user=user)
        except ObjectDoesNotExist:
            note = Note()
    elif docket_pk and docket_pk != "undefined":
        try:
            note = await Note.objects.aget(docket_id=docket_pk, user=user)
        except ObjectDoesNotExist:
            note = Note()
    elif recap_doc_pk and recap_doc_pk != "undefined":
        try:
            note = await Note.objects.aget(
                recap_doc_id=recap_doc_pk, user=user
            )
        except ObjectDoesNotExist:
            note = Note()
    else:
        note = None
    return note


@login_required
async def save_or_update_note(request: HttpRequest) -> HttpResponse:
    """Uses ajax to save or update a note.

    Receives a request as an argument, and then uses that plus POST data to
    create or update a note in the database for a specific user. If the
    user already has a note for the document, it updates the note with the
    new information. If not, it creates a new note.
    """
    if is_ajax(request):
        note = await get_note(request)
        if note is None:
            return HttpResponseServerError(
                "Unknown document, audio, docket or recap document id."
            )

        f = NoteForm(request.POST, instance=note)
        if await sync_to_async(f.is_valid)():
            new_note = await sync_to_async(f.save)(commit=False)
            new_note.user = await request.auser()
            try:
                await sync_to_async(new_note.save)()
            except IntegrityError:
                # User already has this note.
                return HttpResponse("It worked")
        else:
            # Validation errors fail silently. Probably could be better.
            return HttpResponseServerError("Failure. Form invalid")

        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods={"POST"}, content="Not an ajax request."
        )


@login_required
async def delete_note(request: HttpRequest) -> HttpResponse:
    """Delete a user's note

    Deletes a note for a user using an ajax call and post data.
    """
    if is_ajax(request):
        note = await get_note(request)
        if note is None:
            return HttpResponseServerError(
                "Unknown document, audio, docket, or recap document id."
            )
        await note.adelete()

        try:
            if request.POST["message"] == "True":
                # used on the profile page. True is a string, not a bool.
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    "Your note was deleted successfully.",
                )
        except MultiValueDictKeyError:
            # This happens if message isn't set.
            pass

        return HttpResponse("It worked.")

    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request."
        )


async def view_tag(request, username, tag_name):
    tag = await aget_object_or_404(
        UserTag, name=tag_name, user__username=username
    )
    await increment_view_count(tag, request)

    if tag.published is False:
        if await User.objects.aget(pk=tag.user_id) != await request.auser():
            # They don't even get to see if it exists.
            raise Http404("This tag does not exist")

    # Calculate the total tag count (as we add more types of taggables, add
    # them here).
    enhanced_dockets = tag.dockets.all().order_by("date_filed")
    total_tag_count = await enhanced_dockets.acount()
    async for docket in enhanced_dockets:
        docket_tag = await DocketTag.objects.aget(docket=docket, tag=tag)
        docket.association_id = docket_tag.pk
    requested_user = await aget_object_or_404(User, username=username)
    is_page_owner = await request.auser() == requested_user

    return TemplateResponse(
        request,
        "tag.html",
        {
            "tag": tag,
            "dockets": enhanced_dockets,
            "total_tag_count": total_tag_count,
            "private": False,
            "is_page_owner": is_page_owner,
        },
    )


async def view_tags(request, username):
    """Show the user their tags if they're looking at their own, or show the
    public tags of somebody else.
    """
    requested_user = await aget_object_or_404(User, username=username)
    is_page_owner = await request.auser() == requested_user
    return TemplateResponse(
        request,
        "tag_list.html",
        {
            "requested_user": requested_user,
            "is_page_owner": is_page_owner,
            "private": False,
        },
    )


async def open_prayers(request: HttpRequest) -> HttpResponse:
    """Show the user top open prayer requests."""

    top_prayers = await get_top_prayers()

    page = request.GET.get("page", 1)

    @sync_to_async
    def paginate_open_prayers(top_prayers, prayer_page):
        paginator = Paginator(top_prayers, 25, orphans=10)
        try:
            return paginator.page(prayer_page)
        except PageNotAnInteger:
            return paginator.page(1)
        except EmptyPage:
            return paginator.page(paginator.num_pages)

    paginated_entries = await paginate_open_prayers(top_prayers, page)

    recap_documents = paginated_entries.object_list

    user = await request.auser()
    existing_prayers = {}
    if user.is_authenticated:
        # Check prayer existence in bulk.
        existing_prayers = await get_existing_prayers_in_bulk(
            user, recap_documents
        )

    # Merge counts and existing prayer status to RECAPDocuments.
    async for rd in recap_documents:
        rd.prayer_exists = existing_prayers.get(rd.id, False)

    granted_stats = await get_lifetime_prayer_stats(Prayer.GRANTED)
    waiting_stats = await get_lifetime_prayer_stats(Prayer.WAITING)

    context = {
        "top_prayers": paginated_entries,
        "private": False,
        "granted_stats": granted_stats,
        "waiting_stats": waiting_stats,
    }

    return TemplateResponse(request, "top_prayers.html", context)


@login_required
async def create_prayer_view(
    request: HttpRequest, recap_document: int
) -> HttpResponse:
    user = request.user
    is_htmx_request = request.META.get("HTTP_HX_REQUEST", False)
    regular_size = bool(request.POST.get("regular_size"))
    if not (await prayer_eligible(request.user))[0]:
        if is_htmx_request:
            return TemplateResponse(
                request,
                "includes/pray_and_pay_htmx/pray_button.html",
                {
                    "prayer_exists": False,
                    "document_id": recap_document,
                    "count": 0,
                    "daily_limit_reached": True,
                    "regular_size": regular_size,
                    "should_swap": True,
                },
            )
        return HttpResponseServerError(
            "User have reached your daily request limit"
        )

    recap_document = await RECAPDocument.objects.aget(id=recap_document)

    # Call the create_prayer async function
    await create_prayer(user, recap_document)
    if is_htmx_request:
        return TemplateResponse(
            request,
            "includes/pray_and_pay_htmx/pray_button.html",
            {
                "prayer_exists": True,
                "document_id": recap_document.pk,
                "count": 0,
                "daily_limit_reached": False,
                "regular_size": regular_size,
                "should_swap": True,
            },
        )
    return HttpResponse("It worked.")


@login_required
async def delete_prayer_view(
    request: HttpRequest, recap_document: int
) -> HttpResponse:
    user = request.user
    recap_document = await RECAPDocument.objects.aget(id=recap_document)

    # Call the delete_prayer async function
    await delete_prayer(user, recap_document)
    regular_size = bool(request.POST.get("regular_size"))
    source = request.POST.get("source", "")
    if request.META.get("HTTP_HX_REQUEST"):
        return TemplateResponse(
            request,
            "includes/pray_and_pay_htmx/pray_button.html",
            {
                "prayer_exists": False,
                "document_id": recap_document.pk,
                "count": 0,
                "regular_size": regular_size,
                "should_swap": True if source != "user_prayer_list" else False,
            },
            headers={"HX-Trigger": "prayersListChanged"},
        )
    return HttpResponse("It worked.")


async def user_prayers_view(
    request: HttpRequest, username: str
) -> HttpResponse:
    queryset = User.objects.prefetch_related("profile")
    requested_user = await aget_object_or_404(queryset, username=username)
    is_page_owner = await request.auser() == requested_user

    page_public = requested_user.profile.prayers_public

    if not (is_page_owner or page_public):
        return redirect("top_prayers")

    rd_with_prayers_waiting = await get_user_prayers(
        requested_user, Prayer.WAITING
    )

    user_history = await get_user_prayer_history(requested_user)

    _, num_remaining = await prayer_eligible(requested_user)

    waiting_page = request.GET.get("page", 1)

    @sync_to_async
    def paginate_waiting_prayers(waiting_prayers, prayer_page):
        paginator = Paginator(waiting_prayers, 25, orphans=10)
        try:
            return paginator.page(prayer_page)
        except PageNotAnInteger:
            return paginator.page(1)
        except EmptyPage:
            return paginator.page(paginator.num_pages)

    paginated_entries_waiting = await paginate_waiting_prayers(
        rd_with_prayers_waiting, waiting_page
    )

    context = {
        "rd_with_prayers_waiting": paginated_entries_waiting,
        "requested_user": requested_user,
        "is_page_owner": is_page_owner,
        "user_history": user_history,
        "num_remaining": num_remaining,
        "page_public": page_public,
        "private": False,
    }

    return TemplateResponse(request, "user_prayers_pending.html", context)


async def user_prayers_view_granted(
    request: HttpRequest, username: str
) -> HttpResponse:
    requested_user = await aget_object_or_404(User, username=username)
    is_page_owner = await request.auser() == requested_user

    # unlike pending prayers page, this should always remain private, per the current design
    if not is_page_owner:
        return redirect("top_prayers")

    rd_with_prayers_granted = await get_user_prayers(
        requested_user, Prayer.GRANTED
    )

    user_history = await get_user_prayer_history(requested_user)

    _, num_remaining = await prayer_eligible(requested_user)

    granted_page = request.GET.get("page", 1)

    @sync_to_async
    def paginate_granted_prayers(granted_page, prayer_page):
        paginator = Paginator(granted_page, 25, orphans=10)
        try:
            return paginator.page(prayer_page)
        except PageNotAnInteger:
            return paginator.page(1)
        except EmptyPage:
            return paginator.page(paginator.num_pages)

    paginated_entries_granted = await paginate_granted_prayers(
        rd_with_prayers_granted, granted_page
    )

    context = {
        "rd_with_prayers_granted": paginated_entries_granted,
        "requested_user": requested_user,
        "is_page_owner": is_page_owner,
        "user_history": user_history,
        "num_remaining": num_remaining,
        "private": False,
    }

    return TemplateResponse(request, "user_prayers_granted.html", context)


@login_required
@require_http_methods(["POST"])
def toggle_prayer_public(
    request: HttpRequest,
) -> HttpResponse:
    """Toggle the user's setting to make pending prayers public"""
    user = request.user
    next_toggle_status = not bool(request.POST.get("current_toggle_status"))
    UserProfile.objects.filter(user=user).update(
        prayers_public=next_toggle_status
    )
    return TemplateResponse(
        request,
        "includes/public_prayers_switch.html",
        {"page_public": next_toggle_status},
    )
