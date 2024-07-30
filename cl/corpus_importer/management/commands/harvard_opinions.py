import difflib
import itertools
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from glob import glob
from typing import Any, Optional, TypedDict

import requests
from bs4 import BeautifulSoup
from courts_db import find_court
from django.conf import settings
from django.db import transaction
from django.db.utils import OperationalError
from eyecite.find import get_citations
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer
from juriscraper.lib.diff_tools import normalize_phrase
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize, titlecase

from cl.corpus_importer.utils import (
    add_citations_to_cluster,
    clean_body_content,
    match_based_text,
)
from cl.lib.argparse_types import _argparse_volumes
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_utils import trunc
from cl.lib.utils import human_sort
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.scrapers.utils import update_or_create_docket
from cl.search.models import SOURCES, Court, Docket, Opinion, OpinionCluster
from cl.search.tasks import add_items_to_solr

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")

cnt = CaseNameTweaker()


def validate_dt(date_str: str) -> tuple[Optional[date], bool]:
    """
    Check if the date string is only year-month or year.
    If partial date string, make date string the first of the month
    and mark the date as an estimate.

    If unable to validate date return an empty string, True tuple.

    :param date_str: a date string we receive from the harvard corpus
    :returns: Tuple of date obj or date obj estimate
    and boolean indicating estimated date or actual date.
    """
    date_obj, date_approx = None, False
    add_ons = ["", "-15", "-07-01"]
    for add_on in add_ons:
        try:
            date_obj = datetime.strptime(date_str + add_on, "%Y-%m-%d").date()
            break
        except ValueError as msg:
            date_approx = True
            # We discovered that dates like 1913-02-29 killed this method.
            # In this instance, revert back one day and continue
            if (
                str(msg) == "day is out of range for month"
                and "02-29" in date_str
            ):
                date_str = date_str.replace("29", "28")
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                break
    return date_obj, date_approx


def _make_glob_from_args(
    reporter: Optional[str],
    volumes: Optional[range],
    page: Optional[str],
) -> list[str]:
    """Make list of glob paths

    :param reporter: The reporter to filter if any
    :param volumes: The volumes of the reporter to filter to, if any
    :return: A list of glob paths
    """

    if reporter and volumes and page:
        glob_path = os.path.join(
            settings.MEDIA_ROOT,
            "harvard_corpus",
            f"law.free.cap.{reporter}.{volumes[0]}",
            f"{page}.*.json",
        )
        return [glob_path]
    elif reporter and volumes:
        glob_paths = []
        for volume in volumes:
            glob_path = os.path.join(
                settings.MEDIA_ROOT,
                "harvard_corpus",
                f"law.free.cap.{reporter}.{volume}",
                "*.json",
            )
            glob_paths.append(glob_path)
        return glob_paths
    elif reporter:
        reporter_key = ".".join(["law.free.cap", reporter])
        glob_path = os.path.join(
            settings.MEDIA_ROOT,
            "harvard_corpus",
            f"{reporter_key}.*/*.json",
        )
    else:
        glob_path = os.path.join(
            settings.MEDIA_ROOT, "harvard_corpus", "law.free.cap.*/*.json"
        )
    return [glob_path]


def filepath_list(
    reporter: str,
    volumes: Optional[range],
    page: Optional[str],
) -> list[str]:
    """Given a reporter and volume, return a sorted list of files to process

    Make a list of file paths accordingly:
     - If neither a reporter nor a volume are given, do all cases from all
       volumes of all reporters.
     - If a only reporter is given, do all cases in all volumes for that
       reporter.
     - If a reporter and volume are both given, only do cases from that volume
       of that reporter.

    :param reporter: The reporter to filter to (optional)
    :param volumes: The volumes of the reporter to filter to (optional)
    :param page: The page of the reporter's volume to filter to (optional)
    :return: A sorted list of file paths
    """

    files = []
    glob_paths = _make_glob_from_args(reporter, volumes, page)
    for glob_path in glob_paths:
        files.extend(glob(glob_path))
    files = human_sort(files, key=None)  # type: ignore
    return files  # type: ignore


def check_for_match(new_case: str, possibilities: list[str]) -> bool:
    """Check for matches based on case names

    This code is a variation of get_closest_match_index used in juriscraper.
    It checks if the case name we are trying to add matches any duplicate
    citation cases already in the system.

    :param new_case: The importing case name
    :param possibilities: The array of cases already in the
    system with the same citation
    :return: Returns the match if any, otherwise returns None.
    """
    new_case = normalize_phrase(new_case)
    possibilities = [normalize_phrase(x) for x in possibilities]
    try:
        match = difflib.get_close_matches(
            new_case, possibilities, n=1, cutoff=0.7
        )[0]
        return True if match else False
    except IndexError:
        # No good matches.
        return False


