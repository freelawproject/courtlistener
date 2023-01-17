from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import NoteForm
from cl.favorites.models import Note
from cl.lib import search_utils
from cl.lib.string_utils import trunc


@never_cache
def view_audio_file(request, pk, _):
    """Using the ID, return the oral argument page.

    We also test if the item is a note and send data as such.
    """
    af = get_object_or_404(Audio, pk=pk)
    title = trunc(af.case_name, 100)
    get_string = search_utils.make_get_string(request)

    try:
        note = Note.objects.get(audio_id=af.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not note or anonymous user
        note_form = NoteForm(
            initial={
                "audio_id": af.pk,
                "name": trunc(best_case_name(af.docket), 100, ellipsis="..."),
            }
        )
    else:
        note_form = NoteForm(instance=note)

    return render(
        request,
        "oral_argument.html",
        {
            "title": title,
            "af": af,
            "note_form": note_form,
            "get_string": get_string,
            "private": af.blocked,
        },
    )
