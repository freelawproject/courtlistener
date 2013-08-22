# -*- coding: utf-8 -*-
import os
import sys
sys.path.append(os.getenv('CL_INSTALL_ROOT', '/var/www/courtlistener'))

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.lib.mojibake import fix_mojibake
from alert.lib import sunburnt
from alert.search.models import Document

from optparse import OptionParser


conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')

def cleaner(simulate=False, verbose=True):
    '''Fix cases that have mojibake as a result of pdffactory 3.51.'''

    # Find all the cases using Solr
    results_si = conn.raw_query(**{'q': u'ÚÑÎ'})
    for result in results_si:
        # For each document
        doc = Document.objects.get(documentUUID=result['id'])
        if verbose:
            print "http://courtlistener.com" + doc.get_absolute_url()
        # Correct the text
        text = doc.plain_text
        doc.plain_text = fix_mojibake(text)

        # Save the case
        if not simulate:
            doc.save()

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

    return cleaner(simulate, verbose)
    exit(0)

if __name__ == '__main__':
    main()
