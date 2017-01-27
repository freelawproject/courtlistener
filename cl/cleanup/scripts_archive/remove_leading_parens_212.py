import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert.search.models import Document
from juriscraper.lib.string_utils import harmonize, clean_string, titlecase
from optparse import OptionParser
import re


def fixer(simulate=False, verbose=False):
    """Remove leading slashes by running the new and improved harmonize/clean_string scipts"""
    docs = Document.objects.raw(r'''select Document.pk
                                    from Document, Citation
                                    where Document.citation_id = Citation.pk and
                                    Citation.case_name like '(%%';''')

    for doc in docs:
        # Special cases
        if 'Klein' in doc.case_name:
            continue
        elif 'in re' in doc.case_name.lower():
            continue
        elif doc.case_name == "(White) v. Gray":
            doc.case_name = "White v. Gray"
            if not simulate:
                doc.save()


        # Otherwise, we nuke the leading parens.
        old_case_name = doc.case_name
        new_case_name = titlecase(harmonize(clean_string(re.sub('\(.*?\)', '', doc.case_name, 1))))

        if verbose:
            print "Fixing document %s: %s" % (doc.pk, doc)
            print "        New for %s: %s\n" % (doc.pk, new_case_name)

        if not simulate:
            doc.case_name = new_case_name
            doc.citation.save()


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

    return fixer(simulate, verbose)

if __name__ == '__main__':
    main()
