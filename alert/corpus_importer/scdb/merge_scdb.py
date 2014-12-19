"""
Process here will be to iterate over every item in the SCDB and to locate it in
CourtListener.

Location is done by:
 - Looking in the `supreme_court_db_id` field. During the first run of this
   program we expect this to fail for all items since they will not have this
   field populated yet. During subsequent runs, this field will have hits and
   will provide improved performance.
 - Looking for matching U.S. and docket number.

Once located, we update items:
 - Case name -- will this automatically fix the docket as well?
 - Citations (Lexis, US, L.Ed., etc.)
 - Docket number?
 - supreme_court_db_id
"""
import os
import sys
execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alert.settings")

from alert.citations.tasks import update_document_by_id
from alert.search.models import Document
import csv
from datetime import date
from django.db.models.query import EmptyQuerySet


DATA_DIR = os.path.dirname(__name__)
SCDB_FILENAME = os.path.join(DATA_DIR, 'SCDB_2014_01_caseCentered_Citation.csv')
SCDB_BEGINS = date(1946, 11, 18)
SCDB_ENDS = date(2014, 6, 19)
START_ROW = 171


def merge_docs(first_pk, second_pk):
    first = Document.objects.get(pk=first_pk)
    second = Document.objects.get(pk=second_pk)
    first.source = 'LR'
    first.judges = second.judges
    first.html_lawbox = second.html_lawbox
    first.save()
    first.citation.case_name = second.citation.case_name
    first.citation.slug = second.citation.slug
    first.citation.save()
    second.docket.delete()
    second.citation.delete()
    second.delete()
    update_document_by_id(first_pk)


with open(SCDB_FILENAME) as f:
    dialect = csv.Sniffer().sniff(f.read(1024))
    f.seek(0)
    reader = csv.DictReader(f, dialect=dialect)
    for i, d in enumerate(reader):
        # Iterate over every item, looking for matches in various ways.
        if i < START_ROW:
            continue
        print "Row is: %s. ID is: %s" % (i, d['caseId'])

        ds = EmptyQuerySet()
        if len(ds) == 0:
            print "  Checking by caseID...",
            ds = Document.objects.filter(
                supreme_court_db_id=d['caseId'])
            print "%s matches found." % len(ds)
        if d['usCite'].strip():
            # Only do these lookups if there is in fact a usCite value.
            if len(ds) == 0:
                # None found by supreme_court_db_id. Try by citation number.
                print "  Checking by federal_cite_one..",
                ds = Document.objects.filter(
                    citation__federal_cite_one=d['usCite'])
                print "%s matches found." % len(ds)
            if len(ds) == 0:
                print "  Checking by federal_cite_one...",
                ds = Document.objects.filter(
                    citation__federal_cite_two=d['usCite'])
                print "%s matches found." % len(ds)
            if len(ds) == 0:
                print "  Checking by federal_cite_three...",
                ds = Document.objects.filter(
                    citation__federal_cite_three=d['usCite'])
                print "%s matches found." % len(ds)

        if len(ds) == 0:
            print '  No items found.'
        elif len(ds) == 1:
            print '  Exactly one match found.'
        elif len(ds) == 2:
            print '  Two items found.'
            print '    Absolute URLs:\n      %s' % '\n      '.join([
                'https://www.courtlistener.com/opinion/%s/slug/' % d.pk
                for d in ds])
            proceed = raw_input("Should we merge these? (Ctrl+C to quit, or "
                                "Enter to merge.")
            merge_docs(first_pk=ds[0], second_pk=ds[1])
