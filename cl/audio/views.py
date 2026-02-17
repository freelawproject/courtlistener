from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.shortcuts import aget_object_or_404  # type: ignore[attr-defined]
from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache

from cl.audio.models import Audio, AudioTranscriptionMetadata
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import NoteForm
from cl.favorites.models import Note
from cl.lib import search_utils
from cl.lib.string_utils import trunc
from cl.search.models import Docket


@never_cache
async def view_audio_file(
    request: HttpRequest, pk: int, _: str
) -> HttpResponse:
    """Using the ID, return the oral argument page.

    We also test if the item has a note and send data as such.
    """
    af = await aget_object_or_404(Audio, pk=pk)
    title = trunc(af.case_name, 100)
    get_string = search_utils.make_get_string(request)

    # --- Fetch transcript metadata ---
    segments_list = []
    # Get the latest metadata. There can be many metadata rows for a single
    # audio, if the transcription failed as hallucinated and was retried
    metadata_qs = AudioTranscriptionMetadata.objects.filter(audio=af).order_by(
        "-id"
    )
    metadata_obj = await metadata_qs.afirst()

    if metadata_obj:
        # Extract the 'segments' list instead of 'words'
        segments_list = metadata_obj.metadata.get("segments", [])
        # Validate if segments_list is actually a list
        if not isinstance(segments_list, list):
            segments_list = []  # Reset to empty list if format is unexpected

    # --- End transcript metadata fetch ---

    try:
        note = await Note.objects.aget(
            audio_id=af.pk,
            user=await request.auser(),  # type: ignore[attr-defined]
        )
    except (ObjectDoesNotExist, TypeError):
        # Not note or anonymous user
        docket = await Docket.objects.aget(id=af.docket_id)
        note_form = NoteForm(
            initial={
                "audio_id": af.pk,
                "name": trunc(best_case_name(docket), 100, ellipsis="..."),
            }
        )
    else:
        note_form = NoteForm(instance=note)

    return TemplateResponse(
        request,
        "oral_argument.html",
        {
            "title": title,
            "af": af,
            "note_form": note_form,
            "get_string": get_string,
            "private": af.blocked,
            "transcript_segments_data": segments_list,
        },
    )
