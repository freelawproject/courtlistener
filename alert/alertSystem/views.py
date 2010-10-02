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
from alert.alertSystem.string_utils import ascii_to_num
from django.contrib.sites.models import Site
from django.http import HttpResponsePermanentRedirect, Http404
from django.shortcuts import render_to_response
from django.shortcuts import get_object_or_404, get_list_or_404
from django.template import RequestContext
from django.template.defaultfilters import slugify
from django.views.decorators.cache import cache_page
import string

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
    """
    Take a court, an ID, and a casename, and return the document.

    This is remarkably easy compared to old method, below. casename isn't
    used, and can be anything.
    """

    # Decode the id string back to an int
    id = ascii_to_num(id)

    # Look up the court, document, and title
    doc   = get_object_or_404(Document, documentUUID = id)
    ct    = get_object_or_404(Court, courtUUID = court)
    title = doc.citation.caseNameShort

    return render_to_response('display_cases.html', {'title': title,
        'doc': doc, 'court': ct}, RequestContext(request))


@cache_page(60*5)
def viewCasesDeprecated(request, court, case):
    '''
    This is a fallback view that is only used by old links that have not yet
    been flushed from the Interwebs. It was too slow, so viewCases was
    created to replace it.

    Take a court and a caseNameShort, and display what we know about that
    case. If the casename fails, try the case number.

    It no longer will return more than one case per URL.
    '''

    # get the court information from the URL
    ct = Court.objects.get(courtUUID = court)

    # try looking it up by casename. Failing that, try the caseNumber.
    # replace hyphens with spaces, and underscores with hyphens to undo the
    # URLizing that the get_absolute_url in the Document model used to set up.
    caseName = case.replace('-', ' ').replace('_', '-')
    cites = get_list_or_404(Citation, caseNameShort = caseName)

    # get any documents with this citation at that court.
    doc = get_list_or_404(Document, court = ct, citation = cites[0])

    # Construct a URL
    current_site = Site.objects.get_current()
    slug = doc[0].citation.slug
    URL = "http://" + current_site.domain + "/" + court + "/" + \
        num_to_ascii(doc[0].documentUUID) + "/" + slug + "/"
    return HttpResponsePermanentRedirect(URL)


@cache_page(60*15)
def viewDocumentListByCourt(request, court):
    """Show documents for a court, ten at a time"""
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
