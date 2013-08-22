import sys
execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)

import settings
from django.core.management import setup_environ
setup_environ(settings)

from search.models import Document, Citation
from alert.lib.db_tools import *

from optparse import OptionParser
from lxml.html import fromstring

def db_corrector(simulate, verbose):
    """Fixes invalid resource.org citations

    This one-off script iterates over all documents currently in the system
    that were imported from resource.org, and moves their citation information
    from the caseNumber field to the docket_number field.

    Once that is complete, it pulls the HTML for the document, and extracts
    the docket number from it, if possible. Since we already have the West
    citations, we don't care particularly about errors, and can carelessly
    punt them.
    """
    docs = queryset_generator(Document.objects.filter(source = 'R'))
    for doc in docs:
        if verbose:
            print "Assigning %s to west_cite on doc %s" % (doc.citation.docket_number, doc.documentUUID)
        doc.citation.west_cite = doc.citation.docket_number

        # Gather the docket number
        try:
            htmlTree = fromstring(doc.html)
            docket = htmlTree.xpath('//p[@class = "docket"]')[0].text
            docket = docket.replace('No. ', '').strip('.')
            doc.citation.docket_number = docket
        except IndexError:
            if verbose:
                print "Failed to get docket number from text."
            doc.citation.docket_number = None
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


if __name__ == '__main__':
    main()
