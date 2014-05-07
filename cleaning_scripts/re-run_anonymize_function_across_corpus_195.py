import os
import sys
from django.utils.timezone import now

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert.search.models import Document
from alert.lib.db_tools import queryset_generator
from alert.lib.string_utils import anonymize
from optparse import OptionParser
from datetime import date


def cleaner(simulate=False, verbose=False):
    """Re-run the anonymize function across the whole corpus.

    The anonymize function was previously missing any documents that contained
    punctuation before or after an ID. This script re-runs the function, fixing
    the error.
    """
    docs = queryset_generator(Document.objects.all())
    for doc in docs:
        text = doc.plain_text
        clean_lines = []
        any_mods = []
        for line in text.split('\n'):
            clean_line, modified = anonymize(line)
            if modified:
                print "Fixing text in document: %s" % doc.pk
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
            doc.plain_text = '\n'.join(clean_lines)
            doc.blocked = True
            doc.date_blocked = now()
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


if __name__ == '__main__':
    main()
