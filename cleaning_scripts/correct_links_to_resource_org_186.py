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

from alerts.models import Document, Citation
from lib.db_tools import queryset_iterator
from lib.string_utils import clean_string
from lib.string_utils import harmonize
from lib.string_utils import titlecase
from optparse import OptionParser
import re


def link_fixer(link):
    '''Fixes the errors in a link

    Orig:  http://bulk.resource.org/courts.gov/c/US/819/996.F2d.311.html
    Fixed: http://bulk.resource.org/courts.gov/c/F2/996/996.F2d.311.html
    '''
    # Very crude and lazy replacement of US with F2
    link_parts = link.split('US')
    fixed = 'F2'.join(link_parts)

    # Fixes the number
    link_parts = fixed.split('/')
    number = int(link_parts[-2]) + 177
    fixed = '/'.join(link_parts[0:-2]) + "/" + str(number) + "/" + str(link_parts[-1])

    return fixed

def cleaner(simulate=False, verbose=False):
    docs = queryset_iterator(Document.objects.filter(source = 'R', time_retrieved__gt = '2011-06-01'))
    for doc in docs:
        original_link = doc.download_URL
        fixed = link_fixer(original_link)
        doc.download_URL = fixed
        if verbose:
            print "Changing: " + original_link
            print "      to: " + fixed
        if not simulate:
            doc.save()


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
