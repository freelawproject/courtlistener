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

from alert.search.models import Document
import csv
from datetime import date
from django.db.models.query import EmptyQuerySet


DATA_DIR = os.path.dirname(__name__)
SCDB_FILENAME = os.path.join(DATA_DIR, 'SCDB_2014_01_caseCentered_Citation.csv')
SCDB_BEGINS = date(1946, 11, 18)
SCDB_ENDS = date(2014, 6, 19)

with open(SCDB_FILENAME) as f:
    dialect = csv.Sniffer().sniff(f.read(1024))
    f.seek(0)
    reader = csv.DictReader(f, dialect=dialect)
    for d in reader:
        # Iterate over every item, looking for matches in various ways.
        ds = EmptyQuerySet()
        if len(ds) == 0:
            ds = Document.objects.filter(
                supreme_court_db_id=d['caseId'])
        if d['usCite'].strip():
            # Only do these lookups if there is in fact a usCite value.
            if len(ds) == 0:
                # None found by supreme_court_db_id. Try by citation number.
                ds = Document.objects.filter(
                    citation__federal_cite_one=d['usCite'])
            if len(ds) == 0:
                ds = Document.objects.filter(
                    citation__federal_cite_two=d['usCite'])
            if len(ds) == 0:
                ds = Document.objects.filter(
                    citation__federal_cite_three=d['usCite'])

        if len(ds) == 0:
            print 'No items found for %s' % d['caseId']
        elif len(ds) == 1:
            print 'Exactly one match found for %s' % d['caseId']
        elif len(ds) > 1:
            print 'Multiple items found for %s (we found %s): (%s)' % \
                  (d['caseId'], len(ds), ', '.join([d.citation.pk for d in ds]))
