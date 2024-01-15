import os
import sys
import traceback
from datetime import date
from typing import Optional, Tuple
from urllib.parse import urljoin

import requests
from asgiref.sync import async_to_sync
from courts_db import find_court_by_id, find_court_ids_by_name
from django.conf import settings
from django.db.models import QuerySet
from juriscraper.AbstractSite import logger
from juriscraper.lib.test_utils import MockRequest
from lxml import html
from requests import Response, Session
from requests.cookies import RequestsCookieJar

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.decorators import retry
from cl.lib.microservice_utils import microservice
from cl.recap.mergers import find_docket_object
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
        requests.ConnectionError,
        requests.ReadTimeout,
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
        requests.ConnectionError,
        requests.ReadTimeout,
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
    cookies: RequestsCookieJar,
    headers: dict,
    method: str = "GET",
) -> Tuple[str, Optional[Response]]:
    """Downloads the file, covering a few special cases such as invalid SSL
    certificates and empty file errors.

    :param download_url: The URL for the item you wish to download.
    :param cookies: Cookies that might be necessary to download the item.
    :param headers: Headers that might be necessary to download the item.
    :param method: The HTTP method used to get the item, or "LOCAL" to get an
    item during testing
    :return: Two values. The first is a msg indicating any errors encountered.
    If blank, that indicates success. The second value is the response object
    containing the downloaded file.
    """
    if not download_url:
        # Occurs when a DeferredList fetcher fails.
        msg = f"NoDownloadUrlError: {download_url}\n{traceback.format_exc()}"
        return msg, None
    # noinspection PyBroadException
    if method == "LOCAL":
        url = os.path.join(settings.MEDIA_ROOT, download_url)
        mr = MockRequest(url=url)
        r = mr.get()
        r = follow_redirections(r, requests.Session())
        r.raise_for_status()
    else:
        # Note that we do a GET even if site.method is POST. This is
        # deliberate.
        s = requests.session()

        r = s.get(
            download_url,
            verify=False,  # WA has a certificate we don't understand
            headers=headers,
            cookies=cookies,
            timeout=300,
        )

        # test for empty files (thank you CA1)
        if len(r.content) == 0:
            msg = f"EmptyFileError: {download_url}\n{traceback.format_exc()}"
            return msg, None

        # test for and follow meta redirects
        r = follow_redirections(r, s)
        r.raise_for_status()

    # Success!
    return "", r


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


def update_or_create_docket(
    case_name: str,
    case_name_short: str,
    court_id: str,
    docket_number: str,
    source: int,
    blocked: bool = False,
    case_name_full: str = "",
    date_blocked: date | None = None,
    date_argued: date | None = None,
    ia_needs_upload: bool | None = None,
) -> Docket:
    """Look for an existing Docket and update it or create a new one if it's
    not found.

    :param case_name: The docket case_name.
    :param case_name_short: The docket case_name_short
    :param court_id: The court id the docket belongs to.
    :param docket_number: The docket number.
    :param source: The docket source.
    :param blocked: If the docket should be blocked, default False.
    :param case_name_full: The docket case_name_full.
    :param date_blocked: The docket date_blocked if it's blocked.
    :param date_argued: The docket date_argued if it's an oral argument.
    :param ia_needs_upload: If the docket needs upload to IA, default None.
    :return: The docket docket.
    """
    docket = async_to_sync(find_docket_object)(court_id, None, docket_number)
    if docket.pk:
        docket.case_name = case_name
        docket.case_name_short = case_name_short
        docket.case_name_full = case_name_full
        docket.source = source
        docket.blocked = blocked
        docket.date_blocked = date_blocked
        docket.date_argued = date_argued
        docket.ia_needs_upload = ia_needs_upload
    else:
        docket = Docket(
            case_name=case_name,
            case_name_short=case_name_short,
            case_name_full=case_name_full,
            docket_number=docket_number,
            court_id=court_id,
            source=source,
            blocked=blocked,
            date_blocked=date_blocked,
            date_argued=date_argued,
            ia_needs_upload=ia_needs_upload,
        )
    return docket
