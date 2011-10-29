# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from alert.alerts.models import Court, Document
from alert.userHandling.forms import FavoriteForm
from alert.userHandling.models import Favorite
from alert.lib.encode_decode import ascii_to_num
from django.contrib.auth.decorators import login_required
from django.contrib.sites.models import Site
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage
from django.core.paginator import InvalidPage
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response
from django.shortcuts import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from django.utils.datastructures import MultiValueDictKeyError
from django.views.decorators.cache import cache_page
import string


@cache_page(60 * 5)
def redirect_short_url(request, encoded_string):
    '''Redirect a user to the CourtListener site from the crt.li site.'''

    # strip any GET arguments from the string
    index = string.find(encoded_string, "&")
    if index != -1:
        # there's an ampersand. Strip the GET params.
        encoded_string = encoded_string[0:index]

    # Decode the string to find the object ID, and construct a link.
    num = ascii_to_num(encoded_string)

    # Get the document or throw a 404
    doc = get_object_or_404(Document, documentUUID=num)

    # Construct the URL
    slug = doc.citation.slug
    court = str(doc.court.courtUUID)
    current_site = Site.objects.get_current()
    URL = "http://" + current_site.domain + "/" + court + "/" + \
        encoded_string + "/" + slug + "/"
    return HttpResponsePermanentRedirect(URL)


@cache_page(60 * 5)
def viewCase(request, court, pk, casename):
    '''Take a court and an ID, and return the document.

    We also test if the document ID is a favorite for the user, and send data
    as such. If it's a favorite, we send the bound form for the favorite, so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    '''

    # Decode the id string back to an int
    pk = ascii_to_num(pk)

    # Look up the court, document, title and favorite information
    doc = get_object_or_404(Document, documentUUID=pk)
    ct = get_object_or_404(Court, courtUUID=court)
    title = doc.citation.caseNameShort
    user = request.user

    try:
        # Check if we know the user's query. Pass it onwards if so.
        query = request.GET['q']
    except MultiValueDictKeyError:
        # No query parameter.
        query = ''

    try:
        # Get the favorite, if possible
        fave = Favorite.objects.get(doc_id=doc.documentUUID, users__user=user)
        favorite_form = FavoriteForm(instance=fave)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={'doc_id': doc.documentUUID,
            'name' : doc.citation.caseNameFull})

    return render_to_response('display_cases.html', {'title': title,
        'doc': doc, 'court': ct, 'favorite_form': favorite_form, 'query': query},
        RequestContext(request))


@login_required
def save_or_update_favorite(request):
    '''Uses ajax to save or update a favorite.

    Receives a request as an argument, and then uses that plus POST data to
    create or update a favorite in the database for a specific user. If the user
    already has the document favorited, it updates the favorite with the new
    information. If not, it creates a new favorite.
    '''
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

            up = request.user.get_profile()
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
    '''Provide a form for the user to update alerts, or do so if submitted via
    POST
    '''

    try:
        fave_id = int(fave_id)
    except:
        return HttpResponseRedirect('/')

    try:
        fave = Favorite.objects.get(id=fave_id, users__user=request.user)
        doc = fave.doc_id
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

    return render_to_response('profile/edit_favorite.html', {'favorite_form': form,
        'doc' : doc}, RequestContext(request))


@login_required
def delete_favorite(request):
    '''Delete a user's favorite

    Deletes a favorite for a user using an ajax call and post data.
    '''
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
