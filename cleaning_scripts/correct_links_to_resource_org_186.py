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


def link_fixer(link):
    """Fixes the errors in a link

    Orig:  http://bulk.resource.org/courts.gov/c/US/819/996.F2d.311.html
    Fixed: http://bulk.resource.org/courts.gov/c/F2/996/996.F2d.311.html
    """
    # Very crude and lazy replacement of US with F2
    link_parts = link.split('US')
    fixed = 'F2'.join(link_parts)

    # Fixes the number
    link_parts = fixed.split('/')
    number = int(link_parts[-2]) + 177
    fixed = '/'.join(link_parts[0:-2]) + "/" + str(number) + "/" + str(link_parts[-1])

    return fixed

def cleaner(simulate=False, verbose=False):
    docs = queryset_generator(Document.objects.filter(source = 'R', time_retrieved__gt = '2011-06-01'))
    for doc in docs:
        original_link = doc.download_url
        fixed = link_fixer(original_link)
        doc.download_url = fixed
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


if __name__ == '__main__':
    main()
