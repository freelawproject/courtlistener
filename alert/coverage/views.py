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
from alert.alertSystem.models import Document, Court
from alert.alertSystem.models import PACER_CODES

def coverage(request):
    """A view that displays some sweet (and accurate) coverage stats. Essentially,
    we'll gather the stats here, and hand them all off to a template that will
    kindly display them all for us.

    Stats we want include:
        - total number of cases in the db
        - number of cases in each court
        - earliest and latest case in each court

    Thus, our method will be:
        1. Get the number of cases (easy)
        2. Build a nested list of the following form:
            [[oldestDocInCourt, numCasesInCourt],[oldestDocInCourt2, numCasesInCourt2]]
    """

    totalCasesQ = Document.objects.all().count()

    statsP = []
    # get all the courts
    for code in PACER_CODES:
        q = Document.objects.filter(court=code[0], documentType="P")
        numDocs = q.count()
        if numDocs != 0:
            doc = q.order_by('dateFiled')[0]
            tempList = [doc, numDocs]
            statsP.append(tempList)

    statsU = []
    for code in PACER_CODES:
        q = Document.objects.filter(court=code[0], documentType__in=["U","E","I","R"])
        numDocs = q.count()
        if numDocs != 0:
            doc = q.order_by('dateFiled')[0]
            tempList = [doc, numDocs]
            statsU.append(tempList)

    statsMissingType = []
    for code in PACER_CODES:
        q = Document.objects.filter(court=code[0], documentType="")
        numDocs = q.count()
        if numDocs != 0:
            doc = q.order_by('dateFiled')[0]
            tempList = [doc, numDocs]
            statsMissingType.append(tempList)

    return render_to_response('coverage/coverage.html', {'totalCasesQ': totalCasesQ,
        'statsP':statsP, 'statsU': statsU, 'statsMissingType': statsMissingType},
        RequestContext(request))



