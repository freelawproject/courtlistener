from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import FavoriteForm
from cl.favorites.models import Favorite
from cl.lib import search_utils
from cl.lib.string_utils import trunc


@never_cache
def view_audio_file(request, pk, _):
    """Using the ID, return the oral argument page.

    We also test if the item is a favorite and send data as such.
    """
    af = get_object_or_404(Audio, pk=pk)
    title = trunc(af.case_name, 100)
    get_string = search_utils.make_get_string(request)

    try:
        fave = Favorite.objects.get(audio_id=af.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(
            initial={
                "audio_id": af.pk,
                "name": trunc(best_case_name(af.docket), 100, ellipsis="..."),
            }
        )
    else:
        favorite_form = FavoriteForm(instance=fave)

    return render(
        request,
        "oral_argument.html",
        {
            "title": title,
            "af": af,
            "favorite_form": favorite_form,
            "get_string": get_string,
            "private": af.blocked,
        },
    )
