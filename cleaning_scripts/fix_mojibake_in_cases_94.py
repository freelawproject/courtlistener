# -*- coding: utf-8 -*-

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
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.

import sys
sys.path.append('/var/www/court-listener/alert')

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
        text = doc.documentPlainText
        doc.documentPlainText = fix_mojibake(text)

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
