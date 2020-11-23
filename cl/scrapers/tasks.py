# -*- coding: utf-8 -*-

import logging
import random
import traceback

import requests
from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.utils.timezone import now
from juriscraper.pacer import PacerSession, CaseQuery
from requests import Timeout

from cl.audio.models import Audio
from cl.celery_init import app
from cl.citations.tasks import find_citations_for_opinion_by_pks
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.juriscraper_utils import get_scraper_object_by_name
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.lib.string_utils import anonymize, trunc
from cl.lib.utils import is_iter
from cl.recap.mergers import (
    update_docket_metadata,
    add_bankruptcy_data_to_docket,
)
from cl.scrapers.models import ErrorLog
from cl.scrapers.transformer_extractor_utils import (
    get_page_count,
    document_extract,
    convert_and_clean_audio,
)
from cl.search.models import Opinion, RECAPDocument, Docket
from cl.search.tasks import add_items_to_solr

logger = logging.getLogger(__name__)


def update_document_from_text(opinion):
    """Extract additional metadata from document text

    Use functions from Juriscraper to pull metadata out of opinion
    text. Currently only implemented in Tax, but functional in all
    scrapers via AbstractSite object.

    Note that this updates the values but does not save them. Saving is left to
    the calling function.

    :param opinion: Opinion object
    :return: None
    """
    court = opinion.cluster.docket.court.pk
    site = get_scraper_object_by_name(court)
    if site is None:
        return
    metadata_dict = site.extract_from_text(opinion.plain_text)
    for model_name, data in metadata_dict.items():
        ModelClass = apps.get_model("search.%s" % model_name)
        if model_name == "Docket":
            opinion.cluster.docket.__dict__.update(data)
        elif model_name == "OpinionCluster":
            opinion.cluster.__dict__.update(data)
        elif model_name == "Citation":
            data["cluster_id"] = opinion.cluster_id
            ModelClass.objects.get_or_create(**data)
        else:
            raise NotImplementedError(
                "Object type of %s not yet supported." % model_name
            )


@app.task
def extract_doc_content(pk, do_ocr=False, citation_jitter=False):
    """
    Given an opinion PK, we extract it, sniffing its extension, then store its
    contents in the database.  Finally, we asynchronously find citations in
    the document content and match them to other documents.

    This implementation uses local paths.

    :param pk: The opinion primary key to work on
    :param do_ocr: Whether the PDF converting function should use OCR
    :param citation_jitter: Whether to apply jitter before running the citation
    parsing code. This can be useful do spread these tasks out when doing a
    larger scrape.
    """
    opinion = Opinion.objects.get(pk=pk)

    path = opinion.local_path.path

    extension = path.split(".")[-1]
    response = document_extract(path, do_ocr)
    content = response["content"]
    error = response["err"]
    success = response["error_code"]
    # Do page count, if possible
    opinion.page_count = get_page_count(path)["pg_count"]

    # Do blocked status
    if extension in ["html", "wpd"]:
        opinion.html, blocked = anonymize(content)
    else:
        opinion.plain_text, blocked = anonymize(content)
    if blocked:
        opinion.cluster.blocked = True
        opinion.cluster.date_blocked = now()

    update_document_from_text(opinion)
    if not success:
        print(
            "****Error extracting text from %s: %s****" % (extension, opinion)
        )
        return

    # Save item, and index Solr if needed.
    # noinspection PyBroadException
    try:
        opinion.cluster.docket.save()
        opinion.cluster.save(index=False)
        if not citation_jitter:
            # No waiting around. Save to the database now, but don't bother
            # with the index yet because citations are being done imminently.
            opinion.save(index=False)
        else:
            # Save to the index now, citations come later, commit comes
            # according to schedule
            opinion.save(index=True)
    except Exception:
        print(
            "****Error saving text to the db for: %s****\n%s"
            % (opinion, traceback.format_exc())
        )
        return

    # Identify and link citations within the document content
    find_citations_for_opinion_by_pks.apply_async(
        ([opinion.pk],), countdown=random.randint(0, 3600)
    )


@app.task
def extract_recap_pdf(pks, skip_ocr=False, check_if_needed=True):
    """Extract the contents from a RECAP PDF if necessary."""
    if not is_iter(pks):
        pks = [pks]

    processed = []
    for pk in pks:
        rd = RECAPDocument.objects.get(pk=pk)
        if check_if_needed and not rd.needs_extraction:
            # Early abort if the item doesn't need extraction and the user
            # hasn't disabled early abortion.
            processed.append(pk)
            continue

        path = rd.filepath_local.path
        response = document_extract(path, do_ocr=True)
        content = response["content"]
        err = response["err"]

        if err == Timeout:
            content = u"Unable to extract document content."
            rd.ocr_status = RECAPDocument.OCR_FAILED
        elif len(content.strip()) == 0:
            rd.ocr_status = RECAPDocument.OCR_NEEDED
        else:
            rd.ocr_status = RECAPDocument.OCR_COMPLETE

        rd.plain_text, _ = anonymize(content)
        # Do not do indexing here. Creates race condition in celery.
        rd.save(index=False, do_extraction=False)
        processed.append(pk)

    return processed


def process_audio_file(pk):
    """Given the key to an audio file, extract its content and add the related
    meta data to the database.
    """
    af = Audio.objects.get(pk=pk)
    try:
        response = convert_and_clean_audio(af).json()
        cf = ContentFile(response["content"])
        file_name = trunc(best_case_name(af).lower(), 72) + "_cl.mp3"
        af.file_with_date = af.docket.date_argued
        af.local_path_mp3.save(file_name, cf, save=False)
        af.duration = response["duration"]

    except Timeout:
        ErrorLog.objects.create(
            log_level="CRITICAL",
            court=af.docket.court,
            message="Timeout occurred in docker container for %s" % (af.pk),
        )
    except:
        msg = (
            "Unable to save mp3 to audio_file in scraper.tasks."
            "process_audio_file for item: %s\n"
            "Traceback:\n"
            "%s" % (af.pk, traceback.format_exc())
        )
        print(msg)
        ErrorLog.objects.create(
            log_level="CRITICAL", court=af.docket.court, message=msg
        )
    af.processing_complete = True
    af.save()


@app.task(bind=True, max_retries=2, interval_start=5, interval_step=5)
def update_docket_info_iquery(self, d_pk):
    cookies = get_or_cache_pacer_cookies(
        "pacer_scraper",
        settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    s = PacerSession(
        cookies=cookies,
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    d = Docket.objects.get(pk=d_pk)
    report = CaseQuery(map_cl_to_pacer_id(d.court_id), s)
    try:
        report.query(d.pacer_case_id)
    except (requests.Timeout, requests.RequestException) as exc:
        logger.warning(
            "Timeout or unknown RequestException on iquery crawl. "
            "Trying again if retries not exceeded."
        )
        if self.request.retries == self.max_retries:
            return
        raise self.retry(exc=exc)
    if not report.data:
        return

    d = update_docket_metadata(d, report.data)
    try:
        d.save()
        add_bankruptcy_data_to_docket(d, report.data)
    except IntegrityError as exc:
        msg = "Integrity error while saving iquery response."
        if self.request.retries == self.max_retries:
            logger.warn(msg)
            return
        logger.info(msg=" Retrying.")
        raise self.retry(exc=exc)
    add_items_to_solr([d.pk], "search.Docket")
