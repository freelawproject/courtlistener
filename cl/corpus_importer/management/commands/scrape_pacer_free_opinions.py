import copy
import hashlib
import logging
import os
from datetime import timedelta, datetime

import internetarchive as ia
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import BaseCommand
from django.utils.encoding import force_bytes
from juriscraper.lib.string_utils import harmonize, CaseNameTweaker
from juriscraper.pacer.http import login

from cl.search.models import Court, DocketEntry, RECAPDocument
from cl.corpus_importer.tasks import get_free_document_report, get_pdf, \
    upload_to_ia
from cl.lib.celery_utils import blocking_queue
from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id, lookup_and_save, \
    get_blocked_status
from cl.lib.recap_utils import get_document_filename, get_bucket_name
from cl.scrapers.models import PACERFreeDocumentLog
from cl.scrapers.tasks import extract_recap_pdf, get_page_count

PACER_USERNAME = os.environ.get('PACER_USERNAME', None)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', None)

logger = logging.getLogger(__name__)

cnt = CaseNameTweaker()


def get_next_date_range(court_id, span=7):
    """Get the next start and end query dates for a court.

    Check the DB for the last date for a court that was completed. Return the
    day after that date + span days into the future as the range to query for
    the requested court.

    :param court_id: A PACER Court ID (not a CL court ID)
    :param span: The number of days to go forward from the last completed date
    """
    court_id = map_pacer_to_cl_id(court_id)
    try:
        last_complete_date = PACERFreeDocumentLog.objects.filter(
            status=PACERFreeDocumentLog.SCRAPE_SUCCESSFUL,
            court_id=court_id,
        ).latest('date_queried').date_queried
    except PACERFreeDocumentLog.DoesNotExist:
        print "FAILED ON: %s" % court_id
        raise
    next_start_date = last_complete_date + timedelta(days=1)
    next_end_date = last_complete_date + timedelta(days=span)
    return next_start_date, next_end_date


def mark_court_done_on_date(court_id, d):
    court_id = map_pacer_to_cl_id(court_id)
    doc = PACERFreeDocumentLog.objects.filter(
        status=PACERFreeDocumentLog.SCRAPE_SUCCESSFUL,
        court_id=court_id,
    ).latest('date_queried')
    doc.date_queried = d
    doc.save()


