import logging
import random
import re
import traceback
from collections import defaultdict
from io import BytesIO

import celery
import httpx
import openai
import requests
from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.files.base import ContentFile
from httpx import Response
from juriscraper.lib.exceptions import PacerLoginException
from juriscraper.pacer import CaseQuery
from redis import ConnectionError as RedisConnectionError

from cl.audio.models import Audio
from cl.celery_init import app
from cl.citations.tasks import (
    find_citations_and_parentheticals_for_opinion_by_pks,
)
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.celery_utils import throttle_task
from cl.lib.exceptions import ScrapeFailed
from cl.lib.juriscraper_utils import get_scraper_object_by_name
from cl.lib.llm import call_llm_transcription
from cl.lib.microservice_utils import microservice
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.pacer_session import ProxyPacerSession, get_or_cache_pacer_cookies
from cl.lib.privacy_tools import anonymize, set_blocked_status
from cl.lib.recap_utils import needs_ocr
from cl.lib.string_utils import trunc
from cl.lib.utils import is_iter
from cl.recap.mergers import save_iquery_to_docket
from cl.scrapers.management.commands.merge_opinion_versions import (
    get_query_from_url,
    merge_versions_by_text_similarity,
)
from cl.scrapers.utils import citation_is_duplicated, make_citation
from cl.search.models import (
    SOURCES,
    Docket,
    Opinion,
    OriginatingCourtInformation,
    RECAPDocument,
)

logger = logging.getLogger(__name__)

ExtractProcessResult = tuple[str, str | None]


def update_document_from_text(
    opinion: Opinion, juriscraper_module: str = ""
) -> dict:
    """Extract additional metadata from document text

    Note that this updates the values but does not save them for Docket,
    OpinionCluster, Opinion and OriginatingCourtInformation. Saving is left to
    the calling function. It does save Citations

    :param opinion: Opinion object
    :param juriscraper_module: full module to get Site object
    :return: the extracted data dictionary
    """
    court_id = opinion.cluster.docket.court.pk
    site = get_scraper_object_by_name(court_id, juriscraper_module)
    if site is None:
        logger.debug("No site found %s", juriscraper_module)
        return {}

    citation_created = False
    metadata_dict = site.extract_from_text(opinion.plain_text or opinion.html)
    for model_name, data in metadata_dict.items():
        if model_name == "Docket":
            if data.get("docket_number"):
                data["docket_number_raw"] = data["docket_number"]
            opinion.cluster.docket.__dict__.update(data)
        elif model_name == "OpinionCluster":
            opinion.cluster.__dict__.update(data)
        elif model_name == "Citation":
            citation = make_citation(data, opinion.cluster, court_id)
            if not citation or citation_is_duplicated(citation, data):
                continue
            citation.save()
            citation_created = True
        elif model_name == "Opinion":
            opinion.__dict__.update(data)
        elif model_name == "OriginatingCourtInformation":
            docket = opinion.cluster.docket
            if docket.originating_court_information:
                docket.originating_court_information.__dict__.update(data)
            else:
                docket.originating_court_information = (
                    OriginatingCourtInformation(**data)
                )

        else:
            raise NotImplementedError(
                f"Object type of {model_name} not yet supported."
            )

    # if the candidate citation was saved successfully, it will have an id
    metadata_dict["citation_created"] = citation_created

    return metadata_dict


