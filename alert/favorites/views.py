from alert.casepage.views import make_caption, make_citation_string
from alert.search.models import Document
from alert.favorites.forms import FavoriteForm
from alert.favorites.models import Favorite
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.datastructures import MultiValueDictKeyError

@login_required
def save_or_update_favorite(request):
    """Uses ajax to save or update a favorite.

    Receives a request as an argument, and then uses that plus POST data to
    create or update a favorite in the database for a specific user. If the user
    already has the document favorited, it updates the favorite with the new
    information. If not, it creates a new favorite.
    """
    if request.is_ajax():
        # If it's an ajax request, gather the data from the form, save it to
        # the DB, and then return a success code.
        try:
            doc_id = request.POST['doc_id']
        except:
            return HttpResponse("Unknown doc_id")

        doc = Document.objects.get(documentUUID=doc_id)
        try:
            fave = Favorite.objects.get(doc_id=doc, users__user=request.user)
        except ObjectDoesNotExist:
            fave = Favorite()

        f = FavoriteForm(request.POST, instance=fave)
        if f.is_valid():
            new_fave = f.save()

            up = request.user.profile
            up.favorite.add(new_fave)
            up.save()
        else:
            # Validation errors fail silently. Probably could be better.
            HttpResponse("Failure. Form invalid")

        return HttpResponse("It worked")
    else:
        return HttpResponse("Not an ajax request.")



@login_required
def edit_favorite(request, fave_id):
    """Provide a form for the user to update alerts, or do so if submitted via
    POST
    """

    try:
        fave_id = int(fave_id)
    except:
        return HttpResponseRedirect('/')

    try:
        fave = Favorite.objects.get(id=fave_id, users__user=request.user)
        doc = fave.doc_id
        caption = make_caption(doc)
        citation_string = make_citation_string(doc)
    except ObjectDoesNotExist:
        # User lacks access to this fave or it doesn't exist.
        return HttpResponseRedirect('/')

    if request.method == 'POST':
        form = FavoriteForm(request.POST, instance=fave)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS,
                'Your favorite was saved successfully.')

            # redirect to the alerts page
            return HttpResponseRedirect('/profile/favorites/')

    else:
        # the form is loading for the first time
        form = FavoriteForm(instance=fave)

    return render_to_response('profile/edit_favorite.html',
                              {'favorite_form': form,
                               'doc': doc,
                               'caption': caption,
                               'citation_string': citation_string,
                               'private': False},
                              RequestContext(request))


@login_required
def delete_favorite(request):
    """Delete a user's favorite

    Deletes a favorite for a user using an ajax call and post data.
    """
    if request.is_ajax():
        # If it's an ajax request, gather the data from the form, save it to
        # the DB, and then return a success code.
        try:
            doc_id = request.POST['doc_id']
        except:
            return HttpResponse("Unknown doc_id")

        fave = Favorite.objects.get(doc_id=doc_id, users__user=request.user)

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
        return HttpResponse("Not an ajax request.")