def go():
    court_ids = [
        map_cl_to_pacer_id(v) for v in Court.objects.filter(
            jurisdiction__in=['FD', 'FB'],
            in_use=True,
            end_date=None,
        ).exclude(
            pk__in=['gub', 'nmib', 'vib', 'prb']  # No PACER site for Guam & N. Mariana
        ).values_list(
            'pk', flat=True
        )
    ]
    pacer_session = login('cand', PACER_USERNAME, PACER_PASSWORD)
    ia_session = ia.get_session({'s3': {
        'access': settings.IA_ACCESS_KEY,
        'secret': settings.IA_SECRET_KEY,
    }})

    # There may be a better way to do this, but this iterates over every court,
    # X days at a time. As courts are completed, they're removed from the list
    # of courts to process until none are left and we exit the outer while loop.
    tomorrow = datetime.today() + timedelta(days=1)
    while len(court_ids) > 0:
        temp_list = list(court_ids)  # Make a copy of the list.
        for court_id in temp_list:
            next_start_date, next_end_date = get_next_date_range(court_id)

            if next_start_date >= tomorrow.date():
                logger.info("Finished '%s'. Marking it complete." % court_id)
                court_ids.remove(court_id)
                continue

            # Make a chain to run the report, get the PDFs and save it all to
            # CL and to Internet Archive.
            # TODO: Figure out an elegant way to keep the status field in the
            # DB updated during the process below.
            # chain(
            #     get_free_document_report_response(court_id, next_date)
            #     download_pdfs(),
            #     save_to_db_question_mark(),
            #     upload_to_ia(),
            # ).delay()
            results = get_free_document_report(court_id, next_start_date,
                                               next_end_date, pacer_session)
            for result in results:
                # Check if we have the PDF already
                try:
                    result.court = Court.objects.get(pk=map_pacer_to_cl_id(court_id))
                except Court.DoesNotExist:
                    logger.error("Could not find court with pk: %s" % court_id)
                    continue

                # Adjust a variety of fields before doing the lookup/merge
                result.case_name = harmonize(result.case_name)
                result.case_name_short = cnt.make_case_name_short(
                    result.case_name)
                result_copy = copy.copy(result)
                # If we don't do this, the doc's date_filed becomes the docket's
                # date_filed. Bad.
                delattr(result_copy, 'date_filed')
                # If we don't do this, we get the PACER court id and it crashes
                delattr(result_copy, 'court_id')
                docket = lookup_and_save(result_copy)
                if not docket:
                    logger.error("Unable to create docket for %s" % result)
                    continue
                docket.blocked, docket.date_blocked = get_blocked_status(docket)
                docket.save()

                try:
                    docket_entry = DocketEntry.objects.get(
                        docket=docket,
                        entry_number=result.document_number,
                    )
                except DocketEntry.DoesNotExist:
                    docket_entry = DocketEntry(
                        docket=docket,
                        entry_number=result.document_number,
                    )
                docket_entry.date_filed = result.date_filed
                docket_entry.description = result.description
                docket_entry.save()

                try:
                    rd = RECAPDocument.objects.get(
                        docket_entry=docket_entry,
                        document_number=result.document_number,
                        attachment_number=None,
                    )
                except RECAPDocument.DoesNotExist:
                    rd = RECAPDocument(
                        docket_entry=docket_entry,
                        document_number=result.document_number,
                        attachment_number=None,
                    )
                else:
                    if rd.is_available:
                        logger.info("Found the item already in the DB with "
                                    "document_number: %s and docket_entry: "
                                    "%s!" % (result.document_number,
                                             docket_entry))
                        continue
                rd.pacer_doc_id = result.pacer_doc_id
                rd.document_type = RECAPDocument.PACER_DOCUMENT

                response = get_pdf(result, court_id, pacer_session)
                file_name = get_document_filename(
                    result.court.pk,
                    result.pacer_case_id,
                    result.document_number,
                    0,  # Attachment number is zero for all free opinions.
                )
                cf = ContentFile(response.content)
                rd.filepath_local.save(file_name, cf, save=False)
                rd.is_available = True  # We've got the PDF.

                # request.content is sometimes a str, sometimes unicode, so
                # force it all to be bytes, pleasing hashlib.
                rd.sha1 = hashlib.sha1(force_bytes(response.content)).hexdigest()
                rd.is_free_on_pacer = True
                rd.page_count = get_page_count(rd.filepath_local.path, 'pdf')

                # Save and extract, skipping OCR.
                rd.save(do_extraction=False, index=False)
                extract_recap_pdf(rd.pk, skip_ocr=True, check_if_needed=False)

                # Upload to IA and set filepath_ia
                bucket_name = get_bucket_name(result.court.pk,
                                              result.pacer_case_id)
                responses = upload_to_ia(
                    identifier=bucket_name,
                    files=rd.filepath_local.path,
                    metadata={
                        'title': result.case_name,
                        'collection': settings.IA_COLLECTIONS,
                        'contributor': '<a href="https://free.law">Free Law Project</a>',
                        'court': result.court.pk,
                        'language': 'eng',
                        'mediatype': 'texts',
                        'description': "This item represents a case in PACER, "
                                       "the U.S. Government's website for "
                                       "federal case data. If you wish to see "
                                       "the entire case, please consult PACER "
                                       "directly.",
                        'licenseurl': 'https://www.usa.gov/government-works',
                    },
                    session=ia_session,
                )
                if all(r.ok for r in responses):
                    rd.filepath_ia = "https://archive.org/download/%s/%s" % (
                        bucket_name, file_name)
                    rd.save(do_extraction=False, index=False)

            mark_court_done_on_date(court_id, next_end_date)


class Command(BaseCommand):
    help = "Get all the free content from PACER."

    def handle(self, *args, **options):
        go()
