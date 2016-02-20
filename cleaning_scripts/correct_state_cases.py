import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert.search.models import Document, Court
from alert.lib.db_tools import queryset_generator
from optparse import OptionParser


def fixer(simulate=False, verbose=False):
    """Fix a few issues discovered."""
    #docs = queryset_generator(Document.objects.filter(source='C', plain_text=''))
    #docs = Document.objects.raw('''select "pk"  from "Document" where "source" = 'C' and "plain_text" ~ '^[[:space:]]*$' ''')
    #docs = Document.objects.raw('''select "pk" from "Document" where "source" = 'C' and "plain_text" = 'Unable to extract document content.' ''')

    def fix_plaintiffs(docs, left, simulate, verbose):
        for doc in docs:
            if verbose:
                print "Fixing document number %s: %s" % (doc.pk, doc)
                old_case_name = doc.case_name
                if left:
                    new_case_name = old_case_name.replace('P. v.', 'People v.')
                else:
                    new_case_name = old_case_name.replace('v. P.', 'v. People')
                print "    Replacing %s" % old_case_name
                print "         with %s" % new_case_name

            if not simulate:
                if left:
                    doc.case_name = doc.case_name.replace('P. v.', 'People v.')
                else:
                    doc.case_name = doc.case_name.replace('v. P.', 'v. People')
                doc.citation.save()

    def fix_michigan(docs, left, simulate, verbose):
        for doc in docs:
            if verbose:
                print "Fixing document number %s: %s" % (doc.pk, doc)
                old_case_name = doc.case_name
                if left:
                    new_case_name = old_case_name.replace('People of Mi', 'People of Michigan')
                print "    Replacing %s" % old_case_name
                print "         with %s" % new_case_name

            if not simulate:
                if left:
                    doc.case_name = doc.case_name.replace('People of Mi', 'People of Michigan')
                doc.citation.save()

    def fix_wva(docs, simulate, verbose):
        for doc in docs:
            if verbose:
                print "Fixing document number %s: %s" % (doc.pk, doc)
            if not simulate:
                doc.precedential_status = "Published"
                doc.save()


    # Round one! Fix plaintiffs.
    print "!!! ROUND ONE !!!"
    court = Court.objects.get(pk='cal')
    docs = queryset_generator(Document.objects.filter(source="C", court=court, citation__case_name__contains='P. v.'))
    fix_plaintiffs(docs, True, simulate, verbose)

    # Round three! Fix the Mi cases.
    print "!!! ROUND THREE !!!"
    court = Court.objects.get(pk='mich')
    docs = queryset_generator(Document.objects.filter(source="C", court=court, citation__case_name__startswith='People of Mi '))
    fix_michigan(docs, True, simulate, verbose)

    # Round four! Fix the statuses.
    print "!!! ROUND FOUR !!!"
    court = Court.objects.get(pk='wva')
    docs = queryset_generator(Document.objects.filter(precedential_status__in=['Memorandum Decision', 'Per Curiam Opinion', 'Signed Opinion'],
                                                      court=court))
    fix_wva(docs, simulate, verbose)



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
