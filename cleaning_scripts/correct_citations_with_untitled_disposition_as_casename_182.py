import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from django.utils.text import slugify
from alert.search.models import Document
from alert.lib.string_utils import trunc
from optparse import OptionParser


def cleaner(simulate=False, verbose=False):
    """Fixes the titles of cases where the name is untitle disposition.

    Basically, the algorithm here is to find all cases with the error, then
    open each in Firefox one by one. After each case is opened, a prompt will
    allow the case name to be typed in, and it will be corrected on the site.

    These corrections will go live immediately, but will require a reindex to
    be live in the search system.
    """
    queryset = Document.search.query('@casename "unpublished disposition"')
    docs = queryset.set_options(mode="SPH_MATCH_EXTENDED2").order_by('-date_filed')
    if verbose:
        print "%s results found." % (docs.count())

    # Must slice here, or else only get top 20 results
    for doc in docs[0:docs.count()]:
        if doc.citation.caseNameFull.lower() == "unpublished disposition":
            # Only do each case once, since the index isn't updated until
            # later, and I may run this script many times.
            print doc.download_URL
            casename = raw_input("Case name: ")
            doc.citation.caseNameFull = casename
            doc.citation.caseNameShort = trunc(casename, 100)
            doc.citation.slug = trunc(slugify(casename), 50)
            doc.precedential_status = "Unpublished"
            if not simulate:
                doc.citation.save()
                doc.save()
            print ""


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
