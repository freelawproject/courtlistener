"""
    During the initial implementation of the Lawbox corpus, we had a number of items that had a date line like so:

        "October 12-13, 1948"

    Unfortunately, our date parser recognized dates like this as 2013-10-12, instead of 1948-10-12 or 1948-10-13.

    This script finds items with that error, fixes them and then saves them back to the index and database.
"""

from lxml import html

import os
import re
import sys
from alert import settings
from alert.corpus_importer.import_law_box import get_date_filed
from alert.lib.sunburnt import sunburnt

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert.search.models import Document
from optparse import OptionParser


def sunburnt_cached_pager(results, chunksize=100):
    """Takes the results and pages them, optimizing the number of queries.

    Sunburnt makes very clever queries against Solr when it is sliced, but does not under normal iteratation. This
    little generator gives iteration without making one query per item.
    """
    cache = []
    count = len(results)
    i = 0
    while i < count:
        if i % chunksize == 0:
            # Load the cache
            cache = results[i:i + chunksize]

        # Need temporary var so we can get the item from the cache before incrementing i.
        item_to_return = cache[i]
        i += 1
        yield item_to_return


def cleaner(simulate=False, verbose=False):
    """Find items that:

     - Contain the word "argued"
     - Occur between 2002-01-01 and 2031-12-31
     - Are precedential
     - Have a source == L.
     - Match a regex for the funky date pattern

    """
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    q = {
        'q': 'argued',
        'fl': 'id,text,source',
        'fq': [
            'dateFiled:[2002-01-01T00:00:00Z TO 2031-12-31T00:00:00Z]',
            'status_exact:("Precedential")',
        ]
    }
    results = conn.raw_query(**q)
    for r in sunburnt_cached_pager(results):
        # We iterate over the search results. For each one, we run tests on it to see if it needs a fix.
        # If so, we get the record from the database and update it. If not, re continue.
        if r['source'] != 'L':
            # Only affects pure Lawbox cases. Merged cases did not have their date updated.
            continue

        re_match = re.search('Argued.{1,12}\d{1,2}-\d{1,2}, \d{4}', r['text'])
        if not re_match:
            # Lacks the affronting line. Onwards.
            continue

        if verbose:
            print "Item %s has passed all tests and may be modified." % r['id']

        doc = Document.objects.get(pk=r['id'])
        clean_html_tree = html.fromstring(doc.html_lawbox)

        new_date = get_date_filed(clean_html_tree, citations=[]).date()

        if verbose:
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


