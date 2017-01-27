# https://github.com/freelawproject/courtlistener/issues/636
import logging
import os

from django.core.management import BaseCommand
from django.db import IntegrityError

from cl.corpus_importer.tasks import download_recap_item
from cl.lib.pacer import PacerXMLParser
from cl.lib.recap_utils import get_ia_document_url_from_path, \
    get_local_document_url_from_path
from cl.search.models import RECAPDocument, Docket
from cl.scrapers.tasks import get_page_count

logger = logging.getLogger(__name__)


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
            logger.info("  Doing docket_entry: %s, document_number, "
                        "%s and attachment number: %s" %
                        (docket_entry, entry_number, attachment_number))
        old_entry_number = int(entry_number)

        try:
            d = RECAPDocument.objects.get(
                docket_entry=docket_entry,
                document_number=old_entry_number,
                attachment_number=attachment_number or None,
            )
            logger.info("    Found item.")
        except RECAPDocument.DoesNotExist:
            logger.info("    Failed to find item.")
            return None

        d.document_number = entry_number
        if d.is_available:
            new_ia = get_ia_document_url_from_path(
                self.path, entry_number, attachment_number)
            logger.info("    Updating IA URL from %s to %s" %
                        (d.filepath_ia, new_ia))
            d.filepath_ia = new_ia

            if not os.path.isfile(d.filepath_local.path):
                # Set the value correctly and get the file from IA if we don't
                # already have it.
                new_local_path = os.path.join(
                    'recap',
                    get_local_document_url_from_path(self.path, entry_number,
                                                     attachment_number),
                )
                logger.info("    Updating local path from %s to %s" %
                            (d.filepath_local, new_local_path))
                d.filepath_local = new_local_path
                filename = d.filepath_ia.rsplit('/', 1)[-1]
                logger.info("    Downloading item with filename %s" % filename)
                if not debug:
                    download_recap_item(d.filepath_ia, filename)
            else:
                logger.info("    File already on disk. Punting.")

            if d.page_count is None:
                logger.info("    Getting page count.")
                extension = d.filepath_local.path.split('.')[-1]
                d.page_count = get_page_count(d.filepath_local.path, extension)
        else:
            logger.info("    Item not available in RECAP. Punting.")
            return None

        if not debug:
            try:
                d.save(do_extraction=True, index=True)
                logger.info("    Item saved at https://www.courtlistener.com%s"
                            % d.get_absolute_url())
            except IntegrityError:
                logger.info("    Integrity error while saving.")
                return None
        else:
            logger.info("    No save requested in debug mode.")

        return d


class Command(BaseCommand):
    help = "Fix issues identified in 636."

    def add_arguments(self, parser):
        parser.add_argument('--debug', dest='debug', action='store_true')
        parser.set_defaults(debug=False)

    def handle(self, *args, **options):
        dockets = Docket.objects.filter(
            docket_entries__recap_documents__ocr_status=RECAPDocument.OCR_FAILED)
        for docket in dockets:
            docket_path = docket.filepath_local.path
            try:
                logger.info("Doing docket at: %s" % docket_path)
                pacer_doc = CleanupPacerXMLParser(docket_path)
            except IOError:
                logger.info("Couldn't find docket at: %s" % docket_path)
            else:
                _ = pacer_doc.make_documents(
                    docket,
                    debug=options['debug'],
                )