@app.task(
    bind=True,
    autoretry_for=(httpx.ConnectError, httpx.ReadTimeout),
    max_retries=5,
    retry_backoff=10,
)
def extract_opinion_content(
    self,
    pk: int,
    juriscraper_module: str = "",
    ocr_available: bool = False,
    percolate_opinion: bool = False,
) -> None:
    """
    Given an opinion PK, we extract it, sniffing its extension, then store its
    contents in the database.  Finally, we asynchronously find citations in
    the document content and match them to other documents.

    This implementation uses local paths.

    After reviewing some related errors on Sentry we realized that some
    opinions that didn't need OCR were being extracted using OCR.

    Doctor has a method to decide if a document should be extracted using OCR
    that works by checking if the document contains images. The problem with
    that is if a PDF that its content is mostly text contains an image (like a
    stamp or a signature) it'll be fully converted to images to then be
    extracted using OCR. That's not good in large documents due to the
    unnecessary use of resources.

    That's why it's better to first try to extract the content without OCR,
    then if the extraction doesn't return any content try to extract it using
    OCR.
    That means that we'll only use OCR for those PDF documents that are fully
    composed of images.

    Note that this approach won't work well for those documents with mixed
    content (text pages + images pages) in these cases we'll only extract the
    text content. Fortunately seems that documents like those are not too
    common.

    :param self: The Celery task
    :param pk: The opinion primary key to work on
    :param juriscraper_module: the full module string to re-import a Site object
    :param ocr_available: Whether the PDF converting function should use OCR
    :param percolate_opinion: Whether to percolate the related opinion document in
    order to trigger search alerts.
    larger scrape.
    """

    opinion = Opinion.objects.get(pk=pk)

    # Try to extract opinion content without using OCR.
    response = async_to_sync(microservice)(
        service="document-extract",
        item=opinion,
    )
    if not response.is_success:
        logger.error(
            "Error from document-extract microservice: %s",
            response.status_code,
            extra=dict(
                opinion_id=opinion.id,
                url=opinion.download_url,
                local_path=opinion.local_path.name,
                fingerprint=[
                    f"{opinion.cluster.docket.court_id}-document-extract-failure"
                ],
            ),
        )
        return

    content = response.json()["content"]
    extracted_by_ocr = response.json()["extracted_by_ocr"]
    # For PDF documents, if there's no content after the extraction without OCR
    # Let's try to extract using OCR.
    if (
        ocr_available
        and needs_ocr(content)
        and ".pdf" in str(opinion.local_path)
    ):
        response = async_to_sync(microservice)(
            service="document-extract-ocr",
            item=opinion,
            params={"ocr_available": ocr_available},
        )
        if response.is_success:
            content = response.json()["content"]
            extracted_by_ocr = True

    data = response.json()
    extension = opinion.local_path.name.split(".")[-1]
    opinion.extracted_by_ocr = extracted_by_ocr

    if data["page_count"]:
        opinion.page_count = data["page_count"]

    assert isinstance(content, str), (
        f"content must be of type str, not {type(content)}"
    )

    set_blocked_status(opinion, content, extension)
    update_document_from_text(opinion, juriscraper_module)

    if data["err"]:
        logger.error(
            "****Error: %s, extracting text from %s: %s****",
            data["err"],
            extension,
            opinion,
        )
        return

    # Save item
    # noinspection PyBroadException
    try:
        if opinion.cluster.docket.originating_court_information:
            opinion.cluster.docket.originating_court_information.save()

        opinion.cluster.docket.save()
        opinion.cluster.save()
        opinion.save()
    except Exception:
        logger.error(
            "****Error saving text to the db for: %s****\n%s",
            opinion,
            traceback.format_exc(),
        )
        return

    find_and_merge_versions.delay(pk=opinion.id)

    # Identify and link citations within the document content
    find_citations_and_parentheticals_for_opinion_by_pks.apply_async(
        ([opinion.pk], False, False, percolate_opinion)
    )


