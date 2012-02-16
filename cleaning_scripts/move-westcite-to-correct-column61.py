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

import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from search.models import Document, Citation
from alert.lib.db_tools import *

from optparse import OptionParser
from lxml.html import fromstring, tostring
import re

def db_corrector(simulate, verbose):
    '''Fixes invalid resource.org citations

    This one-off script iterates over all documents currently in the system
    that were imported from resource.org, and moves their citation information
    from the caseNumber field to the docketNumber field.

    Once that is complete, it pulls the HTML for the document, and extracts
    the docket number from it, if possible. Since we already have the West
    citations, we don't care particularly about errors, and can carelessly
    punt them.
    '''
    docs = queryset_iterator(Document.objects.filter(source = 'R'))
    for doc in docs:
        if verbose:
            print "Assigning %s to westCite on doc %s" % (doc.citation.docketNumber, doc.documentUUID)
        doc.citation.westCite = doc.citation.docketNumber

        # Gather the docket number
        try:
            htmlTree = fromstring(doc.documentHTML)
            docket = htmlTree.xpath('//p[@class = "docket"]')[0].text
            docket = docket.replace('No. ', '').strip('.')
            doc.citation.docketNumber = docket
        except IndexError:
            if verbose:
                print "Failed to get docket number from text."
            doc.citation.docketNumber = None
        if not simulate:
            doc.citation.save()

    print "***DATA LOSS WARNING - DO NOT RUN THIS SCRIPT TWICE***"


def main():
    usage = "usage: %prog [--verbose] [---simulate]"
    parser = OptionParser(usage)
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
        default=False, help="Display log during execution")
    parser.add_option('-s', '--simulate', action="store_true",
        dest='simulate', default=False, help="Simulate the corrections without " + \
        "actually making them.")
    (options, args) = parser.parse_args()

    verbose = options.verbose
    simulate = options.simulate

    if simulate:
        print "*******************************************"
        print "* SIMULATE MODE - NO CHANGES WILL BE MADE *"
        print "*******************************************"

    print "***DATA LOSS WARNING - DO NOT RUN THIS SCRIPT TWICE***"

    return db_corrector(simulate, verbose)
    exit(0)


if __name__ == '__main__':
    main()