def map_opinion_type(harvard_opinion_type: str) -> str:
    """Map Harvard opinion types to CL ones

    :param harvard_opinion_type: The type field of the Harvard opinion
    :return: The type field from our schema
    """
    type_map = {
        "unanimous": Opinion.UNANIMOUS,
        "majority": Opinion.LEAD,
        "plurality": Opinion.PLURALITY,
        "concurrence": Opinion.CONCURRENCE,
        "concurring-in-part-and-dissenting-in-part": Opinion.CONCUR_IN_PART,
        "dissent": Opinion.DISSENT,
        "remittitur": Opinion.REMITTUR,
        "rehearing": Opinion.REHEARING,
        "on-the-merits": Opinion.ON_THE_MERITS,
        "on-motion-to-strike-cost-bill": Opinion.ON_MOTION_TO_STRIKE,
    }
    return type_map.get(harvard_opinion_type, Opinion.COMBINED)


def parse_extra_fields(soup, fields, long_field=False) -> dict:
    """Parse the remaining extra fields into long or short strings
    returned as dict

    :param soup: The bs4 representation of the case data xml
    :param fields: An array of strings names for fields to parse
    :param long_field: A boolean decides to parse the field into <p> or simple
    text.
    :return: Returns dictionary of string values to be stored in opinion
    """

    data_set = {}
    for field in fields:
        elements = []
        # We look for the matching tag name or matching data-type attribute
        for elem in soup.find_all(
            lambda tag: (tag.name == field and tag.get("data-type") is None)
            or tag.get("data-type") == field
        ):
            [x.extract() for x in elem.find_all("page-number")]
            if long_field:
                elements.append(f"<p>{elem.text}</p>")
            else:
                elements.append(elem.text)

        if long_field:
            data_set[field] = " ".join(elements)
        else:
            data_set[field] = ", ".join(elements)

    return data_set


class OptionsType(TypedDict):
    reporter: str
    volumes: Optional[range]
    page: str
    court_id: Optional[str]
    location: Optional[str]
    make_searchable: bool
    bankruptcy: bool


def get_fix_list() -> list[str]:
    """Download the fix list for harvard data.

    :return:List of files to fix
    """
    data = requests.get(
        "https://raw.githubusercontent.com/freelawproject/opinionated/main/data/harvard/missing-files.json",
        timeout=10,
    ).json()
    return data["files"]


def merge_fixes(data: dict[str, Any], identifier: str) -> dict[str, Any]:
    """Merge fixes into the data

    :param data: The Harvard data
    :param identifier: The filepath of the data to fix.
    :return: a dict with updated data
    """
    fix = requests.get(
        f"https://raw.githubusercontent.com/freelawproject/opinionated/main/data/harvard/{identifier}",
        timeout=10,
    ).json()
    data.update(fix)
    return data


def read_json(file_path: str, ia_download_url: str) -> Optional[Any]:
    """Read JSON file and throw a warning if exceptions occur

    :param file_path: Filepath to JSON
    :param ia_download_url: URL of file
    :return: JSON object if available
    """
    try:
        with open(file_path) as f:
            data = json.load(f)
    except ValueError:
        logger.warning(f"Empty json: missing case at: {ia_download_url}")
        return None
    except Exception as e:
        logger.warning(f"Unknown error {e} for: {ia_download_url}")
        return None
    return data


