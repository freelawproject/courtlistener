# !/usr/bin/python
# -*- coding: utf-8 -*-

import difflib
import itertools
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from glob import glob
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, TypedDict

import requests
from bs4 import BeautifulSoup
from courts_db import find_court
from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.db.utils import IntegrityError, OperationalError
from eyecite.find import get_citations
from eyecite.models import FullCaseCitation
from juriscraper.lib.diff_tools import normalize_phrase
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize, titlecase

from cl.citations.utils import map_reporter_db_cite_type
from cl.lib.argparse_types import _argparse_volumes
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_diff import get_cosine_similarity
from cl.lib.string_utils import trunc
from cl.lib.utils import human_sort
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.scrapers.utils import update_or_create_docket
from cl.search.models import (
    SOURCES,
    Citation,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
)
from cl.search.tasks import add_items_to_solr

cnt = CaseNameTweaker()


def validate_dt(date_str: str) -> Tuple[Optional[date], bool]:
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
) -> List[str]:
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
) -> List[str]:
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
    :return: A sorted list of file paths
    """

    files = []
    glob_paths = _make_glob_from_args(reporter, volumes, page)
    for glob_path in glob_paths:
        files.extend(glob(glob_path))
    files = human_sort(files, key=None)  # type: ignore
    return files  # type: ignore


def check_for_match(new_case: str, possibilities: List[str]) -> bool:
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


def parse_extra_fields(soup, fields, long_field=False):
    """
    Parse the remaining extra fields into long or short strings
    returned as dict

    :param soup: The bs4 representaion of the case data xml
    :param fields: An array of strings names for fields to parse
    :param long_field: A boolean decides to parse the field into <p> or simple
    text.
    :return: Returns dictionary of string values to be stored in opinion
    """

    data_set = {}
    for field in fields:
        elements = []
        for elem in soup.find_all(field):
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


def get_fix_list() -> List[str]:
    """Download the fix list for harvard data.

    :return:List of files to fix
    """
    data = requests.get(
        "https://raw.githubusercontent.com/freelawproject/opinionated/main/data/harvard/missing-files.json",
        timeout=10,
    ).json()
    return data["files"]


def merge_fixes(data: Dict[str, Any], identifier: str) -> Dict[str, Any]:
    """Merge fixes into the data

    :param data: The Harvard data
    :param filepath: The filepath of the data to fix.
    :return:
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
    :return: JSON object if avaialble
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
        cites = get_citations(clean_cite)
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
        harvard_characters = clean_body_content(case_body, harvard=True)

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
                add_citations(
                    data["citations"], cluster_id=previously_imported_case.id
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
    data: Dict[str, Any],
    case_body: str,
    case_name: str,
    case_name_full: str,
    case_name_short: str,
    date_filed: Optional[date],
    is_approximate: bool,
    citation: Citation,
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
        extract_judge_last_name(x.text) for x in soup.find_all("judges")
    ]
    author_list = [
        extract_judge_last_name(x.text) for x in soup.find_all("author")
    ]
    # Flatten and dedupe list of judges
    judges = ", ".join(
        sorted(
            list(set(itertools.chain.from_iterable(judge_list + author_list)))
        )
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
                long_data["correction"] = "%s <br> %s" % (
                    data["docket_number"],
                    long_data["correction"],
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
        add_citations(data["citations"], cluster.id)
        new_op_pks = add_opinions(soup, cluster.id, citation)

    if make_searchable:
        add_items_to_solr.delay(new_op_pks, "search.Opinion")

    logger.info("Finished: %s", citation.corrected_citation())
    logger.info(
        f"Finished adding case at https://www.courtlistener.com/opinion/{cluster.id}/{cluster.slug}"
    )


class CitationType(TypedDict):
    cite: str
    type: str


def add_citations(cites: List[CitationType], cluster_id: int) -> None:
    """Add citations to OpinionClusters

    :param cites: Harvard Citation data
    :param cluster_id: Cluster of found opinion in DB
    :return: None
    """
    for cite in cites:
        # Cleanup citations with extra spaces
        clean_cite = re.sub(r"\s+", " ", cite["cite"])
        citation = get_citations(clean_cite)
        if (
            not citation
            or not isinstance(citation[0], FullCaseCitation)
            or not citation[0].groups.get("volume", False)
        ):
            logger.warning(f"Citation parsing failed for {clean_cite}")
            continue

        # Because of non-canonical reporters this code breaks for states like
        # Washington, where there are reporter abbreviations like "wash", that
        # refer to more than one reporter series. The fix here is to eventually
        # look up the abbreviation in reporters DB and see if the cite_type
        # varies across the reporter series it refers to. If so, we have a hard
        # problem -- maybe unsolveable -- if not, we can just use the value we
        # get. In the case of Wash., it refers to two reporter series, both of
        # which are of type "state", so it's easy.

        # We now have an example of non-canonical reporters that do not have
        # the same type, in Arkansas and Ark App. - We can resolve these by
        # defining the regex pattern much more narrowly.  The neutral cite
        # follows a four digit year volume while the state reporter does not.
        if not citation[0].corrected_reporter():
            reporter_type = Citation.STATE
        else:
            cite_type_str = citation[0].all_editions[0].reporter.cite_type
            reporter_type = map_reporter_db_cite_type(cite_type_str)

        try:
            Citation.objects.get_or_create(
                volume=citation[0].groups["volume"],
                reporter=citation[0].corrected_reporter(),
                page=citation[0].groups["page"],
                type=reporter_type,
                cluster_id=cluster_id,
            )
        except IntegrityError:
            logger.warning(
                f"Reporter mismatch for cluster: {cluster_id} on cite: {cite['cite']}"
            )


def add_opinions(
    soup: BeautifulSoup, cluster_id: int, citation: Citation
) -> List[int]:
    """Add opinions to Cluster

    :param soup: The bs4 representation of the case data xml
    :param cluster_id: The cluster ID
    :param citation: Citation object
    :return: Opinion IDs in a list
    """
    new_op_pks = []
    for op in soup.find_all("opinion"):
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


def get_opinion_content(cluster):
    """Get the opinions content for a cluster object

    :param cluster: Cluster ID for a set of opinions
    :return: Combined opinion text
    """
    opinions = []
    for op in Opinion.objects.filter(cluster_id=cluster.id):
        if len(op.html_with_citations) > 1:
            opinions.append(op.html_with_citations)
        elif len(op.html_columbia) > 1:
            opinions.append(op.html_columbia)
        elif len(op.html_lawbox) > 1:
            opinions.append(op.html_lawbox)
        elif len(op.plain_text) > 1:
            opinions.append(op.plain_text)
        elif len(op.html) > 1:
            opinions.append(op.html)
        elif len(op.xml_harvard) > 1:
            opinions.append(op.xml_harvard)
    op = " ".join(opinions)
    soup = BeautifulSoup(op, features="html.parser")
    return soup.text


def clean_docket_number(docket_number: str) -> str:
    """Strip non-numeric content from docket numbers

    :param docket_number: Case docket number
    :return: A stripped down docket number.
    """

    docket_number = re.sub("Department.*", "", docket_number)
    docket_number = re.sub("Nos?. ", "", docket_number)
    return docket_number


def clean_body_content(case_body: str, harvard: bool = False) -> str:
    """Strip all non-alphanumeric characters

    :param case_body: Opinion text
    :param harvard: Are we harvard xml data
    :return:Opinion text with only alphanumeric characters
    """
    soup = BeautifulSoup(case_body, "lxml")
    if not harvard:
        opinion_text = soup.text
    else:
        opinions = []
        for op in soup.find_all("opinion"):
            opinions.append(op.text)
        opinion_text = "".join([op.text for op in soup.find_all("opinion")])

    return re.sub(r"[^a-zA-Z0-9 ]", "", opinion_text.lower())


def length_too_different(
    case: OpinionCluster, harvard_characters: str, cl_characters: str
) -> bool:
    """Check if length is too different between texts

    :param case: The opinion cluster for the case
    :param harvard_characters: The Harvard opinion content characters
    :param cl_characters: The CL opinion content characters
    :return: Whether the content is too different in length
    """
    if len(cl_characters) == 0:
        logger.info(f"Empty Courtlistener opinion cluster: {case.id}")
        return True

    diff = len(harvard_characters) / len(cl_characters)
    if not (0.3 < diff < 3):
        # Content too dissimilar in length to compare
        return True
    return False


def content_too_different(
    case: OpinionCluster,
    harvard_characters: str,
    cl_characters: str,
    docket: str,
) -> bool:
    """Is the content too different

    Check the percentage overlap of two blocks of text

    Florida uses some pretty rote language in the ~650 character
    length that requires a bump in the length for stricter checking.

    This also means the matching threshold has to go for small cases
    completely so a 98% match in washington is not the
    same as a 99% match in Florida

    Require a very close match - with name overlap and
    docket number for very small cases.

    :param case: Opinion cluster for case
    :param harvard_characters: The Harvard opinion content characters
    :param cl_characters: The CL opinion content characters
    :param docket: The Harvard docket number
    :return: Whether the opinion content is too dissimilar
    """

    if len(harvard_characters) > 10000:
        cosine_sim = get_cosine_similarity(harvard_characters, cl_characters)
        if cosine_sim > 0.97:
            return False
        else:
            return True

    percent_match = compare_documents(harvard_characters, cl_characters)
    if percent_match < 60:
        return True

    if len(harvard_characters) > 1000:
        return False

    if percent_match < 90:
        return True

    # If a docket number exists: check against it.
    if case.docket.docket_number is not None:
        clean_docket = clean_docket_number(docket)
        if clean_docket not in case.docket.docket_number:
            return True
    return False


def case_names_dont_overlap(
    case: OpinionCluster, case_name_full: str, case_name_abbreviation: str
) -> bool:
    """Case names not overlap

    Check if the case names have quality overlapping case name words.
    Excludes 'bad words' and other common words.

    :param case: The case opinion cluster
    :param case_name_full: The case name full from Harvard
    :param case_name_abbreviation: The case name abbreviation from Harvard
    :return: Do the case names share quality overlapping words
    """

    harvard_case = f"{case_name_full} {case_name_abbreviation}"
    overlap = winnow_case_name(case.case_name) & winnow_case_name(harvard_case)

    if not overlap:
        return True
    return False


def cosine_similarity_too_different(
    case: OpinionCluster, case_name_full: str, case_name_abbreviation: str
) -> bool:
    """Cosine similarity comparison between case names

    Checks the cosine similarity between a case in CL and Harvard

    :param case: The case opinion cluster
    :param case_name_full: The case name full from Harvard
    :param case_name_abbreviation: The case name abbreviation from Harvard
    :return: Is the cosine similarity too different
    """

    similarities = []
    for title in [case_name_full, case_name_abbreviation]:
        similarity = get_cosine_similarity(title, case.case_name)
        similarities.append(similarity)
    max_similarity = max(similarities)

    if max_similarity < 0.3:
        return True
    return False


def has_too_similar_citation(case: OpinionCluster, citation: Citation) -> bool:
    """Has a citation associated with cluster in same volume

    If you make it this far - we should check if this small case has
    an identical volume reporter citation attached to it already.
    I think this may help us with the wilder v. state issue of having
    four identical opinions only differentiated by page number

    :param case: The case opinion cluster
    :param citation: The citation of a potential matching
    :return: Whether the citation matches to the reporter and volume.
    """

    return (
        Citation.objects.filter(
            cluster_id=case.id,
            reporter=citation.corrected_reporter(),
        )
        .exclude(
            page=citation.groups["page"], volume=citation.groups["volume"]
        )
        .exists()
    )


def match_based_text(
    harvard_characters: str,
    docket_number: str,
    case_name_full: str,
    possible_cases: QuerySet,
    case_name_abbreviation: str,
    citation: Citation,
) -> Optional[OpinionCluster]:
    """Compare CL text to Harvard content to establish duplicates

    :param harvard_characters: Harvard stripped characters to compare
    :param possible_cases: List of opinions to check against
    :param docket_number: The docket number
    :param case_name_full: The full case name
    :return: OpinionCluster or None
    """
    for case in possible_cases:
        cl_case_body = get_opinion_content(case)
        cl_characters = clean_body_content(cl_case_body)

        if len(cl_characters) == 0:
            logger.warning(
                f"Empty opinion at https://www.courtlistener.com/opinion/{case.id}/{case.slug}"
            )
            continue

        case_and_texts = [case, harvard_characters, cl_characters]
        case_and_texts_and_docket = case_and_texts + [docket_number]
        case_and_titles = [case, case_name_full, case_name_abbreviation]
        if (
            length_too_different(*case_and_texts)
            or has_too_similar_citation(case, citation)
            or case_names_dont_overlap(*case_and_titles)
            or cosine_similarity_too_different(*case_and_titles)
            or content_too_different(*case_and_texts_and_docket)
        ):
            continue
        return case
    return None


def find_previously_imported_cases(
    data: Dict[str, Any],
    court_id: Optional[str],
    date_filed: date,
    harvard_characters: str,
    case_name_full: str,
    citation: Citation,
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
        found_cite = get_citations(cite["cite"])
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


def winnow_case_name(case_name: str) -> Set:
    """Reduce each case title to a set of words worth comparing

    :param case_name: The name of a case or combination of case names
    :return: A set of words worth comparing
    """
    false_positive_set = {
        "and",
        "personal",
        "restraint",
        "matter",
        "washington",
        "florida",
        "county",
        "city",
        "of",
        "the",
        "state",
        "estate",
        "in",
        "inc",
        "st",
        "ex",
        "rel",
    }

    # strings where order matters
    false_positive_strings = ["united states"]

    false_positive_strings_regex = re.compile(
        "|".join(map(re.escape, false_positive_strings))
    )

    # Fix case name to be cleaner
    case_name = harmonize(case_name)

    # Join abbreviations/acronyms. e.g. "D.L.M. v. T.J.S." -> "DLM v. TJS"
    case_name = re.sub(
        r"\b[a-zA-Z][a-zA-Z\.]*[A-Za-z]\b\.?",
        lambda m: m.group().replace(".", ""),
        case_name,
    )

    # Remove all non-alphanumeric characters
    case_title = re.sub(r"[^a-z0-9 ]", " ", case_name.lower())

    # Remove strings that can cause an unnecessary overlap
    case_title = false_positive_strings_regex.sub("", case_title)

    # Remove one-letter words, initials etc.
    case_title = re.sub(r"\b[^ ]\b", "", case_title)

    if not case_title:
        # Log case name if the process reduce it to blank
        logger.warning(f"Case name: {case_name} reduced to blank.")

    # Convert case name to set of words
    cleaned_set = set(case_title.split())

    # Lastly remove our ever-growing set of false positive words
    # This is different from bad words, but may have some overlap.
    return cleaned_set - (cleaned_set & false_positive_set)


def compare_documents(harvard_characters: str, cl_characters: str) -> int:
    """Compare Harvard text to CL opinion text

    This code iterates over two opinions logging similar stretches and then
    returns a percentage of the total overlapping characters

    :param harvard_characters: The stripped down opinion text from Harvard
    :param cl_characters: The stripped down opinion text on Courtlistener
    :return: Percentage (as integer) overlapping content
    """

    start, stop, count = 0, 0, 0
    matched_substring = ""
    found_overlaps = []
    while stop < len(harvard_characters):
        stop += 1
        harvard_substring = harvard_characters[start:stop]
        if harvard_substring in cl_characters:
            matched_substring = harvard_substring
        else:
            if len(matched_substring) > 5:
                subset = make_subset_range(cl_characters, matched_substring)
                found_overlaps.append(subset)
            matched_substring = ""
            start = stop - 1
    if len(matched_substring) > 5:
        subset = make_subset_range(cl_characters, matched_substring)
        found_overlaps.append(subset)

    # If we checked our subsets as we parsed- we wouldn't need to do this
    # filtering here. This is a good candidate for refactoring.
    filtered_subset = list(filter_subsets(found_overlaps))
    for overlap in filtered_subset:
        count += len(overlap)
    percent_match = int(
        100 * (count / min([len(harvard_characters), len(cl_characters)]))
    )
    return percent_match


def make_subset_range(cl_characters: str, max_string: str) -> List[int]:
    """Find indices for matching max_string in CL opinion

    :param cl_characters: The stripped down CL characters
    :param max_string: The current largest identified substring
    :return: Range of indicies of match to CL as list
    """
    string_index_start = cl_characters.find(max_string)
    string_index_end = string_index_start + len(max_string)
    return list(range(string_index_start, string_index_end))


def is_subset(match: List[int], other_match: List[int]) -> bool:
    """Check if match is a subset of other matches

    Check if needle is ordered subset of haystack in O(n)
    :param match: Matching range of text as the indices
    :param other_match: Other matching range of text as indices
    :return: Is match a subset of other match
    """

    if len(other_match) < len(match):
        return False
    index = 0
    for element in match:
        try:
            index = other_match.index(element, index) + 1
        except ValueError:
            return False
    else:
        return True


def filter_subsets(lists: List[List[int]]) -> Iterator[List[int]]:
    """Filter subsets from matches

    Given list of lists, return new list of lists without subsets

    :param lists: List of matched lists ranges
    :return: Reduced list of matches
    """

    for match in lists:
        if not any(
            is_subset(match, other_matches)
            for other_matches in lists
            if match is not other_matches
        ):
            yield match


class MissingDocumentError(Exception):
    """The document could not be opened or was empty"""

    def __init__(self, message):
        Exception.__init__(self, message)


class ParsingError(Exception):
    """The document could not be opened or was empty"""

    def __init__(self, message):
        Exception.__init__(self, message)


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
