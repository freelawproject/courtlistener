import json
import re
from datetime import date, datetime
from urllib.parse import urljoin

import httpx
from asgiref.sync import async_to_sync
from courts_db import find_court_by_id, find_court_ids_by_name
from django.core.files.base import ContentFile
from django.db.models import Q
from eyecite.find import get_citations
from eyecite.tokenizers import HyperscanTokenizer
from juriscraper import AbstractSite
from juriscraper.AbstractSite import logger
from lxml import html
from reporters_db import REPORTERS
from requests import Response, Session

from cl.citations.utils import map_reporter_db_cite_type
from cl.corpus_importer.utils import winnow_case_name
from cl.lib.decorators import retry
from cl.lib.microservice_utils import microservice
from cl.lib.storage import S3GlacierInstantRetrievalStorage
from cl.recap.mergers import find_docket_object
from cl.search.models import (
    Citation,
    Court,
    Docket,
    OpinionCluster,
    OriginatingCourtInformation,
)

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


def make_citation(
    cite_str: str, cluster: OpinionCluster, court_id: str
) -> Citation | None:
    """Create and return a citation object for the input values."""
    citation_objs = get_citations(cite_str, tokenizer=HYPERSCAN_TOKENIZER)
    if not citation_objs:
        logger.error(
            "Could not parse citation from court '%s'",
            court_id,
            extra=dict(
                cite=cite_str,
                cluster=cluster,
                fingerprint=[f"{court_id}-no-citation-found"],
            ),
        )
        return None
    # Convert the found cite type to a valid cite type for our DB.
    cite_type_str = citation_objs[0].all_editions[0].reporter.cite_type
    return Citation(
        cluster=cluster,
        volume=citation_objs[0].groups["volume"],
        reporter=citation_objs[0].corrected_reporter(),
        page=citation_objs[0].corrected_page(),
        type=map_reporter_db_cite_type(cite_type_str),
    )


def citation_is_duplicated(citation_candidate: Citation, cite: str) -> bool:
    """Checks if the citation is duplicated for the cluster

    Following corpus_importer.utils.add_citations_to_cluster we
    identify 2 types of duplication:
    - exact: a citation with the same fields already exists for the cluster
    - duplication in the same reporter: the cluster already has a citation
        in that reporter

    :param citation_candidate: the citation object
    :param cite: citation string

    :return: True if citation is duplicated, False if not
    """
    citation_params = {**citation_candidate.__dict__}
    citation_params.pop("_state", "")
    citation_params.pop("id", "")
    cluster_id = citation_candidate.cluster.id

    # Exact duplication
    if Citation.objects.filter(**citation_params).exists():
        logger.info(
            "Citation '%s' already exists for cluster %s",
            cite,
            cluster_id,
        )
        return True

    # Duplication in the same reporter
    if Citation.objects.filter(
        cluster_id=cluster_id, reporter=citation_candidate.reporter
    ).exists():
        logger.info(
            "Another citation in the same reporter '%s' exists for cluster %s",
            citation_candidate.reporter,
            cluster_id,
        )
        return True

    return False


def get_child_court(child_court_name: str, court_id: str) -> Court | None:
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
def test_for_meta_redirections(r: Response) -> tuple[bool, str | None]:
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


def signal_handler(signal, frame):
    # Trigger this with CTRL+4
    logger.info("**************")
    logger.info("Signal caught. Finishing the current court, then exiting...")
    logger.info("**************")
    global die_now
    die_now = True


