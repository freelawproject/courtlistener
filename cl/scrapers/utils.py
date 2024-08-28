import os
import sys
from datetime import date
from typing import Optional, Tuple
from urllib.parse import urljoin

import httpx
import requests
from asgiref.sync import async_to_sync
from courts_db import find_court_by_id, find_court_ids_by_name
from django.conf import settings
from django.db.models import QuerySet
from juriscraper import AbstractSite
from juriscraper.AbstractSite import logger
from juriscraper.lib.test_utils import MockRequest
from lxml import html
from requests import Response, Session

from cl.corpus_importer.utils import winnow_case_name
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.decorators import retry
from cl.lib.microservice_utils import microservice
from cl.recap.mergers import find_docket_object, make_docket_number_core
from cl.scrapers.exceptions import (
    EmptyFileError,
    NoDownloadUrlError,
    UnexpectedContentTypeError,
)
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import Court, Docket, RECAPDocument


def get_child_court(child_court_name: str, court_id: str) -> Optional[Court]:
    """Get Court object from "child_courts" scraped string

    Ensure that the Court object found has the same parent court id has the
    Court object got from the scraper

    :param item: scraped court's name
    :param court_id: court id got from the Site scraper object

    :return: Court object for the child_court string if it exists and is valid
    """
    if not child_court_name:
        return None

    parent_court = find_court_by_id(court_id)[0]

    child_court_ids = find_court_ids_by_name(
        child_court_name,
        bankruptcy=parent_court["type"] == "bankruptcy",
        location=parent_court["location"],
        allow_partial_matches=False,
    )

    if not child_court_ids:
        logger.error(
            "Could not get child court id from name '%s'",
            child_court_name,
            extra={"fingerprint": [f"{court_id}-no-child-in-reportersdb"]},
        )
        return None

    if not (child_courts := Court.objects.filter(pk=child_court_ids[0])):
        logger.error(
            "Court object does not exist for '%s'",
            child_court_ids[0],
            extra={"fingerprint": [f"{court_id}-no-child-in-db"]},
        )
        return None

    child_court = child_courts[0]
    parent_id = child_court.parent_court.id if child_court.parent_court else ""
    if parent_id != court_id:
        logger.error(
            "Child court found from name '%s' with id '%s' has parent court id different from expected. Expected: '%s' Found: '%s'",
            child_court_name,
            child_court_ids[0],
            court_id,
            parent_id,
            extra={"fingerprint": [f"{court_id}-child-found-no-parent-match"]},
        )
        return None

    return child_court


@retry(
    (
        httpx.NetworkError,
        httpx.TimeoutException,
    ),
    tries=3,
    delay=5,
    backoff=2,
    logger=logger,
)
def test_for_meta_redirections(r: Response) -> Tuple[bool, Optional[str]]:
    """Test for meta data redirections

    :param r: A response object
    :return:  A boolean and value
    """
    extension = async_to_sync(microservice)(
        service="buffer-extension",
        file=r.content,
        params={"mime": True},
    ).text

    if extension == ".html":
        html_tree = html.fromstring(r.text)
        try:
            path = (
                "//meta[translate(@http-equiv, 'REFSH', 'refsh') = "
                "'refresh']/@content"
            )
            attr = html_tree.xpath(path)[0]
            wait, text = attr.split(";")
            if text.lower().startswith("url="):
                url = text[4:]
                if not url.startswith("http"):
                    # Relative URL, adapt
                    url = urljoin(r.url, url)
                return True, url
        except IndexError:
            return False, None
    return False, None


def follow_redirections(r: Response, s: Session) -> Response:
    """
    Parse and recursively follow meta refresh redirections if they exist until
    there are no more.
    """
    redirected, url = test_for_meta_redirections(r)
    if redirected:
        logger.info(f"Following a meta redirection to: {url.encode()}")
        r = follow_redirections(s.get(url), s)
    return r


@retry(
    (
        httpx.NetworkError,
        httpx.TimeoutException,
    ),
    tries=3,
    delay=5,
    backoff=2,
    logger=logger,
)
def get_extension(content: bytes) -> str:
    """A handful of workarounds for getting extensions we can trust."""
    return async_to_sync(microservice)(
        service="buffer-extension",
        file=content,
    ).text


