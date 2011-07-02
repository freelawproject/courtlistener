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

from alert.alertSystem.models import *
from alert.userHandling.forms import *
from alert.userHandling.models import *
from alert.lib.encode_decode import ascii_to_num
from django.contrib.sites.models import Site
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage
from django.core.paginator import InvalidPage
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404, get_list_or_404
from django.template import RequestContext
from django.template.defaultfilters import slugify
from django.utils import simplejson
from django.views.decorators.cache import cache_page
import string
import traceback


@cache_page(60*5)
def redirect_short_url(request, encoded_string):
    """Redirect a user to the CourtListener site from the crt.li site."""

    # strip any GET arguments from the string
    index = string.find(encoded_string, "&")
    if index != -1:
        # there's an ampersand. Strip the GET params.
        encoded_string = encoded_string[0:index]

    # Decode the string to find the object ID, and construct a link.
    num = ascii_to_num(encoded_string)

    # Get the document or throw a 404
    doc = get_object_or_404(Document, documentUUID = num)

    # Construct the URL
    slug = doc.citation.slug
    court = str(doc.court.courtUUID)
    current_site = Site.objects.get_current()
    URL = "http://" + current_site.domain + "/" + court + "/" + \
        encoded_string + "/" + slug + "/"
    return HttpResponsePermanentRedirect(URL)


@cache_page(60*5)
def viewCase(request, court, id, casename):
    '''
    Take a court, an ID, and a casename, and return the document. Casename
    isn't used, and can be anything.

    We also test if the document ID is a favorite for the user, and send data
    as such. If it's a favorite, we send the bound form for the favorite, so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    '''

    # Decode the id string back to an int
    id = ascii_to_num(id)

    # Look up the court, document, title and favorite information
    doc   = get_object_or_404(Document, documentUUID = id)
    ct    = get_object_or_404(Court, courtUUID = court)
    title = doc.citation.caseNameShort
    user  = request.user
    try:
        # Get the favorite, if possible
        # TODO: This query will fail. No user in this model anymore.
        fave = Favorite.objects.get(doc_id = doc.documentUUID, user = request.user)
        favorite_form = FavoriteForm(instance=fave)
    except ObjectDoesNotExist:
        favorite_form = FavoriteForm(initial = {'doc_id': doc.documentUUID})

    return render_to_response('display_cases.html', {'title': title,
        'doc': doc, 'court': ct, 'favorite_form': favorite_form},
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

        # Get the favorite, if it already exists for the user. Otherwise, create it.
        doc = Document.objects.get(documentUUID = doc_id)
        fave, created = Favorite.objects.get_or_create(user = request.user, doc_id = doc)
        form = FavoriteForm(request.POST, instance = fave)

        if form.is_valid():
            cd = form.cleaned_data

            # Then we update it
            fave.name = cd['name']
            fave.notes = cd['notes']
            fave.save()

        else:
            # invalid form...print errors...
            HttpResponse("Failure. Form invalid")

        return HttpResponse("It worked")
    else:
        return HttpResponse("Not an ajax request.")


@login_required
def delete_favorite(request):
    '''
    Deletes a favorite for a user using an ajax call and post data. If a tag
    will be orphaned after the deletion, the tag is deleted as well.
    '''
    if request.is_ajax():
        # If it's an ajax request, gather the data from the form, save it to
        # the DB, and then return a success code.
        try:
            doc_id = request.POST['doc_id']
        except:
            return HttpResponse("Unknown doc_id")
        try:
            fave = Favorite.objects.get(user = request.user, doc_id = doc_id)

            # Finally, delete the favorite
            fave.delete()
        except:
            # Couldn't find the document for some reason. Maybe they already
            # deleted it?
            pass

        return HttpResponse("It worked.")

    else:
        return HttpResponse("Not an ajax request.")


@cache_page(60*15)
def viewDocumentListByCourt(request, court):
    '''
    Show documents for a court, ten at a time
    '''
    from django.core.paginator import Paginator, InvalidPage, EmptyPage
    if court == "all":
        # we get all records, sorted by dateFiled.
        docs = Document.objects.order_by("-dateFiled")
        ct = "All courts"
    else:
        ct = Court.objects.get(courtUUID = court)
        docs = Document.objects.filter(court = ct).order_by("-dateFiled")

    # we will show ten docs/page
    paginator = Paginator(docs, 10)

    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1

    # only allow queries up to page 100.
    if page > 100:
        return render_to_response('view_documents_by_court.html',
            {'over_limit': True}, RequestContext(request))

    # If page request is out of range, deliver last page of results.
    try:
        documents = paginator.page(page)
    except (EmptyPage, InvalidPage):
        documents = paginator.page(paginator.num_pages)

    return render_to_response('view_documents_by_court.html', {'title': ct,
        "documents": documents}, RequestContext(request))
