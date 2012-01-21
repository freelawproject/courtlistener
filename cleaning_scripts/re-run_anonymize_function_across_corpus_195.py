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

from search.models import Document
from alert.lib.db_tools import queryset_iterator
from alert.lib.string_utils import anonymize
from optparse import OptionParser
import re

def cleaner(simulate=False, verbose=False):
    '''Re-run the anonymize function across the whole corpus.
    
    The anonymize function was previously missing any documents that contained 
    punctuation before or after an ID. This script re-runs the function, fixing
    the error.
    '''
    docs = queryset_iterator(Document.objects.all())
    for doc in docs:
        text = doc.documentPlainText
        clean_lines = []
        any_mods = []
        for line in text.split('\n'):
            clean_line, modified = anonymize(line)
            if modified:
                print "Fixing text in document: %s" % doc.documentUUID
                print "Line reads: %s" % line
                fix = raw_input("Fix the line? [Y/n]: ") or 'y'
                if fix.lower() == 'y':
                    clean_lines.append(clean_line)
                    any_mods.append(modified)
                else:
                    clean_lines.append(line)
            else:
                clean_lines.append(line)

        if not simulate and any(any_mods):
            doc.documentPlainText = '\n'.join(clean_lines)
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