def parse_harvard_opinions(options: OptionsType) -> None:
    """Parse Harvard Opinions

    Parse downloaded CaseLaw Corpus from internet archive and add them to our
    database.

    Optionally uses a reporter abbreviation to identify cases to download as
    used by IA.  (Ex. T.C. => tc)

    Optionally uses a volumes integer.

    If neither is provided, code will cycle through all downloaded files.

    :param options: The command line options including (reporter,
    volume court_id and make_searchable)
    :return: None
    """

    reporter = options["reporter"]
    volumes = options["volumes"]
    page = options["page"]
    court_id = options["court_id"]
    make_searchable = options["make_searchable"]
    is_bankruptcy = options["bankruptcy"]

    if not reporter and volumes:
        logger.error("You provided volume(s) but no reporter. Exiting.")
        return

    filepaths = filepath_list(reporter, volumes, page)
    fix_list = get_fix_list()

    for file_path in filepaths:
        logger.info(f"Processing opinion at {file_path}")

        ia_download_url = "/".join(
            ["https://archive.org/download", file_path.split("/", 9)[-1]]
        )

        oc = OpinionCluster.objects.filter(filepath_json_harvard=file_path)
        if len(oc) > 0:
            logger.info(
                f"Skipping {oc[0].id} - already in system {ia_download_url}"
            )
            continue

        data = read_json(file_path, ia_download_url)
        if not data:
            continue

        identifier = "/".join(file_path.rsplit("/", 2)[1:])
        if identifier in fix_list:
            logger.info(f"Fetching fixes and merging data at {file_path}")
            data = merge_fixes(data, identifier)

        # Cleanup whitespace on citations
        clean_cite = re.sub(r"\s+", " ", data["citations"][0]["cite"])
        cites = get_citations(clean_cite, tokenizer=HYPERSCAN_TOKENIZER)
        cites = [cite for cite in cites if isinstance(cite, FullCaseCitation)]
        if not cites:
            logger.warning(f"No citation found for {clean_cite}")
            continue

        case_name = harmonize(data["name_abbreviation"])
        case_name_short = cnt.make_case_name_short(case_name)
        case_name_full = harmonize(data["name"])

        citation = cites[0]

        # TODO: Generalize this to handle all court types somehow.
        if not options["court_id"]:
            # Sometimes the court string doesn't match just one court
            # This is used to alleviate certain circumstances.
            found_court = find_court(
                data["court"]["name"],
                bankruptcy=is_bankruptcy,
                location=options["location"],
            )
            if len(found_court) != 1:
                logging.warning(
                    f"Court not found for {data['court']['name']} at {file_path}"
                )
                continue
            court_id = found_court[0]

        if not Court.objects.filter(id=court_id).exists():
            logger.warning(f"Court not found in Courtlistener: {court_id}")
            continue

        # Handle partial dates by adding -01 to YYYY-MM dates
        date_filed, is_approximate = validate_dt(data["decision_date"])
        if not date_filed:
            logger.warning(
                f"No date found for {data['decision_date']} at {file_path}"
            )
            continue
        case_body = data["casebody"]["data"]
        harvard_characters = clean_body_content(case_body, harvard_file=True)

        if not harvard_characters:
            # Unfortunately, some harvard cases have no opinions.
            # See: https://cite.case.law/pdf/1305086/Vinson%20v.%20Cox,%2099%20Fla.%201373%20(1930).pdf
            logger.warning(f"No opinion in Harvard XML at {file_path}")
            continue

        previously_imported_case = find_previously_imported_cases(
            data,
            court_id,
            date_filed,
            harvard_characters,
            case_name_full,
            citation,
        )
        if previously_imported_case:
            # Simply add citations to our matched case for now. Later, we'll
            # upgrade this to do a full merge.

            with transaction.atomic():
                add_citations_to_cluster(
                    [c.get("cite") for c in data.get("citations", [])],
                    cluster_id=previously_imported_case.id,
                )
                logger.info(
                    f"Adding citations for case at https://www.courtlistener.com/opinion/{previously_imported_case.id}/{previously_imported_case.slug}"
                )
                # Add the filepath to the harvard file for the associated opinion
                previously_imported_case.filepath_json_harvard = file_path
                previously_imported_case.save()
            continue

        logger.info(f"Adding case {case_name_full}")
        add_new_case(
            data,
            case_body,
            case_name,
            case_name_full,
            case_name_short,
            date_filed,
            is_approximate,
            citation,
            court_id,
            file_path,
            make_searchable,
        )


