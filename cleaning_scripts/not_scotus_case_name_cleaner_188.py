import os
import sys
sys.path.append(os.getenv('CL_INSTALL_ROOT', '/var/www/courtlistener'))

import settings
from django.core.management import setup_environ
setup_environ(settings)

from search.models import Document, Citation
from lib.db_tools import queryset_generator
from lib.string_utils import clean_string
from lib.string_utils import harmonize
from lib.string_utils import titlecase
from optparse import OptionParser
import re


def cleaner(simulate=False, verbose=False):
    docs = queryset_generator(Document.objects.filter(date_filed__gt = '1993-08-02'))
    for doc in docs:
        caseNameShortOrig = doc.citation.caseNameShort
        caseNameFullOrig = doc.citation.caseNameFull
        caseNameShort = harmonize(clean_string(caseNameShortOrig))
        caseNameFull  = harmonize(clean_string(caseNameFullOrig))
        doc.citation.caseNameShort = caseNameShort
        doc.citation.caseNameFull = caseNameFull
        if verbose:
            if (caseNameShortOrig != caseNameShort) or (caseNameFullOrig != caseNameFull):
                print "Document: %s" % (doc.documentUUID)
            if caseNameShortOrig != caseNameShort:
                print "Short name, replacing: '%s'" % (caseNameShortOrig)
                print "                 with: '%s'" % (caseNameShort)
            if caseNameFullOrig != caseNameFull:
                print " Full name, replacing: '%s'" % (caseNameFullOrig)
                print "                 with: '%s'\n" % (caseNameFull)
        if not simulate:
            doc.citation.save()


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

    return cleaner(simulate, verbose)
    exit(0)


if __name__ == '__main__':
    main()