def get_binary_content(
    download_url: str,
    site: AbstractSite,
) -> bytes | str:
    """Downloads the file, covering a few special cases such as invalid SSL
    certificates and empty file errors.

    :param download_url: The URL for the item you wish to download.
    :param site: Site object used to download data

    :return: The downloaded and cleaned content
    :raises: NoDownloadUrlError, UnexpectedContentTypeError, EmptyFileError
    """
    if not download_url:
        raise NoDownloadUrlError(download_url)

    # noinspection PyBroadException
    if site.method == "LOCAL":
        # "LOCAL" is the method when testing
        url = os.path.join(settings.MEDIA_ROOT, download_url)
        mr = MockRequest(url=url)
        r = mr.get()
        s = requests.Session()
    else:
        # some sites require a custom ssl_context, contained in the Site's
        # session. However, we can't send a request with both a
        # custom ssl_context and `verify = False`
        has_cipher = hasattr(site, "cipher")
        s = site.request["session"] if has_cipher else requests.session()

        if site.needs_special_headers:
            headers = site.request["headers"]
        else:
            headers = {"User-Agent": "CourtListener"}

        # Note that we do a GET even if site.method is POST. This is
        # deliberate.
        r = s.get(
            download_url,
            verify=has_cipher,  # WA has a certificate we don't understand
            headers=headers,
            cookies=site.cookies,
            timeout=300,
        )

        # test for empty files (thank you CA1)
        if len(r.content) == 0:
            raise EmptyFileError(f"EmptyFileError: '{download_url}'")

        # test for expected content type (thanks mont for nil)
        if site.expected_content_types:
            # Clean up content types like "application/pdf;charset=utf-8"
            # and 'application/octet-stream; charset=UTF-8'
            content_type = (
                r.headers.get("Content-Type").lower().split(";")[0].strip()
            )
            m = any(
                content_type in mime.lower()
                for mime in site.expected_content_types
            )

            if not m:
                court_str = site.court_id.split(".")[-1].split("_")[0]
                fingerprint = [f"{court_str}-unexpected-content-type"]
                msg = f"'{download_url}' '{content_type}' not in {site.expected_content_types}"
                raise UnexpectedContentTypeError(msg, fingerprint=fingerprint)

        # test for and follow meta redirects
        r = follow_redirections(r, s)
        r.raise_for_status()

    content = site.cleanup_content(r.content)

    return content


def signal_handler(signal, frame):
    # Trigger this with CTRL+4
    logger.info("**************")
    logger.info("Signal caught. Finishing the current court, then exiting...")
    logger.info("**************")
    global die_now
    die_now = True


def extract_recap_documents(
    docs: QuerySet,
    ocr_available: bool = True,
    order_by: Optional[str] = None,
    queue: Optional[str] = None,
) -> None:
    """Loop over RECAPDocuments and extract their contents. Use OCR if requested.

    :param docs: A queryset containing the RECAPDocuments to be processed.
    :type docs: Django Queryset
    :param ocr_available: Whether OCR should be completed (True) or whether items
    should simply be updated to have status OCR_NEEDED.
    :type ocr_available: Bool
    :param order_by: An optimization parameter. You may opt to order the
    processing by 'small-first' or 'big-first'.
    :type order_by: str
    :param queue: The celery queue to send the content to.
    :type queue: str
    """
    docs = docs.exclude(filepath_local="")
    if ocr_available:
        # We're doing OCR. Only work with those items that require it.
        docs = docs.filter(ocr_status=RECAPDocument.OCR_NEEDED)
    else:
        # Focus on the items that we don't know if they need OCR.
        docs = docs.filter(ocr_status=None)

    if order_by is not None:
        if order_by == "small-first":
            docs = docs.order_by("page_count")
        elif order_by == "big-first":
            docs = docs.order_by("-page_count")

    count = docs.count()
    throttle = CeleryThrottle(queue_name=queue)
    for i, pk in enumerate(docs.values_list("pk", flat=True)):
        throttle.maybe_wait()
        extract_recap_pdf.apply_async(
            (pk, ocr_available), priority=5, queue=queue
        )
        if i % 1000 == 0:
            msg = f"Sent {i + 1}/{count} tasks to celery so far."
            logger.info(msg)
            sys.stdout.write(f"\r{msg}")
            sys.stdout.flush()


