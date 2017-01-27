# https://github.com/freelawproject/courtlistener/issues/636
import os

from django.core.management import BaseCommand
from django.db import IntegrityError

from cl.corpus_importer.tasks import download_recap_item
from cl.lib.pacer import PacerXMLParser
from cl.lib.recap_utils import get_ia_document_url_from_path, \
    get_local_document_url_from_path
from cl.search.models import RECAPDocument
from cl.scrapers.tasks import get_page_count


class CleanupPacerXMLParser(PacerXMLParser):
    """Overrides the normal parser with one that does cleanup properly."""

    def make_recap_document(self, doc_node, docket_entry, entry_number,
                            attachment_number, document_type, debug):
        """Do nothing for items that don't start with zero. For ones that do,
        find the stripped version, fix it, download the correct item, extract
        it and finally save it to Solr.
        """

        if not entry_number.startswith('0'):
            # Only touch things where the new value leads with a zero.
            return None
        else:
            print "  Doing docket_entry: %s, document_number, " \
                  "%s and attachment number: %s" % (docket_entry, entry_number,
                                                    attachment_number)
        old_entry_number = int(entry_number)

        try:
            d = RECAPDocument.objects.get(
                docket_entry=docket_entry,
                document_number=old_entry_number,
                attachment_number=attachment_number or None,
            )
            print "    Found item."
        except RECAPDocument.DoesNotExist:
            print "    Failed to find item."
            return None

        d.document_number = entry_number
        if d.is_available:
            new_ia = get_ia_document_url_from_path(
                self.path, entry_number, attachment_number)
            print "    Updating IA URL from %s to %s" % (d.filepath_ia, new_ia)
            d.filepath_ia = new_ia

            if not os.path.isfile(d.filepath_local.path):
                # Set the value correctly and get the file from IA if we don't
                # already have it.
                new_local_path = os.path.join(
                    'recap',
                    get_local_document_url_from_path(self.path, entry_number,
                                                     attachment_number),
                )
                print "    Updating local path from %s to %s" % (
                    d.filepath_local, new_local_path)
                d.filepath_local = new_local_path
                filename = d.filepath_ia.rsplit('/', 1)[-1]
                print "    Downloading item with filename %s" % filename
                download_recap_item(d.filepath_ia, filename)
            else:
                print "    File already on disk. Punting."
                return None

            if d.page_count is None:
                print "    Getting page count."
                extension = d.filepath_local.path.split('.')[-1]
                d.page_count = get_page_count(d.filepath_local.path, extension)
        else:
            print "    Item not available in RECAP. Punting."
            return None

        if not debug:
            try:
                d.save(do_extraction=True, index=True)
                print "    Item saved successfully at " \
                      "https://www.courtlistener.com%s" % d.get_absolute_url()
            except IntegrityError:
                print "    Integrity error while saving."
                return None
        else:
            print "    No save requested in debug mode."

        return d


class Command(BaseCommand):
    help = "Fix issues identified in 636."

    def add_arguments(self, parser):
        parser.add_argument('--debug', dest='debug', action='store_true')
        parser.set_defaults(debug=False)

    def handle(self, *args, **options):
        docs = RECAPDocument.objects.filter(ocr_status=RECAPDocument.OCR_FAILED)
        for doc in docs:
            docket_path = doc.docket_entry.docket.filepath_local.path
            try:
                print "Doing docket at: %s" % docket_path
                pacer_doc = CleanupPacerXMLParser(docket_path)
            except IOError:
                print "Couldn't find docket at: %s" % docket_path
            else:
                _ = pacer_doc.make_documents(
                    doc.docket_entry.docket,
                    debug=options['debug'],
                )
