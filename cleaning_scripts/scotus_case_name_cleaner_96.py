import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert.search.models import Document, Citation
from alert.lib.db_tools import queryset_generator
from alert.lib.string_utils import clean_string
from alert.lib.string_utils import harmonize
from alert.lib.string_utils import titlecase
from optparse import OptionParser


def cleaner(simulate=False, verbose=False):
    docs = queryset_generator(Document.objects.filter(source = 'R'))
    for doc in docs:
        caseNameShortOrig = doc.citation.caseNameShort
        caseNameFullOrig = doc.citation.caseNameFull
        caseNameShort = titlecase(harmonize(clean_string(caseNameShortOrig)))
        caseNameFull  = titlecase(harmonize(clean_string(caseNameFullOrig)))
        doc.citation.caseNameShort = caseNameShort
        doc.citation.caseNameFull = caseNameFull
        if verbose:
            if (caseNameShortOrig != caseNameShort) or (caseNameFullOrig != caseNameFull):
                print "Document: %s" % doc.documentUUID
            if caseNameShortOrig != caseNameShort:
                print "Short name, replacing: '%s'" % caseNameShortOrig
                print "                 with: '%s'" % caseNameShort
            if caseNameFullOrig != caseNameFull:
                print " Full name, replacing: '%s'" % caseNameFullOrig
                print "                 with: '%s'\n" % caseNameFull
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


if __name__ == '__main__':
    main()


