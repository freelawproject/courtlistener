import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert import settings
from alert.corpus_importer.import_law_box import get_court_object
from alert.lib.sunburnt import sunburnt
from alert.search.models import Document
from lxml import html
from optparse import OptionParser


def cleaner(simulate=False, verbose=False):
    """Find items that are in californiad and change them to be in caed by using an updated set of regexes.
    """
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='rw')
    q = {'fq': ['court_exact:%s' % 'californiad']}

    results = conn.raw_query(**q)
    for r in results:
        if verbose:
            print "Running tests on item %s" % r['id']

        doc = Document.objects.get(pk=r['id'])

        # Make the HTML element, then figure out the court
        clean_html_tree = html.fromstring(doc.html_lawbox)
        correct_court = get_court_object(clean_html_tree)

        if verbose:
            print "  - https://www.courtlistener.com%s" % doc.get_absolute_url()
            print "  - Old value was: %s" % doc.court_id
            print "  - New value is:  %s" % correct_court

        if doc.court_id == correct_court:
            # No change needed, simply move on.
            if verbose:
                print "  - Proceeding to next item: Values are equal."
            continue
        elif correct_court != 'caed':
            # Attempting to change to an unexpected value.
            if verbose:
                print "  - Proceeding to next item: New value is not what we expected."
            continue
        else:
            if verbose:
                print "  - Updating with new value."
            if not simulate:
                doc.court_id = correct_court
                doc.save(index=True, commit=False)

    # Do one big commit at the end
    conn.commit()


def main():
    usage = "usage: %prog [--verbose] [---simulate]"
    parser = OptionParser(usage)
    parser.add_option(
        '-v',
        '--verbose',
        action="store_true",
        dest='verbose',
        default=False,
        help="Display log during execution"
    )
    parser.add_option(
        '-s',
        '--simulate',
        action="store_true",
        dest='simulate',
        default=False,
        help="Simulate the corrections without actually making them."
    )
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