# TODO: Remove after the new extract_opinion_content is deployed.
@app.task(
    bind=True,
    autoretry_for=(httpx.ConnectError, httpx.ReadTimeout),
    max_retries=5,
    retry_backoff=10,
)
def extract_doc_content(
    self,
    pk: int,
    juriscraper_module: str = "",
    ocr_available: bool = False,
    citation_jitter: bool = False,
) -> None:
    """
    Given an opinion PK, we extract it, sniffing its extension, then store its
    contents in the database.  Finally, we asynchronously find citations in
    the document content and match them to other documents.

    This implementation uses local paths.

    After reviewing some related errors on Sentry we realized that some
    opinions that didn't need OCR were being extracted using OCR.

    Doctor has a method to decide if a document should be extracted using OCR
    that works by checking if the document contains images. The problem with
    that is if a PDF that its content is mostly text contains an image (like a
    stamp or a signature) it'll be fully converted to images to then be
    extracted using OCR. That's not good in large documents due to the
    unnecessary use of resources.

    That's why it's better to first try to extract the content without OCR,
    then if the extraction doesn't return any content try to extract it using
    OCR.
    That means that we'll only use OCR for those PDF documents that are fully
    composed of images.

    Note that this approach won't work well for those documents with mixed
    content (text pages + images pages) in these cases we'll only extract the
    text content. Fortunately seems that documents like those are not too
    common.

    :param self: The Celery task
    :param pk: The opinion primary key to work on
    :param juriscraper_module: the full module string to re-import a Site object
    :param ocr_available: Whether the PDF converting function should use OCR
    :param citation_jitter: Whether to apply jitter before running the citation
    parsing code. This can be useful do spread these tasks out when doing a
    larger scrape.
    """

    opinion = Opinion.objects.get(pk=pk)

    # Try to extract opinion content without using OCR.
    response = async_to_sync(microservice)(
        service="document-extract",
        item=opinion,
    )
    if not response.is_success:
        logger.error(
            "Error from document-extract microservice: %s",
            response.status_code,
            extra=dict(
                opinion_id=opinion.id,
                url=opinion.download_url,
                local_path=opinion.local_path.name,
                fingerprint=[
                    f"{opinion.cluster.docket.court_id}-document-extract-failure"
                ],
            ),
        )
        return

    content = response.json()["content"]
    extracted_by_ocr = response.json()["extracted_by_ocr"]
    # For PDF documents, if there's no content after the extraction without OCR
    # Let's try to extract using OCR.
    if (
        ocr_available
        and needs_ocr(content)
        and ".pdf" in str(opinion.local_path)
    ):
        response = async_to_sync(microservice)(
            service="document-extract-ocr",
            item=opinion,
            params={"ocr_available": ocr_available},
        )
        if response.is_success:
            content = response.json()["content"]
            extracted_by_ocr = True

    data = response.json()
    extension = opinion.local_path.name.split(".")[-1]
    opinion.extracted_by_ocr = extracted_by_ocr

    if data["page_count"]:
        opinion.page_count = data["page_count"]

    assert isinstance(content, str), (
        f"content must be of type str, not {type(content)}"
    )

    set_blocked_status(opinion, content, extension)
    update_document_from_text(opinion, juriscraper_module)

    if data["err"]:
        logger.error(
            "****Error: %s, extracting text from %s: %s****",
            data["err"],
            extension,
            opinion,
        )
        return

    # Save item
    # noinspection PyBroadException
    try:
        if opinion.cluster.docket.originating_court_information:
            opinion.cluster.docket.originating_court_information.save()

        opinion.cluster.docket.save()
        opinion.cluster.save()
        opinion.save()
    except Exception:
        logger.error(
            "****Error saving text to the db for: %s****\n%s",
            opinion,
            traceback.format_exc(),
        )
        return

    find_and_merge_versions.delay(pk=opinion.id)

    # Identify and link citations within the document content
    find_citations_and_parentheticals_for_opinion_by_pks.apply_async(
        ([opinion.pk],), countdown=random.randint(0, 3600)
    )


@app.task(bind=True)
def find_and_merge_versions(self, pk: int) -> None:
    """Find versions of the `pk` opinion, and try to merge them

    Since this relies on text similarity, we are calling it from
    `extract_opinion_content`

    Currently only checks for exact `download_url` match, update this when
    different strategies are implemented

    :param self: the celery task
    :param pk: opinion primary key
    :return None:
    """
    recently_scraped_opinion = Opinion.objects.get(id=pk)
    if not recently_scraped_opinion.download_url:
        return
    query = get_query_from_url(recently_scraped_opinion.download_url, "exact")
    versions = (
        Opinion.objects.filter(query)
        .filter(cluster__source=SOURCES.COURT_WEBSITE)
        .exclude(id=pk)
        .exclude(main_version__isnull=False)
        .order_by("-date_created")
    )

    # versions are ordered in descending date_created, we keep the latest
    # creation as the main version, since we expect it to be freshest
    # from the court's server. Since this task is called on a scrape, we assume
    # that is the most recent
    if versions.exists():
        stats = defaultdict(lambda: 0)
        merge_versions_by_text_similarity(
            recently_scraped_opinion, versions, stats
        )
        logger.debug(stats)


