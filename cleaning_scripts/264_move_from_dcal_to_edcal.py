import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

import re
from alert import settings
from alert.corpus_importer.import_law_box import get_date_filed
from alert.lib.sunburnt import sunburnt
from alert.search.models import Document
from lxml import html
from optparse import OptionParser


def cleaner(simulate=False, verbose=False):
    """Find items that:

     - Contain the word "argued"
     - Occur between 2002-01-01 and 2031-12-31
     - Are precedential
     - Have a source == L.
     - Match a regex for the funky date pattern

    """
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='rw')
    q = {'fq': ['court_exact:%s' % 'californiad']}

    results = conn.raw_query(**q)
    for r in results:
        if verbose:
            print "Running tests on item %s" % r['id']
        # We iterate over the search results. For each one, we run tests on it to see if it needs a fix.
        # If so, we get the record from the database and update it. If not, re continue.
        if r['source'] != 'L':
            # Only affects pure Lawbox cases. Merged cases did not have their date updated.
            if verbose:
                print "  - Source is %s. Punting." % r['source']
            continue

        re_match = re.search('Argued.{1,12}\d{1,2}-\d{1,2}, \d{4}', r['text'])
        if not re_match:
            # Lacks the affronting line. Onwards.
            if verbose:
                print "  - Lacks the bad date string. Punting."
            continue

        if verbose:
            print "  - All tests pass. This item may be modified. (Simulate is: %s)" % simulate

        doc = Document.objects.get(pk=r['id'])
        clean_html_tree = html.fromstring(doc.html_lawbox)

        new_date = get_date_filed(clean_html_tree, citations=[]).date()

        if verbose:
            print "  - https://www.courtlistener.com%s" % doc.get_absolute_url()
            print "  - Old date was: %s" % doc.date_filed
            print "  - New date is:  %s" % new_date

        if new_date == doc.date_filed:
            # No change needed, simply move on.
            if verbose:
                print "  - Dates are equal: Proceeding."
            continue
        else:
            if verbose:
                print "  - Updating with new date."
            if not simulate:
                doc.date_filed = new_date
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


