from alert.audio.models import Audio
from alert.favorites.forms import FavoriteForm
from alert.favorites.models import Favorite
from alert.search.models import Document
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, Http404, HttpResponseServerError, \
    HttpResponseNotAllowed
from django.utils.datastructures import MultiValueDictKeyError


@login_required
def save_or_update_favorite(request):
    """Uses ajax to save or update a favorite.

    Receives a request as an argument, and then uses that plus POST data to
    create or update a favorite in the database for a specific user. If the
    user already has the document favorited, it updates the favorite with the
    new information. If not, it creates a new favorite.
    """
    if request.is_ajax():
        # If it's an ajax request, gather the data from the form, save it to
        # the DB, and then return a success code.
        audio_pk = request.POST.get('audio_id')
        doc_pk = request.POST.get('doc_id')
        if audio_pk and audio_pk != 'undefined':
            af = Audio.objects.get(pk=audio_pk)
            try:
                fave = Favorite.objects.get(audio_id=af,
                                            users__user=request.user)
            except ObjectDoesNotExist:
                fave = Favorite()
        elif doc_pk and doc_pk != 'undefined':
            doc = Document.objects.get(pk=doc_pk)
            try:
                fave = Favorite.objects.get(doc_id=doc,
                                            users__user=request.user)
            except ObjectDoesNotExist:
                fave = Favorite()
        else:
            return Http404("Unknown document or audio id")

        f = FavoriteForm(request.POST, instance=fave)
        if f.is_valid():
            new_fave = f.save()

            up = request.user.profile
            up.favorite.add(new_fave)
            up.save()
        else:
            # Validation errors fail silently. Probably could be better.
            return HttpResponseServerError("Failure. Form invalid")

        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed("Not an ajax request.")


@login_required
def delete_favorite(request):
    """Delete a user's favorite

    Deletes a favorite for a user using an ajax call and post data.
    """
    if request.is_ajax():
        # If it's an ajax request, gather the data from the form, save it to
        # the DB, and then return a success code.
        audio_pk = request.POST.get('audio_id')
        doc_pk = request.POST.get('doc_id')
        if audio_pk and audio_pk != 'undefined':
            af = Audio.objects.get(pk=audio_pk)
            try:
                fave = Favorite.objects.get(audio_id=af,
                                            users__user=request.user)
            except ObjectDoesNotExist:
                fave = Favorite()
        elif doc_pk and doc_pk != 'undefined':
            doc = Document.objects.get(pk=doc_pk)
            try:
                fave = Favorite.objects.get(doc_id=doc,
                                            users__user=request.user)
            except ObjectDoesNotExist:
                fave = Favorite()
        else:
            return Http404("Unknown document or audio id")

        # Finally, delete the favorite
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
        return HttpResponseNotAllowed("Not an ajax request.")