def add_new_case(
    data: dict[str, Any],
    case_body: str,
    case_name: str,
    case_name_full: str,
    case_name_short: str,
    date_filed: Optional[date],
    is_approximate: bool,
    citation: FullCaseCitation,
    court_id: Optional[str],
    file_path: str,
    make_searchable: bool,
) -> None:
    """Add new case to Courtlistener.com

    :param data: The Harvard data JSON object
    :param case_body: The Harvard Case body
    :param case_name: The case name
    :param case_name_full: The full case name
    :param case_name_short: The case name abbreviation
    :param date_filed: The date the case was filed
    :param is_approximate: Is the case date filed approximate
    :param citation: The citation we use in logging and first citation parsed
    :param court_id: The CL Court ID
    :param file_path: The path to the Harvard JSON
    :param make_searchable: Should we add this case to SOLR
    :return: None
    """
    soup = BeautifulSoup(case_body, "lxml")

    # Some documents contain images in the HTML
    # Flag them for a later crawl by using the placeholder '[[Image]]'
    judge_list = [
        extract_judge_last_name(x.text)
        for x in soup.find_all(
            lambda tag: (tag.name == "judges" and tag.get("data-type") is None)
            or tag.get("data-type") == "judges"
        )
    ]
    author_list = [
        extract_judge_last_name(x.text)
        for x in soup.find_all(
            lambda tag: (tag.name == "author" and tag.get("data-type") is None)
            or tag.get("data-type") == "author"
        )
    ]
    # Flatten and dedupe list of judges
    judges = ", ".join(
        sorted(set(itertools.chain.from_iterable(judge_list + author_list)))
    )
    judges = titlecase(judges)
    docket_string = data["docket_number"].strip()

    short_fields = ["attorneys", "disposition", "otherdate", "seealso"]

    long_fields = [
        "syllabus",
        "summary",
        "history",
        "headnotes",
        "correction",
    ]

    short_data = parse_extra_fields(soup, short_fields, False)
    long_data = parse_extra_fields(soup, long_fields, True)

    with transaction.atomic():
        logger.info(
            f"Adding docket for {case_name}: {citation.corrected_citation()}"
        )
        docket = update_or_create_docket(
            case_name,
            case_name_short,
            court_id,
            docket_string,
            Docket.HARVARD,
            overwrite_existing_data=True,
            case_name_full=case_name_full,
            ia_needs_upload=False,
        )
        try:
            with transaction.atomic():
                docket.save()
        except OperationalError as e:
            if "exceeds maximum" in str(e):
                docket.docket_number = (
                    "%s, See Corrections for full Docket Number"
                    % trunc(docket_string, length=5000, ellipsis="...")
                )
                docket.save()
                long_data["correction"] = (
                    f"{data['docket_number']} <br> {long_data['correction']}"
                )

        cluster = OpinionCluster(
            case_name=case_name,
            case_name_short=case_name_short,
            case_name_full=case_name_full,
            precedential_status="Published",
            docket_id=docket.id,
            source=SOURCES.HARVARD_CASELAW,
            date_filed=date_filed,
            date_filed_is_approximate=is_approximate,
            attorneys=short_data["attorneys"],
            disposition=short_data["disposition"],
            syllabus=long_data["syllabus"],
            summary=long_data["summary"],
            history=long_data["history"],
            other_dates=short_data["otherdate"],
            cross_reference=short_data["seealso"],
            headnotes=long_data["headnotes"],
            correction=long_data["correction"],
            judges=judges,
            filepath_json_harvard=file_path,
        )
        cluster.save(index=False)
        logger.info("Saving cluster for: %s", cluster.id)

        logger.info("Adding citation for: %s", citation.corrected_citation())
        add_citations_to_cluster(
            [c.get("cite") for c in data.get("citations", [])], cluster.id
        )
        new_op_pks = add_opinions(soup, cluster.id, citation)

    if make_searchable:
        add_items_to_solr.delay(new_op_pks, "search.Opinion")

    logger.info("Finished: %s", citation.corrected_citation())
    logger.info(
        f"Finished adding case at https://www.courtlistener.com/opinion/{cluster.id}/{cluster.slug}"
    )


def add_opinions(
    soup: BeautifulSoup, cluster_id: int, citation: FullCaseCitation
) -> list[int]:
    """Add opinions to Cluster

    :param soup: The bs4 representation of the case data xml
    :param cluster_id: The cluster ID
    :param citation: Citation object
    :return: Opinion IDs in a list
    """
    new_op_pks = []
    # We look for opinion tags without data-type or tags with data-type == "opinion"
    for op in soup.find_all(
        lambda tag: (tag.name == "opinion" and tag.get("data-type") is None)
        or tag.get("data-type") == "opinion"
    ):
        # This code cleans author tags for processing.
        # It is particularly useful for identifying Per curiam
        for elem in [op.find("author")]:
            if elem is not None:
                [x.extract() for x in elem.find_all("page-number")]

        auth = op.find("author")
        if auth is not None:
            author_tag_str = titlecase(auth.text.strip(":"))
            author_str = titlecase(
                "".join(extract_judge_last_name(author_tag_str))
            )
        else:
            author_str = ""
            author_tag_str = ""

        per_curiam = True if author_tag_str == "Per Curiam" else False
        # If Per Curiam is True set author string to Per Curiam
        if per_curiam:
            author_str = "Per Curiam"

        op_type = map_opinion_type(op.get("type"))
        opinion_xml = str(op)
        logger.info("Adding opinion for: %s", citation.corrected_citation())
        op = Opinion(
            cluster_id=cluster_id,
            type=op_type,
            author_str=author_str,
            xml_harvard=opinion_xml,
            per_curiam=per_curiam,
            extracted_by_ocr=True,
        )
        # Don't index now; do so later if desired
        op.save(index=False)
        new_op_pks.append(op.pk)
    return new_op_pks


