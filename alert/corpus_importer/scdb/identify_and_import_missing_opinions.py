import argparse
import csv
import glob
import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alert.settings")

from alert.corpus_importer.resource_org.manual_import import \
    import_resource_org_item
from alert.corpus_importer.scdb.merge_scdb import (
    enhance_item_with_scdb, SCDB_FILENAME
)
from alert.search.models import Document


PRO_ROOT = os.path.join('/', 'sources', 'Resource.org', 'data', 'US')


def make_document_for_enhancement(d):
    """Use the SCDB dict to find a PRO item on disk. Make a Document from
    that, then hand that off for processing by the action_one function.
    """
    # Use the citation to find the correct item on disk. The directories look
    # like:     /sources/Resource.org/data/US/99/99.US.668.html
    print "    Attempting to add it from PRO collection at: %s" % PRO_ROOT
    try:
        vol, page = d['usCite'].split(' U.S. ')
    except ValueError:
        # No usCite value. Punt.
        print "     No U.S. citation, cannot proceed."
        return None
    dir_path = os.path.join(PRO_ROOT, vol)
    candidate_files = glob.glob(os.path.join(
        dir_path,
        '%s.US.%s*' % (vol, page))
    )
    if len(candidate_files) == 1:
        # We found it. Import it.
        doc = import_resource_org_item(
            os.path.join(dir_path, candidate_files[0])
        )
        print "Created doc: %s" % doc.pk
    else:
        print "    Unable to find and add a PRO document."
        doc = None
    return doc


def main():
    parser = argparse.ArgumentParser(
        description=(
            'Iterate over the SCDB. If no hits are found for an item, import '
            'it from the public.resource.org corpus.'
        )
    )
    parser.add_argument(
        '-s',
        '--start_id',
        required=True,
        type=int,
        help=(
            'The zero-indexed row ID in the SCDB where we should begin '
            'processing.'
        )
    )
    cli_args = parser.parse_args()
    start_row = cli_args.start_id

    with open(SCDB_FILENAME) as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        reader = csv.DictReader(f, dialect=dialect)
        for i, d in enumerate(reader):
            # Iterate over every item, looking for matches in various ways.
            if i < start_row:
                continue
            print "Row is: %s. ID is: %s" % (i, d['caseId'])
            if d['decisionType'] == '4':
                print "  Punting decision b/c is it is a decree."
                continue

            print "  Checking by caseID...",
            docs = Document.objects.filter(
                supreme_court_db_id=d['caseId'])
            print "%s matches found." % len(docs)

            if len(docs) == 0:
                doc = make_document_for_enhancement(d)
                if doc is not None:
                    enhance_item_with_scdb(doc, d)

if __name__ == '__main__':
    main()
