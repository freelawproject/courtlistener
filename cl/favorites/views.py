from asgiref.sync import sync_to_async
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
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

from cl.favorites.forms import NoteForm
from cl.favorites.models import DocketTag, Note, UserTag
from cl.favorites.utils import (
    create_prayer,
    delete_prayer,
    get_top_prayers,
    get_user_prayers,
    get_user_prayer_history,
    prayer_eligible,
)
from cl.lib.decorators import cache_page_ignore_params
from cl.lib.http import is_ajax
from cl.lib.view_utils import increment_view_count
from cl.search.models import RECAPDocument


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


@cache_page_ignore_params(30)  # Cache for 30 seconds
async def open_prayers(request: HttpRequest) -> HttpResponse:
    """Show the user top open prayer requests."""

    top_prayers = await get_top_prayers()

    context = {
        "top_prayers": top_prayers,
        "private": False,
    }

    return TemplateResponse(request, "top_prayers.html", context)


@login_required
async def create_prayer_view(
    request: HttpRequest, recap_document: int
) -> HttpResponse:
    user = request.user
    is_htmx_request = request.META.get("HTTP_HX_REQUEST", False)
    if not await prayer_eligible(request.user):
        if is_htmx_request:
            return TemplateResponse(
                request,
                "includes/pray_and_pay_htmx/pray_button.html",
                {
                    "prayer_exists": False,
                    "document_id": recap_document,
                    "count": 0,
                    "daily_limit_reached": True,
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

    if request.META.get("HTTP_HX_REQUEST"):
        return TemplateResponse(
            request,
            "includes/pray_and_pay_htmx/pray_button.html",
            {
                "prayer_exists": False,
                "document_id": recap_document.pk,
                "count": 0,
            },
        )
    return HttpResponse("It worked.")


async def user_prayers_view(
    request: HttpRequest, username: str
) -> HttpResponse:
    requested_user = await aget_object_or_404(User, username=username)
    is_page_owner = await request.auser() == requested_user

    # this is a temporary restriction for the MVP. The intention is to eventually treat like tags.
    if not is_page_owner:
        return redirect("top_prayers")

    prayers = await get_user_prayers(requested_user)

    count, total_cost = await get_user_prayer_history(requested_user)

    context = {
        "prayers": prayers,
        "requested_user": requested_user,
        "is_page_owner": is_page_owner,
        "count": count,
        "total_cost": total_cost,
        "private": False,
    }

    # I want this to include the following things - show date fulfilled, link to file, etc. What else?
    return TemplateResponse(request, "user_prayers.html", context)
