import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
from django.template.defaultfilters import slugify
setup_environ(settings)

from alert.lib.string_utils import trunc
from alert.search.models import Citation
from optparse import OptionParser


def fixer(simulate=False, verbose=False):
    '''If a Citation lacks a slug, we make one for it.'''
    citations = Citation.objects.filter(slug=None)

    for citation in citations:
        if verbose:
            print "Fixing %s" % citation
        citation.slug = trunc(slugify(citation.case_name), 50)
        if not simulate:
            citation.save()


def main():
    usage = "usage: %prog [--verbose] [---simulate]"
    parser = OptionParser(usage)
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
        default=False, help="Display log during execution")
    parser.add_option('-s', '--simulate', action="store_true",
        dest='simulate', default=False, help=("Simulate the corrections "
                                              "without actually making them."))
    (options, args) = parser.parse_args()

    verbose = options.verbose
    simulate = options.simulate

    if simulate:
        print "*******************************************"
        print "* SIMULATE MODE - NO CHANGES WILL BE MADE *"
        print "*******************************************"

    return fixer(simulate, verbose)
    exit(0)

if __name__ == '__main__':
    main()