@app.task(
    bind=True,
    autoretry_for=(
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
    ),
    max_retries=3,
    retry_backoff=10,
)
def extract_recap_pdf(
    self,
    pks: int | list[int],
    ocr_available: bool = True,
    check_if_needed: bool = True,
) -> list[int]:
    """Celery task wrapper for extract_recap_pdf_base
    Extract the contents from a RECAP PDF if necessary.

    In order to avoid the issue described here:
    https://github.com/freelawproject/courtlistener/issues/2103#issuecomment-1206700403

    If a Celery task is called as a synchronous function within another parent
    task when it fails the parent task will be retried and every retry logged
    to sentry.

    To avoid logging every retry to sentry a new base method was created:
    extract_recap_pdf_base that method should be used when a synchronous call
    is needed within a parent task.

    And this task wrapper should be used elsewhere for asynchronous calls
    (delay, async).

    :param pks: The RECAPDocument pk or list of pks to work on.
    :param ocr_available: Whether it's needed to perform OCR extraction.
    :param check_if_needed: Whether it's needed to check if the RECAPDocument
    needs extraction.

    :return: A list of processed RECAPDocument
    """

    return async_to_sync(extract_recap_pdf_base)(
        pks, ocr_available, check_if_needed
    )


async def extract_recap_pdf_base(
    pks: int | list[int],
    ocr_available: bool = True,
    check_if_needed: bool = True,
) -> list[int]:
    """Extract the contents from a RECAP PDF if necessary.

    :param pks: The RECAPDocument pk or list of pks to work on.
    :param ocr_available: Whether it's needed to perform OCR extraction.
    :param check_if_needed: Whether it's needed to check if the RECAPDocument
    needs extraction.

    :return: A list of processed RECAPDocument
    """

    if not is_iter(pks):
        pks = [pks]

    processed: list[int] = []
    for pk in pks:
        rd = await RECAPDocument.objects.aget(pk=pk)
        if check_if_needed and not rd.needs_extraction:
            # Early abort if the item doesn't need extraction and the user
            # hasn't disabled early abortion.
            processed.append(pk)
            continue

        response = await microservice(
            service="document-extract",
            item=rd,
        )
        if not response.is_success:
            continue

        content = response.json()["content"]
        extracted_by_ocr = response.json()["extracted_by_ocr"]
        ocr_needed = needs_ocr(content, page_count=rd.page_count)
        if ocr_available and ocr_needed:
            response = await microservice(
                service="document-extract-ocr",
                item=rd,
                params={"ocr_available": ocr_available},
            )
            if response.is_success:
                content = response.json()["content"]
                extracted_by_ocr = True

        has_content = bool(content)
        match has_content, extracted_by_ocr:
            case True, True:
                rd.ocr_status = RECAPDocument.OCR_COMPLETE
            case True, False:
                if not ocr_needed:
                    rd.ocr_status = RECAPDocument.OCR_UNNECESSARY
            case False, True:
                rd.ocr_status = RECAPDocument.OCR_FAILED
            case False, False:
                rd.ocr_status = RECAPDocument.OCR_NEEDED

        rd.plain_text, _ = anonymize(content)
        await rd.asave(
            do_extraction=False,
            update_fields=["ocr_status", "plain_text"],
        )
        processed.append(pk)

    return processed


@app.task(
    bind=True,
    autoretry_for=(
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.TimeoutException,
    ),
    max_retries=3,
    retry_backoff=10,
)
@throttle_task("1/3m")
def process_audio_file(self, pk) -> None:
    """Given the key to an audio file, extract its content and add the related
    meta data to the database.

    :param self: A Celery task object
    :param pk: Audio file pk
    :return: None
    """
    audio_obj = Audio.objects.get(pk=pk)
    date_argued = audio_obj.docket.date_argued
    if date_argued:
        date_argued_str = date_argued.strftime("%Y-%m-%d")
        date_argued_year = date_argued.year
    else:
        date_argued_str, date_argued_year = None, None

    audio_data = {
        "court_full_name": audio_obj.docket.court.full_name,
        "court_short_name": audio_obj.docket.court.short_name,
        "court_pk": audio_obj.docket.court.pk,
        "court_url": audio_obj.docket.court.url,
        "docket_number": audio_obj.docket.docket_number,
        "date_argued": date_argued_str,
        "date_argued_year": date_argued_year,
        "case_name": audio_obj.case_name,
        "case_name_full": audio_obj.case_name_full,
        "case_name_short": audio_obj.case_name_short,
        "download_url": audio_obj.download_url,
    }
    audio_response: Response = async_to_sync(microservice)(
        service="convert-audio",
        item=audio_obj,
        params=audio_data,
    )
    audio_response.raise_for_status()
    cf = ContentFile(audio_response.content)
    file_name = f"{trunc(best_case_name(audio_obj).lower(), 72)}_cl.mp3"
    audio_obj.file_with_date = audio_obj.docket.date_argued
    audio_obj.local_path_mp3.save(file_name, cf, save=False)
    audio_obj.duration = float(
        async_to_sync(microservice)(
            service="audio-duration",
            file=audio_response.content,
            file_type="mp3",
        ).text
    )
    audio_obj.processing_complete = True
    audio_obj.save(
        update_fields=[
            "duration",
            "local_path_mp3",
            "processing_complete",
        ]
    )


