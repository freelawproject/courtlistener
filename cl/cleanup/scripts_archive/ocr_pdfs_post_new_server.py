import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from celery.task.sets import subtask
from alert.search.models import Document
from optparse import OptionParser

# adding alert to the front of this breaks celery. Ignore pylint error.
from scrapers.tasks import extract_doc_content, extract_by_ocr


def fixer(simulate=False, verbose=False):
    """OCR documents that lack content"""
    #docs = queryset_generator(Document.objects.filter(source='C', plain_text=''))
    #docs = Document.objects.raw('''select "pk"  from "Document" where "source" = 'C' and "plain_text" ~ '^[[:space:]]*$' ''')
    docs = Document.objects.raw('''select "pk" from "Document" where "source" = 'C' and "plain_text" = 'Unable to extract document content.' ''')
    for doc in docs:
        if verbose:
            print "Fixing document number %s: %s" % (doc.pk, doc)

        if not simulate:
            # Extract the contents asynchronously.
            extract_doc_content(doc.pk, callback=subtask(extract_by_ocr))

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
