from cl.audio.models import Audio
from cl.favorites.forms import FavoriteForm
from cl.favorites.models import Favorite
from cl.search.models import OpinionCluster

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import (
    HttpResponse, HttpResponseServerError, HttpResponseNotAllowed,
)
from django.utils.datastructures import MultiValueDictKeyError


def get_favorite(request):
    audio_pk = request.POST.get('audio_id')
    cluster_pk = request.POST.get('cluster_id')
    if audio_pk and audio_pk != 'undefined':
        af = Audio.objects.get(pk=audio_pk)
        try:
            fave = Favorite.objects.get(
                audio_id=af,
                user=request.user
            )
        except ObjectDoesNotExist:
            fave = Favorite()
    elif cluster_pk and cluster_pk != 'undefined':
        cluster = OpinionCluster.objects.get(pk=cluster_pk)
        try:
            fave = Favorite.objects.get(
                cluster_id=cluster,
                user=request.user
            )
        except ObjectDoesNotExist:
            fave = Favorite()
    else:
        fave = None
    return fave


@login_required
def save_or_update_favorite(request):
    """Uses ajax to save or update a favorite.

    Receives a request as an argument, and then uses that plus POST data to
    create or update a favorite in the database for a specific user. If the
    user already has the document favorited, it updates the favorite with the
    new information. If not, it creates a new favorite.
    """
    if request.is_ajax():
        fave = get_favorite(request)
        if fave is None:
            return HttpResponseServerError("Unknown document or audio id")

        f = FavoriteForm(request.POST, instance=fave)
        if f.is_valid():
            new_fave = f.save(commit=False)
            new_fave.user = request.user
            new_fave.save()
        else:
            # Validation errors fail silently. Probably could be better.
            return HttpResponseServerError("Failure. Form invalid")

        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods={'POST'},
            content="Not an ajax request."
        )


@login_required
def delete_favorite(request):
    """Delete a user's favorite

    Deletes a favorite for a user using an ajax call and post data.
    """
    if request.is_ajax():
        fave = get_favorite(request)
        if fave is None:
            return HttpResponseServerError("Unknown document or audio id")

        fave.delete()

        try:
            if request.POST['message'] == "True":
                # used on the profile page. True is a string, not a bool.
                messages.add_message(request, messages.SUCCESS,
                                     'Your favorite was deleted successfully.')
        except MultiValueDictKeyError:
            # This happens if message isn't set.
            pass

        return HttpResponse("It worked.")

    else:
        return HttpResponseNotAllowed(
            permitted_methods=['POST'],
            content="Not an ajax request."
        )

