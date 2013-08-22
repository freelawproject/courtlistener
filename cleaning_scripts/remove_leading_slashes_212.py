import sys
execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)

import settings
from django.core.management import setup_environ
setup_environ(settings)

from search.models import Document
from juriscraper.lib.string_utils import harmonize, clean_string
from optparse import OptionParser


def fixer(simulate=False, verbose=False):
    """Remove leading slashes by running the new and improved harmonize/clean_string scipts"""
    docs = Document.objects.raw(r'''select Document.documentUUID
                                    from Document, Citation
                                    where Document.citation_id = Citation.citationUUID and
                                    Citation.case_name like '/%%';''')
    for doc in docs:
        if verbose:
            print "Fixing document %s: %s" % (doc.pk, doc)

        if not simulate:
            doc.citation.case_name = harmonize(clean_string(doc.citation.case_name))
            doc.citation.save()


def main():
    usage = "usage: %prog [--verbose] [---simulate]"
    parser = OptionParser(usage)
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
        default=False, help="Display log during execution")
    parser.add_option('-s', '--simulate', action="store_true",
        dest='simulate', default=False, help=("Simulate the corrections without "
        "actually making them."))
    (options, args) = parser.parse_args()

    verbose = options.verbose
    simulate = options.simulate

    if simulate:
        print "*******************************************"
        print "* SIMULATE MODE - NO CHANGES WILL BE MADE *"
        print "*******************************************"

    return fixer(simulate, verbose)

if __name__ == '__main__':
    main()
