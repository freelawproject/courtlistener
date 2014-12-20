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
from datetime import date, datetime
from django.db.models.query import EmptyQuerySet


DATA_DIR = os.path.dirname(__name__)
SCDB_FILENAME = os.path.join(DATA_DIR, 'SCDB_2014_01_caseCentered_Citation.csv')
SCDB_BEGINS = date(1946, 11, 18)
SCDB_ENDS = date(2014, 6, 19)

START_ROW = 7368
DEBUG = False

# Relevant numbers:
#  - 7907: After this point we don't seem to have any citations for items.

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


def enhance_item_with_scdb(doc, scdb_info):
    """Good news: A single Document object was found for the SCDB record.

    Take that item and enhance it with the SCDB content.
    """
    c = doc.citation
    c.federal_cite_one = scdb_info['usCite']
    c.federal_cite_two = scdb_info['sctCite']
    c.federal_cite_three = scdb_info['ledCite']
    c.lexis_cite = scdb_info['lexisCite']
    c.docket_number = scdb_info['docket']
    doc.supreme_court_db_id = scdb_info['caseId']

    if not DEBUG:
        c.save()
        doc.save()


def winnow_by_docket_number(docs, d):
    """Go through each of the docs and see if they have a matching docket
    number. Return only those oness that do.
    """
    good_doc_ids = []
    for doc in docs:
        dn = doc.citation.docket_number
        if dn is not None:
            dn = dn.replace(', Original', ' ORIG')
            dn = dn.replace('___, ORIGINAL', 'ORIG')
            dn = dn.replace(', Orig', ' ORIG')
            dn = dn.replace(', Misc', ' M')
            dn = dn.replace(' Misc', ' M')
            dn = dn.replace('NO. ', '')
            if dn == d['docket']:
                good_doc_ids.append(doc.pk)

    # Convert our list of IDs back into a QuerySet for consistency.
    return Document.objects.filter(pk__in=good_doc_ids)

with open(SCDB_FILENAME) as f:
    dialect = csv.Sniffer().sniff(f.read(1024))
    f.seek(0)
    reader = csv.DictReader(f, dialect=dialect)
    for i, d in enumerate(reader):
        # Iterate over every item, looking for matches in various ways.
        if i < START_ROW:
            continue
        print "Row is: %s. ID is: %s" % (i, d['caseId'])

        docs = EmptyQuerySet()
        if len(docs) == 0:
            print "  Checking by caseID...",
            docs = Document.objects.filter(
                supreme_court_db_id=d['caseId'])
            print "%s matches found." % len(docs)
        if d['usCite'].strip():
            # Only do these lookups if there is in fact a usCite value.
            if len(docs) == 0:
                # None found by supreme_court_db_id. Try by citation number.
                print "  Checking by federal_cite_one..",
                docs = Document.objects.filter(
                    citation__federal_cite_one=d['usCite'])
                print "%s matches found." % len(docs)
            if len(docs) == 0:
                print "  Checking by federal_cite_one...",
                docs = Document.objects.filter(
                    citation__federal_cite_two=d['usCite'])
                print "%s matches found." % len(docs)
            if len(docs) == 0:
                print "  Checking by federal_cite_three...",
                docs = Document.objects.filter(
                    citation__federal_cite_three=d['usCite'])
                print "%s matches found." % len(docs)

            # At this point, we need to start getting more experimental b/c
            # the easy ways to find items did not work. Items matched here are
            # ones that lack citations.
            if len(docs) == 0:
                # try by date and then winnow by docket number
                print "  Checking by date...",
                docs = Document.objects.filter(
                    date_filed=datetime.strptime(
                        d['dateDecision'], '%m/%d/%Y'
                    ),
                    docket__court_id='scotus',
                )
                print "%s matches found." % len(docs)
                print "    Winnowing by docket number...",
                docs = winnow_by_docket_number(docs, d)
                print "%s matches found." % len(docs)

                if len(docs) == 1:
                    print '      Docket numbers: %s, %s' % \
                          (docs[0].citation.docket_number, d['docket'])
                    print '      Case names:'
                    print '        DB: %s (%s)' % (docs[0].citation.case_name, docs[0].pk)
                    print '        SCDB: %s' % d['caseName']
                    good_match = raw_input('    Is this a good match [y/n]: ')
                    if good_match == 'y':
                        pass
                    else:
                        # No good. Press forward with no items.
                        docs = EmptyQuerySet()

        if len(docs) == 0:
            print '  No items found.'
        elif len(docs) == 1:
            print '  Exactly one match found.'
            print '    --> Enhancing document %s with data from SCDB.' % docs[0].pk
            enhance_item_with_scdb(docs[0], d)
        else:
            print '  %s items found:' % len(docs)
            for j, doc in enumerate(docs):
                print '    %s: Document %s:' % (j, doc.pk)
                print '      https://www.courtlistener.com/opinion/%s/slug/' % doc.pk
                print '      %s' % doc.citation.case_name
                print '      %s' % doc.citation.docket_number
            print '  SCDB info:'
            print '    %s' % d['caseName']
            print '    %s' % d['docket']

            choice = raw_input('  Which item should we update? [0-%s] ' %
                               (len(docs) - 1))
            try:
                choice = int(choice)
                print '    --> Enhancing document %s with data from SCDB.' % \
                      docs[choice].pk
                enhance_item_with_scdb(docs[choice], d)
            except ValueError:
                print '  OK. No changes will be made.'
