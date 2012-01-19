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

from alert import settings
from alert.lib import search_utils
from alert.search.forms import SearchForm
from alert.search.models import Court
from alert.search.models import Document
from alert.tinyurl.encode_decode import ascii_to_num
from alert.favorites.forms import FavoriteForm
from alert.favorites.models import Favorite
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from django.views.decorators.cache import never_cache

import os

@never_cache
def view_case(request, court, pk, casename):
    '''Take a court and an ID, and return the document.

    We also test if the document ID is a favorite for the user, and send data
    as such. If it's a favorite, we send the bound form for the favorite so
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

    search_form = SearchForm(request.GET)
    get_string = search_utils.make_get_string(request)

    if search_form.is_valid():
        cd = search_form.cleaned_data
        court_facet_fields, stat_facet_fields, count = search_utils.place_facet_queries(cd)
        # Create facet variables that can be used in our templates
        court_facets = search_utils.make_facets_variable(
                         court_facet_fields, search_form, 'court_exact', 'court_')
        status_facets = search_utils.make_facets_variable(
                         stat_facet_fields, search_form, 'status_exact', 'stat_')

    try:
        # Get the favorite, if possible
        fave = Favorite.objects.get(doc_id=doc.documentUUID, users__user=user)
        favorite_form = FavoriteForm(instance=fave)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(initial={'doc_id': doc.documentUUID,
            'name' : doc.citation.caseNameFull})

    return render_to_response(
                  'view_case.html',
                  {'title': title, 'doc': doc, 'court': ct, 'count': count,
                   'favorite_form': favorite_form, 'search_form': search_form,
                   'get_string': get_string, 'court_facets': court_facets,
                   'status_facets': status_facets},
                  RequestContext(request))

def serve_static_file(request, mime='', file_path=''):
    '''Sends a static file to a user.
    
    This serves up the static case files such as the PDFs in a way that can be
    blocked from search engines if necessary. We do four things:
     - Look up the document associated with the filepath
     - Check if it's blocked
     - If blocked, we set the x-robots-tag HTTP header
     - Serve up the file using Apache2's xsendfile
    '''
    doc = get_object_or_404(Document, local_path=os.path.join(mime, file_path))
    response = HttpResponse()
    if doc.blocked:
        response['X-Robots-Tag'] = 'noindex,noodp,noarchive,noimageindex'
    print "So far, so good"
    abs_file_path = os.path.join(settings.MEDIA_ROOT, file_path)
    response['X-Sendfile'] = abs_file_path
    return response