def get_existing_docket(
    court_id: str, docket_number: str, appeal_from_str: str = ""
) -> Docket | None:
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
    :param appeal_from_str: useful for disambiguating `ohioctapp` dockets,
        this is the "lower_courts" returned juriscraper field

    :return: Docket if find a match, None if we don't
    """
    # Avoid lookups by blank docket number
    if not docket_number.strip():
        return

    # delete semicolons only for the lookup, for back compatibility
    # with juriscraper string formatting
    # https://github.com/freelawproject/juriscraper/pull/1166
    lookup = Q(court_id=court_id) & (
        Q(docket_number=docket_number.replace(";", ""))
        | Q(docket_number=docket_number)
    )

    # Special case where docket numbers are the same and repeated
    # across districts, but can be disambiguated using the lower court
    if court_id == "ohioctapp" and appeal_from_str:
        lookup = lookup & Q(appeal_from_str=appeal_from_str)

    queryset = Docket.objects.filter(lookup)
    count = queryset.count()
    if count == 1:
        return queryset[0]
    if count > 1:
        logger.error(
            "%s: more than 1 docket match for docket number '%s'",
            court_id,
            docket_number,
        )
        return queryset[0]


def case_names_are_too_different(
    first: str, second: str, threshold: float = 0.5
) -> bool:
    """Compares 2 case names' words as a similitude measure
    Useful to raise a warning when updating a docket and names are found
    to be too different

    :param first: first case name
    :param second: second case name
    :param threshold: minimum percentage of words in common

    :return: True if case names are too different according to the threshold;
        False if names are similar
    """
    new_parts = winnow_case_name(first.lower())
    old_parts = winnow_case_name(second.lower())
    # or 1 to prevent 0 lenght minimum
    denominator = min(len(old_parts), len(new_parts)) or 1
    return len(new_parts.intersection(old_parts)) / denominator < threshold


def update_or_create_docket(
    case_name: str,
    case_name_short: str,
    court: Court,
    docket_number: str,
    source: int,
    from_harvard: bool,
    blocked: bool = False,
    case_name_full: str = "",
    date_blocked: date | None = None,
    date_argued: date | None = None,
    ia_needs_upload: bool | None = None,
    appeal_from_str: str = "",
    appeal_from_id: str = "",
) -> Docket:
    """Look for an existing Docket and update it or create a new one if it's
    not found.

    :param case_name: The docket case_name.
    :param case_name_short: The docket case_name_short
    :param court: The court objects the docket belongs to
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
    :param appeal_from_id: Lower court id.
    :return: The docket.
    """
    docket_fields = {
        "case_name": case_name,
        "case_name_short": case_name_short,
        "case_name_full": case_name_full,
        "blocked": blocked,
        "ia_needs_upload": ia_needs_upload,
        "appeal_from_str": appeal_from_str,
        "appeal_from_id": appeal_from_id,
        "date_blocked": date_blocked,
        "date_argued": date_argued,
    }
    if not appeal_from_id:
        docket_fields.pop("appeal_from_id", "")
    elif not Court.objects.filter(id=appeal_from_id).exists():
        docket_fields.pop("appeal_from_id", "")
        logger.error(
            "Docket.appeal_from_id has non existing Court.id '%s' as value",
            appeal_from_id,
        )

    court_id = court.pk
    uses_docket_number_core = court.jurisdiction in Court.FEDERAL_JURISDICTIONS

    if from_harvard or uses_docket_number_core:
        docket = async_to_sync(find_docket_object)(
            court_id, None, docket_number, None, None, None
        )
    else:
        docket = get_existing_docket(court_id, docket_number, appeal_from_str)

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
            if case_names_are_too_different(value, docket.case_name, 0.5):
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


def scraped_citation_object_is_valid(citation_object: dict) -> bool:
    """Validate Citation objects from `Site.extract_from_text`

    Check that the parsed `Citation.reporter` exists in reporters-db
    and that the `Citation.type` matches the reporters-db type

    :param citation_object: dict got from `Site.extract_from_text`
    :return: True if the parsed reporter and type match with reporters-db
        False otherwise
    """
    parsed_reporter = citation_object["reporter"]
    try:
        reporter = REPORTERS[parsed_reporter]
        mapped_type = map_reporter_db_cite_type(reporter[0].get("cite_type"))
        if mapped_type == citation_object["type"]:
            return True
        logger.error(
            "Citation.type '%s' from `extract_from_text` does not match reporters-db type '%s' for reporter '%s'",
            citation_object["type"],
            mapped_type,
            parsed_reporter,
        )
    except KeyError:
        logger.error("Parsed reporter '%s' does not exist", parsed_reporter)

    return False


def save_response(site: AbstractSite) -> None:
    """Stores scrapers responses content and headers in a S3 bucket

    This is passed to juriscraper's Site objects as the
    `save_response_fn` argument, which will make Juriscraper
    save every response

    :param site: the Site object, used to access the saved response
    :return None
    """

    storage = S3GlacierInstantRetrievalStorage()
    response = site.request["response"]

    scraper_id = site.court_id.split(".")[-1]
    scrape_type = site.court_id.split(".")[1]  # opinions or oral args
    now_str = datetime.now().strftime("%Y/%m/%d/%H_%M_%S")
    base_name = f"responses/{scrape_type}/{scraper_id}/{now_str}"

    headers_json = json.dumps(dict(response.headers), indent=4)
    storage.save(f"{base_name}_headers.json", ContentFile(headers_json))

    try:
        # both tests for and parses JSON content
        content = json.dumps(json.loads(response.content), indent=4)
        extension = "json"
    except (UnicodeDecodeError, json.decoder.JSONDecodeError):
        content = response.content
        extension = "html"

    content_name = f"{base_name}.{extension}"
    storage.save(content_name, ContentFile(content))


def check_duplicate_ingestion(local_path_name: str) -> None:
    """
    Send an error log to Sentry if a filename has a high repetition count

    S3 filenames / filepaths for opinions and oral arguments are created using
    created via `cl.lib.storage.get_name_by_incrementing`. The name is composed
    of the document's filed date or argued date, the case name and the file
    extension. `get_name_by_incrementing` adds a counter if the name already
    existed

    For example, this file name means there are 2 documents for that case name,
    date and extension combination
    'pdf/2025/06/05/state_v._walsh_1.pdf'

    Need to consider an acceptable repetition threshold, since we may get the
    same file path for:
    - a cluster of opinions, which are actually different documents for the
        same date and case
    - a common case name in the same date, for example, "State v. Doe"
    - opinion versions

    :param local_path_name: filepath of the file in S3
    :return None
    """
    # Trigger error log for repetitions beyond this count
    SUSPECT_DUPLICATES_THRESHOLD = 4

    match = re.search(r"_(?P<repeated_count>\d+)\.\w+$", local_path_name or "")
    if not match:
        return

    repeated_count = int(match.group("repeated_count"))
    if repeated_count > SUSPECT_DUPLICATES_THRESHOLD:
        base_file_name = f"{local_path_name[: match.start()]}.{local_path_name.split('.')[-1]}"
        logger.error(
            "Probable ongoing duplicate ingestion: %s files with name '%s'",
            repeated_count,
            base_file_name,
        )


def update_or_create_originating_court_information(
    docket: Docket, lower_court_number: str, lower_court_judge: str
) -> OriginatingCourtInformation | None:
    """Update or create an OriginatingCourtInformation given the scraped values

    :param docket: the docket to which the OCI will be linked
    :param lower_court_number: will go into OCI.docket_number
    :param lower_court_judge: will go into OCI.assigned_to_str
    """
    if not (lower_court_judge or lower_court_number):
        return

    if existing_oci := docket.originating_court_information:
        update = False
        if not existing_oci.docket_number and lower_court_number:
            existing_oci.docket_number = lower_court_number
            update = True
        if not existing_oci.assigned_to_str and lower_court_judge:
            existing_oci.assigned_to_str = lower_court_judge
            update = True

        if update:
            existing_oci.save()

        # If the docket already had a OriginatingCourtInformation, just return
        return

    return OriginatingCourtInformation(
        docket_number=lower_court_number or "",
        assigned_to_str=lower_court_judge or "",
    )
