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

from alert.alerts.models import Court
from alert.alerts.models import Document
from alert.tinyurl.encode_decode import ascii_to_num
from alert.userHandling.forms import FavoriteForm
from alert.userHandling.models import Favorite
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404
from django.template import RequestContext
from django.views.decorators.cache import cache_page
from django.utils.datastructures import MultiValueDictKeyError

@cache_page(60 * 5)
def view_case(request, court, pk, casename):
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