def get_existing_docket(court_id: str, docket_number: str) -> Docket | None:
    """Look for an existing docket for a given court_id and docket number

    recap.mergers.find_docket_object prioritizes lookups by docket_number_core
    which is designed for federal / PACER sources. This function is rough
    equivalent with lookup priorities inverted, intended to be used with
    scraped sources

    Even when make_docket_number_core returns an empty string for most state
    courts that we scrape, it causes mismatches in courts like `az`, where
    2 different dockets like '1 CA-CR 23-0297' and '1 CA-CV 23-0297-FC'
    have the same core number

    Examples of  docket numbers do not map to a docket_number_core
    (fldistctapp '5D2023-0888'), (ohioctapp, '22CA15')

    :param court_id: the court id
    :param docket_number: the docket number

    :return: Docket if find a match, None if we don't
    """
    lookups = [
        {"court_id": court_id, "docket_number": docket_number},
    ]

    docket_number_core = make_docket_number_core(docket_number)
    if docket_number_core:
        lookups.append(
            {
                "court_id": court_id,
                "pacer_case_id": None,
                "docket_number_core": docket_number_core,
            }
        )

    for lookup in lookups:
        queryset = Docket.objects.filter(**lookup)
        count = queryset.count()
        if count == 1:
            return queryset[0]
        if count > 1:
            logger.error(
                "%s: more than 1 docket match for docket number '%s'",
                court_id,
                docket_number,
            )


def update_or_create_docket(
    case_name: str,
    case_name_short: str,
    court_id: str,
    docket_number: str,
    source: int,
    from_harvard: bool,
    blocked: bool = False,
    case_name_full: str = "",
    date_blocked: date | None = None,
    date_argued: date | None = None,
    ia_needs_upload: bool | None = None,
    appeal_from_str: str = "",
) -> Docket:
    """Look for an existing Docket and update it or create a new one if it's
    not found.

    :param case_name: The docket case_name.
    :param case_name_short: The docket case_name_short
    :param court_id: The court id the docket belongs to.
    :param docket_number: The docket number.
    :param source: The docket source.
    :param from_harvard: True when this function is called from the
        Harvard importer; the Harvard data is considered
        more trustable  and should overwrite an existing docket's data
        Should be False when called from scrapers.
    :param blocked: If the docket should be blocked, default False.
    :param case_name_full: The docket case_name_full.
    :param date_blocked: The docket date_blocked if it's blocked.
    :param date_argued: The docket date_argued if it's an oral argument.
    :param ia_needs_upload: If the docket needs upload to IA, default None.
    :param appeal_from_str: Name (not standardized id) of the lower level court.
    :return: The docket.
    """

    docket_fields = {
        "case_name": case_name,
        "case_name_short": case_name_short,
        "case_name_full": case_name_full,
        "blocked": blocked,
        "ia_needs_upload": ia_needs_upload,
        "appeal_from_str": appeal_from_str,
        "date_blocked": date_blocked,
        "date_argued": date_argued,
    }
    if from_harvard:
        docket = async_to_sync(find_docket_object)(
            court_id, None, docket_number, None, None, None
        )
    else:
        docket = get_existing_docket(court_id, docket_number)

    if not docket or not docket.pk:
        return Docket(
            **docket_fields,
            source=source,
            docket_number=docket_number,
            court_id=court_id,
        )

    # Update the existing docket with the new values
    docket.add_opinions_source(source)

    for field, value in docket_fields.items():
        # do not use blanket `if not value:`, since
        # blocked and ia_needs_upload are booleans and would be skipped
        if value is None or value == "":
            continue

        if (
            not from_harvard
            and field == "case_name"
            and getattr(docket, field)
            and getattr(docket, field) != value
        ):
            # Safeguard to catch possible docket mismatches, check that they
            # have at least 50% of words in common
            new_parts = winnow_case_name(value)
            old_parts = winnow_case_name(docket.case_name)
            denominator = min(len(old_parts), len(new_parts)) + 1
            if len(new_parts.intersection(old_parts)) / denominator < 0.5:
                logger.error(
                    "New case_name '%s' looks too different from old '%s'. Court %s. Docket %s",
                    value,
                    docket.case_name,
                    court_id,
                    docket.pk,
                )
                continue

            # Most times, we find updated values for case_name that may
            # be a longer form than what we currently have, which we can
            # take advantage of to populate case_name_full
            if not getattr(docket, "case_name_full") and len(value) > len(
                getattr(docket, field)
            ):
                setattr(docket, "case_name_full", value)
        else:
            setattr(docket, field, value)

    return docket
