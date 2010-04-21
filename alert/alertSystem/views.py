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


from django.shortcuts import render_to_response
from django.template import RequestContext
from alert.alertSystem.models import *


def viewCases(request, court, case):
    """Take a court and a caseNameShort, and display what we know about that
    case.
    """

    # get the court information from the URL
    ct = Court.objects.get(courtUUID = court)

    # try looking it up by casename. Failing that, try the caseNumber. 
    # replace spaces with hyphens to undo the URLizing that the get_absolute_url
    # in the Document model sets up.
    cites = Citation.objects.filter(caseNameShort__in = [case.replace('-', ' '), case])
    if cites.count() == 0:
        # if we can't find it by case name, try by case number
        cites = Citation.objects.filter(caseNumber = case)

    if cites.count() > 0:
        # get any documents with this/these citation(s) at that court. We need
        # all the documents with what might be more than one citation, so we\
        # use a filter, and the __in method.
        docs = Document.objects.filter(court = ct, citation__in = cites).order_by("-dateFiled")

        return render_to_response('display_cases.html', {'title': case,
            'docs': docs, 'court': ct}, RequestContext(request))

    else:
        # we have no hits, punt
        return render_to_response('display_cases.html', {'title': case,
            'court': ct}, RequestContext(request))


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

    # If page request is out of range, deliver last page of results.
    try:
        documents = paginator.page(page)
    except (EmptyPage, InvalidPage):
        documents = paginator.page(paginator.num_pages)

    return render_to_response('view_documents_by_court.html', {'title': ct,
        "documents": documents}, context_instance=RequestContext(request))