def find_previously_imported_cases(
    data: dict[str, Any],
    court_id: Optional[str],
    date_filed: date,
    harvard_characters: str,
    case_name_full: str,
    citation: FullCaseCitation,
) -> Optional[OpinionCluster]:
    """Check if opinion is in Courtlistener

    :param data: The harvard data
    :param court_id: Court ID
    :param date_filed: The date filed
    :param harvard_characters: Harvard stripped down characters
    :param case_name_full: The full case name from Harvard
    :param citation: CL Citation object
    :return: The matching opinion cluster in CL or None
    """

    # Match against known citations.
    for cite in data["citations"]:
        found_cite = get_citations(cite["cite"], tokenizer=HYPERSCAN_TOKENIZER)
        if (
            found_cite
            and isinstance(found_cite[0], FullCaseCitation)
            and found_cite[0].groups.get("volume", False)
        ):
            possible_cases = OpinionCluster.objects.filter(
                citations__reporter=found_cite[0].corrected_reporter(),
                citations__volume=found_cite[0].groups["volume"],
                citations__page=found_cite[0].groups["page"],
            ).order_by("id")
            match = match_based_text(
                harvard_characters,
                data["docket_number"],
                case_name_full,
                possible_cases,
                data["name_abbreviation"],
                citation,
            )
            # If a match is found - return it.  Else keep searching.
            if match:
                return match

    possible_cases = (
        OpinionCluster.objects.filter(
            date_filed=date_filed,
            docket__court_id=court_id,
        )
        .exclude(citations__reporter=citation.corrected_reporter())
        .order_by("id")
    )
    docket_number = data["docket_number"]
    match = match_based_text(
        harvard_characters,
        docket_number,
        case_name_full,
        possible_cases,
        data["name_abbreviation"],
        citation,
    )
    if not match:
        month = timedelta(days=31)
        possible_cases = (
            OpinionCluster.objects.filter(
                date_filed__range=[date_filed - month, date_filed + month],
                docket__court_id=court_id,
            )
            .exclude(citations__reporter=citation.corrected_reporter())
            .exclude(date_filed=date_filed)
            .order_by("id")
        )
        match = match_based_text(
            harvard_characters,
            docket_number,
            case_name_full,
            possible_cases,  # type: ignore
            data["name_abbreviation"],
            citation,
        )
    return match


class Command(VerboseCommand):
    help = "Download and save Harvard corpus on IA to disk."

    def add_arguments(self, parser):
        parser.add_argument(
            "--volumes",
            required=False,
            type=_argparse_volumes,
            help="Ex. '2:10' will fetch volumes 2 to 10 inclusive;"
            "'1:' will start at 1 and to 2000; '5' will do volume 5",
        )
        parser.add_argument(
            "--reporter",
            type=str,
            help="Reporter abbreviation as saved on IA.",
            required=False,
        )
        parser.add_argument(
            "--page",
            type=str,
            help="Opinion page as saved on IA.",
            required=False,
            default=None,
        )
        parser.add_argument(
            "--court-id",
            type=str,
            help="The CL Court ID",
            required=False,
        )
        parser.add_argument(
            "--location",
            type=str,
            help="The location of the court (if applicable) ex. Florida"
            "for courts-db differentiation.",
            required=False,
            default=None,
        )
        parser.add_argument(
            "--make-searchable",
            action="store_true",
            help="Add items to solr as we create opinions. "
            "Items are not searchable unless flag is raised.",
        )
        parser.add_argument(
            "--bankruptcy",
            action="store_true",
            help="Tells function to use bankruptcy courts for bankruptcy "
            "cases.",
        )
        parser.add_argument(
            "--no-debug",
            action="store_true",
            help="Turn off debug logging",
        )

    def handle(self, *args, **options):
        if options["no_debug"]:
            logging.disable(logging.DEBUG)
        parse_harvard_opinions(options)