@app.task(
    bind=True,
    autoretry_for=(PacerLoginException, RedisConnectionError),
    max_retries=3,
    interval_start=5,
    interval_step=5,
)
@throttle_task("1/s", key="court_id")
def update_docket_info_iquery(self, d_pk: int, court_id: str) -> None:
    """Update the docket info from iquery

    :param self: The Celery task
    :param d_pk: The ID of the docket
    :param court_id: The court of the docket. Needed for throttling by court.
    :return: None
    """
    session_data = async_to_sync(get_or_cache_pacer_cookies)(
        "pacer_scraper",
        settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    s = ProxyPacerSession(
        cookies=session_data.cookies,
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
        proxy=session_data.proxy_address,
    )
    d = Docket.objects.get(pk=d_pk, court_id=court_id)
    report = CaseQuery(map_cl_to_pacer_id(d.court_id), s)
    try:
        async_to_sync(report.query)(d.pacer_case_id)
    except (httpx.Timeout, httpx.RequestError) as exc:
        logger.warning(
            "Timeout or unknown RequestException on iquery crawl. "
            "Trying again if retries not exceeded."
        )
        if self.request.retries == self.max_retries:
            return
        raise self.retry(exc=exc)
    if not report.data:
        return

    save_iquery_to_docket(
        self,
        report.data,
        report.response.text,
        d,
        tag_names=None,
        skip_iquery_sweep=True,
    )


def process_scotus_captcha_transcription(transcription: str) -> str:
    """Converts the transcription of a SCOTUS audio CAPTCHA into a list of five alphanumeric characters. Throws an error if it is unable to do so.

    SCOTUS audio CAPTCHAs consist of three alphanumeric characters read out using the NATO phonetic alphabet. This makes extracting them from a transcription quite easy. The main challenge is that certain transcription models may choose odd spellings of certain phonetic characters, alternatively spell or not spell numbers, and insert punctuation in arbitrary locations. This method attempts to deal with all of those.

    :param transcription: The transcription of the CAPTCHA.
    :return: The alphanumeric characters extracted from the transcription."""

    numeric_map = {
        "zero": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
    }

    words = [
        re.sub(r"\W+", "", word) for word in transcription.lower().split(" ")
    ]

    if len(words) != 5:
        raise ValueError(f"Expected 5 words, got {len(words)}")
    if any([len(word) == 0 for word in words]):
        raise ValueError("Expected all words to be non-empty")

    characters = [
        numeric_map[word] if word in numeric_map else word[0] for word in words
    ]

    return "".join(characters)


@app.task(bind=True, max_retries=3, autoretry_for=(ScrapeFailed,))
@throttle_task("1/m")
def subscribe_to_scotus_updates(self: celery.Task, pk: int) -> None:
    """Subscribe to SCOTUS email updates for a given opinion.

    :param self: The celery task
    :param pk: The primary key of the Docket object to subscribe for.
    :return: None
    :raises ScrapeFailed: If the subscription form could not be found, the CAPTCHA could not be solved, a JSON response
    could not be decoded, or the subscription process failed for any other reason.
    """
    if settings.OPENAI_TRANSCRIPTION_KEY is None:
        logger.error(
            "OPENAI_TRANSCRIPTION_KEY environment variable is not set."
        )
        raise ScrapeFailed(
            "OPENAI_TRANSCRIPTION_KEY environment variable is not set."
        )

    docket = Docket.objects.get(pk=pk)
    docket_number = docket.docket_number

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Free Law Project",
        }
    )

    base_url = "https://file.supremecourt.gov"
    form_url = f"{base_url}/CaseNotification?caseNumber={docket_number}"
    try:
        logger.info("Fetching subscription page for case %s", docket_number)
        response = session.get(form_url, timeout=10)
        response.raise_for_status()
        scotus_html = BeautifulSoup(response.content, "html.parser")
        form = scotus_html.find("form", id="CaseNotificationForm")
        if not form:
            raise ScrapeFailed("Could not find the main subscription form.")

        # Collect all form inputs and include the anti-forgery token and CaseNumber
        payload = {}
        for input_tag in form.find_all("input"):
            name = input_tag.get("name")
            value = input_tag.get("value", "")
            if name:
                payload[name] = value

        anti_forgery_token = payload.get("__RequestVerificationToken")
        if not anti_forgery_token:
            raise ScrapeFailed("Could not find __RequestVerificationToken.")

        captcha_reset_url = f"{base_url}/Captcha/Reset"
        captcha_payload = {"__RequestVerificationToken": anti_forgery_token}
        reset_response = session.post(
            captcha_reset_url,
            data=captcha_payload,
            headers={
                "Referer": form_url,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=10,
        )
        reset_response.raise_for_status()
        reset_data = reset_response.json()
        captcha_id = reset_data.get("captchaId")
        if not captcha_id:
            raise ScrapeFailed(
                f"Failed to get captchaId from /Captcha/Reset. Response: {reset_response.text}"
            )

        # Fetch the Audio
        audio_url = f"{base_url}/Captcha/audio?captchaId={captcha_id}"
        audio_response = session.get(
            audio_url, headers={"Referer": form_url}, timeout=10
        )
        audio_response.raise_for_status()

        # Solve the captcha
        audio_file = BytesIO(audio_response.content)
        transcription = call_llm_transcription(
            ("captcha.wav", audio_file),
            api_key=settings.OPENAI_TRANSCRIPTION_KEY,
        )
        solution = process_scotus_captcha_transcription(transcription)

        # Validate Kendo captcha.
        captcha_validate_url = f"{base_url}/Captcha/validate"
        validate_payload = {
            "captchaId": captcha_id,
            "captcha": solution,
            "__RequestVerificationToken": anti_forgery_token,
        }
        validate_response = session.post(
            captcha_validate_url,
            data=validate_payload,
            headers={
                "Referer": form_url,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=10,
        )
        validate_response.raise_for_status()

        # Kendo validation returns JSON: true or false
        if validate_response.json() is not True:
            raise ScrapeFailed(
                f"CAPTCHA validation failed via AJAX. Response: {validate_response.text}"
            )

        # Main Form Submission
        final_submit_url = f"{base_url}{form.get('action')}"

        # Final Payload Update
        payload.update(
            {
                "Email": "scotus@recap.email",
                "captcha": solution,
                "SubscribeButton": "Subscribe",
            }
        )
        # Send the final request
        post_response = session.post(
            final_submit_url, data=payload, timeout=10
        )
        post_response.raise_for_status()

        if (
            "Docket Case Notification" in post_response.text
            and "verification link will be sent" in post_response.text
        ):
            logger.info(
                "Successfully submitted subscription for case %s. Verification email pending.",
                docket_number,
            )
        else:
            # Try to check other errors from the HTML response and log them...
            raise ScrapeFailed(
                f"Main form submission failed for case {docket_number}."
            )
    except requests.JSONDecodeError as e:
        logger.error(
            "Failed to decode JSON response during SCOTUS subscription: %s", e
        )
        raise ScrapeFailed(f"Failed to decode JSON response: {e}")
    except openai.APIError as e:
        logger.error("OpenAI API error during SCOTUS subscription: %s", e)
        raise ScrapeFailed(f"OpenAI API error: {e}")
    except requests.RequestException as e:
        logger.error("Network error during SCOTUS subscription: %s", e)
        raise ScrapeFailed(f"Network error: {e}")
    except Exception as e:
        logger.exception("Unexpected error during SCOTUS subscription")
        raise ScrapeFailed(str(e))
