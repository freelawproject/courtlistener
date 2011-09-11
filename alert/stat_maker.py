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
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.
import settings
from django.core.management import setup_environ
setup_environ(settings)

from django.contrib.flatpages.models import FlatPage
from django.template import loader, Context
from alert.alertSystem.models import Document
from alert.alertSystem.models import PACER_CODES

def makeStats():
    '''
    A function that displays some sweet (and accurate) coverage stats. Essentially,
    we'll gather the stats here, and process them in a template, and then dump
    the results in a flatpage.

    The result is that the coverage page is reliably cached in the DB.

    Stats we want include:
        - total number of documents in the db
        - number of documents from each court
        - earliest and latest document from each court

    Thus, our method will be:
        1. Get the number of documents (easy)
        2. Build a nested list of the following form:
            [[oldestDocInCourt, numCasesInCourt],[oldestDocInCourt2, numCasesInCourt2]]
    '''

    totalCasesQ = Document.objects.all().count()

    statsP = []
    # get all the courts
    for code in PACER_CODES:
        q = Document.objects.filter(court = code[0],
            documentType = "Published").exclude(dateFiled = None)
        numDocs = q.count()
        if numDocs != 0:
            doc = q.order_by('dateFiled')[0]
            tempList = [doc, numDocs]
            statsP.append(tempList)

    statsU = []
    for code in PACER_CODES:
        q = Document.objects.filter(court = code[0],
            documentType__in = ["Unpublished", "Errata", "In-chambers", "Relating-to"])\
            .exclude(dateFiled = None)
        numDocs = q.count()
        if numDocs != 0:
            doc = q.order_by('dateFiled')[0]
            tempList = [doc, numDocs]
            statsU.append(tempList)

    statsMissingType = []
    for code in PACER_CODES:
        q = Document.objects.filter(court = code[0],
            documentType = "").exclude(dateFiled = None)
        numDocs = q.count()
        if numDocs != 0:
            doc = q.order_by('dateFiled')[0]
            tempList = [doc, numDocs]
            statsMissingType.append(tempList)

    return totalCasesQ, statsP, statsU, statsMissingType


def main():
    '''
    The master function. This will receive arguments from the user, determine
    the actions to take, then hand it off to other functions that will handle the
    nitty-gritty crud.

    returns an int indicating success or failure. == 0 is success. > 0 is failure.
    '''

    # get the values from the DB
    totalCasesQ, statsP, statsU, statsMissingType = makeStats()

    # make them into pretty HTML
    t = loader.get_template('coverage/coverage.html')
    c = Context({'totalCasesQ': totalCasesQ, 'statsP':statsP, 'statsU': statsU,
        'statsMissingType': statsMissingType})
    html = t.render(c)

    # put that in the correct flatpage
    page = FlatPage.objects.get(url = '/coverage/')
    page.content = html
    page.save()

    return 0


if __name__ == '__main__':
    main()
