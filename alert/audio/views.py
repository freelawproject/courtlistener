from alert.audio.models import Audio
from alert.favorites.forms import FavoriteForm
from alert.favorites.models import Favorite
from alert.lib import search_utils
from alert.lib.string_utils import trunc
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.views.decorators.cache import never_cache


@never_cache
def view_audio_file(request, pk, _):
    """Using the ID, return the oral argument page.

    We also test if the item is a favorite and send data as such.
    """
    af = get_object_or_404(Audio, pk=pk)
    title = "Oral Argument for " + trunc(af.case_name, 100)
    get_string = search_utils.make_get_string(request)

    try:
        fave = Favorite.objects.get(audio_id=af.pk, users__user=request.user)
        favorite_form = FavoriteForm(instance=fave)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(
            initial={
                'audio_id': af.pk,
                'name': trunc(af.docket.case_name, 100, ellipsis='...'),
            }
        )

    return render_to_response(
        'audio/oral_argument.html',
        {'title': title,
         'af': af,
         'favorite_form': favorite_form,
         'get_string': get_string,
         'private': af.blocked,
         },
        RequestContext(request)
    )
