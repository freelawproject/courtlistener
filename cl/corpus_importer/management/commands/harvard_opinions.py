# !/usr/bin/python
# -*- coding: utf-8 -*-

import difflib
import itertools
import json
import logging
import math
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta
from glob import glob
from typing import Any, Dict, Iterator, List, Optional, Tuple, TypedDict

from bs4 import BeautifulSoup
from courts_db import find_court_ids_by_name
from django.conf import settings
from django.db import transaction
from django.db.utils import OperationalError
from eyecite.find_citations import get_citations
from juriscraper.lib.diff_tools import normalize_phrase
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize, titlecase
from reporters_db import REPORTERS

from cl.citations.utils import map_reporter_db_cite_type
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_utils import trunc
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.search.models import Citation, Docket, Opinion, OpinionCluster
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
    date_obj = None
    date_approx = False
    add_ons = ["", "-15", "-07-01"]
    for add_on in add_ons:
        try:
            date_obj = datetime.strptime(date_str + add_on, "%Y-%m-%d").date()
        except ValueError:
            # Failed parsing at least once, ∴ an approximate date
            date_approx = True
    return date_obj, date_approx


def filepath_list(reporter, volume):
    """Given a reporter and volume, return a sorted list of files to process

    Make a list of file paths accordingly:
     - If neither a reporter nor a volume are given, do all cases from all
       volumes of all reporters.
     - If a only reporter is given, do all cases in all volumes for that
       reporter.
     - If a reporter and volume are both given, only do cases from that volume
       of that reporter.

    :param reporter: The reporter to filter to (optional)
    :param volume: The volume of the reporter to filter to (optional)
    :return: A sorted list of file paths
    """
    if reporter and volume:
        reporter_key = ".".join(["law.free.cap", reporter, volume])
        glob_path = os.path.join(
            settings.MEDIA_ROOT, "harvard_corpus", f"{reporter_key}/*.json"
        )
    elif reporter:
        reporter_key = ".".join(["law.free.cap", reporter])
        glob_path = os.path.join(
            settings.MEDIA_ROOT, "harvard_corpus", f"{reporter_key}.*/*.json"
        )
    else:
        glob_path = os.path.join(
            settings.MEDIA_ROOT, "harvard_corpus", "law.free.cap.*/*.json"
        )
    return sorted(glob(glob_path))


def get_cosine(vec1: Counter, vec2: Counter) -> float:
    """Get cosine simililarity between two counter dictionaries

    :param vec1: A vectorized string to compare
    :param vec2: A vectorized string to compare
    :return: The cosine similarity
    """
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum([vec1[x] * vec2[x] for x in intersection])

    sum1 = sum([vec1[x] ** 2 for x in list(vec1.keys())])
    sum2 = sum([vec2[x] ** 2 for x in list(vec2.keys())])
    denominator = math.sqrt(sum1) * math.sqrt(sum2)

    if not denominator:
        return 0.0
    else:
        return float(numerator) / denominator


WORD = re.compile(r"\w+")


def text_to_vector(text: str) -> Counter:
    """Convert text line to collections dictionary

    :param text: Case title to compare
    :return: Counter for all words
    """
    words = WORD.findall(text)
    return Counter(words)


def get_cosine_similarity(cl_case: str, possibilities: List[str]):
    """Calculate cosine similarity between harvard and cl case names

    Generally anything around 1 is good - but matches as low as .3 could
    be good.  This is generally my favorite way to identify similar text

    :param cl_case: Courtlistener Case title
    :param possibilities: List of case names from the harvard data set
    :return: Largest cosine match
    """
    cosines = []
    for possibilty in possibilities:
        vector_match = get_cosine(
            text_to_vector(cl_case), text_to_vector(possibilty)
        )
        cosines.append(vector_match)
    return max(cosines)


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
        return match
    except IndexError:
        # No good matches.
        return None


def skip_processing(citation, case_name, file_path):
    """Run checks for whether to skip the item from being added to the DB

    Checks include:
     - Is the reporter one we know about in the reporter DB?
     - Can we properly extract the reporter?
     - Can we find a duplicate of the item already in CL?
     - If we think we have a match - check if all matches are harvard cases
       and compare against filepaths.

    :param citation: CL citation object
    :param case_name: The name of the case
    :param file_path: The file_path of our case
    :return: True if the item should be skipped; else False
    """

    # Handle duplicate citations by checking for identical citations and
    # overly similar case names
    cite_search = Citation.objects.filter(
        reporter=citation.reporter, page=citation.page, volume=citation.volume
    )
    if cite_search.count() > 0:
        case_data = OpinionCluster.objects.filter(
            citations__in=cite_search
        ).values_list("case_name", "filepath_json_harvard")
        case_names = [s[0] for s in case_data]
        found_filepaths = [s[1] for s in case_data]
        if check_for_match(case_name, case_names) is not None:

            for found_filepath in found_filepaths:
                if found_filepath == file_path:
                    # Check if all same citations are Harvard imports
                    # If all Harvard data - match on file_path
                    # If no match assume different case
                    logger.info(f"Looks like we already have {case_name}.")
                    return True

        logger.info(
            f"Duplicate cite string but appears to be a new case {case_name}"
        )
    return False


def map_opinion_type(harvard_opinion_type):
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
    volume: str
    court_id: Optional[str]
    make_searchable: bool


def parse_harvard_opinions(options: OptionsType) -> None:
    """Parse Harvard Opinions

    Parse downloaded CaseLaw Corpus from internet archive and add them to our
    database.

    Optionally uses a reporter abbreviation to identify cases to download as
    used by IA.  (Ex. T.C. => tc)

    Optionally uses a volume integer.

    If neither is provided, code will cycle through all downloaded files.

    :param options: The command line options including (reporter,
    volume court_id and make_searchable)
    :return: None
    """

    reporter = options["reporter"]
    volume = options["volume"]
    court_id = options["court_id"]
    make_searchable = options["make_searchable"]

    if not reporter and volume:
        logger.error("You provided a volume but no reporter. Exiting.")
        return

    for file_path in filepath_list(reporter, volume):
        ia_download_url = "/".join(
            ["https://archive.org/download", file_path.split("/", 9)[-1]]
        )

        oc = OpinionCluster.objects.filter(filepath_json_harvard=file_path)
        if len(oc) > 0:
            logger.info(
                f"Skipping {oc[0].id} - already in system {ia_download_url}"
            )
            continue

        try:
            with open(file_path) as f:
                data = json.load(f)
        except ValueError:
            logger.warning(f"Empty json: missing case at: {ia_download_url}")
            continue
        except Exception as e:
            logger.warning(f"Unknown error {e} for: {ia_download_url}")
            continue

        cites = get_citations(data["citations"][0]["cite"])
        if not cites:
            logger.info(
                f"No citation found for {data['citations'][0]['cite']}."
            )
            continue

        case_name = harmonize(data["name_abbreviation"])
        case_name_short = cnt.make_case_name_short(case_name)
        case_name_full = harmonize(data["name"])

        citation = cites[0]

        # TODO: Generalize this to handle all court types somehow.
        if not options["court_id"]:
            # Sometimes the court string doesn't match just one court
            # This is used to alleviate certain circumstances.
            found_court = find_court_ids_by_name(
                data["court"]["name"], bankruptcy=False
            )
            if len(found_court) != 1:
                logging.info(
                    f"Court not found for {data['court']['name']} at {file_path}"
                )
                continue

            court_id = found_court[0]
        # Handle partial dates by adding -01 to YYYY-MM dates
        date_filed, is_approximate = validate_dt(data["decision_date"])
        case_body = data["casebody"]["data"]
        harvard_characters = clean_body_content(case_body, harvard=True)

        if not harvard_characters:
            # Unfortunately, some harvard cases have no opinions.
            # See: https://cite.case.law/pdf/1305086/Vinson%20v.%20Cox,%2099%20Fla.%201373%20(1930).pdf
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
            continue

        logger.info(f"Adding case {case_name_full}")
        # This case appears new to CL - lets add it.
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
    date_filed: date,
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
            f"Adding docket for {case_name}: {citation.base_citation()}"
        )
        docket = Docket(
            case_name=case_name,
            case_name_short=case_name_short,
            case_name_full=case_name_full,
            docket_number=docket_string,
            court_id=court_id,
            source=Docket.HARVARD,
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
            source="U",
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

        logger.info("Adding citation for: %s", citation.base_citation())
        add_citations(data["citations"], cluster.id)
        new_op_pks = add_opinions(soup, cluster.id, citation)

    if make_searchable:
        add_items_to_solr.delay(new_op_pks, "search.Opinion")

    logger.info("Finished: %s", citation.base_citation())
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
        citation = get_citations(cite["cite"])
        if not citation:
            logger.warning(f"Citation parsing failed for {cite['cite']}")
            continue

        # Because of non-canonical reporters this code breaks for states like
        # Washington, where there are reporter abbreviations like "wash", that
        # refer to more than one reporter series. The fix here is to eventually
        # look up the abbreviation in e reporters DB and see if the cite_type
        # varies across the reporter series it refers to. If so, we have a hard
        # problem -- maybe unsolveable -- if not, we can just use the value we
        # get. In the case of Wash., it refers to two reporter series, both of
        # which are of type "state", so it's easy.
        if not citation[0].canonical_reporter:
            reporter_type = Citation.STATE
        else:
            reporter_type = map_reporter_db_cite_type(
                REPORTERS[citation[0].canonical_reporter][0]["cite_type"]
            )

        Citation.objects.get_or_create(
            volume=citation[0].volume,
            reporter=citation[0].reporter,
            page=citation[0].page,
            type=reporter_type,
            cluster_id=cluster_id,
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
        logger.info("Adding opinion for: %s", citation.base_citation())
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
        elif len(op.plain_text) > 1:
            opinions.append(op.plain_text)
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

    return re.sub(r"[^a-zA-Z0-9]", "", opinion_text.lower())


def match_based_text(
    harvard_characters: str,
    docket_number: str,
    case_name_full: str,
    possible_cases: List,
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
            logger.info(f"Empty Courtlistener opinion cluster: {case.id}")
            continue

        diff = len(harvard_characters) / len(cl_characters)
        if not (0.3 < diff < 3):
            # Content too dissimilar in length to compare
            continue

        percent_match = compare_documents(harvard_characters, cl_characters)
        if percent_match < 60:
            continue

        # Require some overlapping case title
        overlaps = overlap_case_names(
            case.case_name, [case_name_full, case_name_abbreviation]
        )
        if not overlaps:
            continue

        vector_match = get_cosine_similarity(
            case.case_name, [case_name_full, case_name_abbreviation]
        )
        if vector_match < 0.3:
            continue

        # The threshold for washington state cases was around 500 but for florida
        # it appears to be around 650.  Bumping the threshold for more intense
        # comparisons to 1000 to be safe.
        if len(harvard_characters) < 1000:
            # Florida uses some pretty rote language in the ~650 character
            # length that requires a bump in the length for stricter checking.

            # This also means the matching threshold has to go for small cases
            # completely so a 98% match in washington is not the
            # same as a 99% match in Florida

            # Require a very close match - with name overlap and
            # docket number for very small cases.
            if percent_match < 90:
                continue

            # If a docket number exists: check against it.
            if case.docket.docket_number is not None:
                clean_docket = clean_docket_number(docket_number)
                if clean_docket not in case.docket.docket_number:
                    continue

            # If you make it this far - we should check if this small case has
            # an identifical volume reporter citation attached to it already.
            # I think this may help us with the wilder v. state issue of having
            # four identical opinions only differentiated by page number

            similar_cites = Citation.objects.filter(
                cluster_id=case.id,
                reporter=citation.reporter,
            ).exclude(page=citation.page, volume=citation.volume)
            if similar_cites:
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
        if found_cite:
            possible_cases = OpinionCluster.objects.filter(
                citations__reporter=found_cite[0].reporter,
                citations__volume=found_cite[0].volume,
                citations__page=found_cite[0].page,
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

    possible_cases = OpinionCluster.objects.filter(
        date_filed=date_filed,
        docket__court_id=court_id,
    ).order_by("id")

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
        broad_search = OpinionCluster.objects.filter(
            date_filed__range=[date_filed - month, date_filed + month],
            docket__court_id=court_id,
        ).order_by("id")
        possible_cases = [
            case for case in broad_search if case.date_filed != date_filed
        ]
        match = match_based_text(
            harvard_characters,
            docket_number,
            case_name_full,
            possible_cases,
            data["name_abbreviation"],
            citation,
        )
    return match


def overlap_case_names(
    cl_case_name: str, harvard_case_names: List[str]
) -> List[str]:
    """Find overlapping case names - excluding certain words.

    Convert each string to a list - stripped of punctuation and compares for
    overlapping case title words.  After which we remove superflous words that
    create false positives

    We use two differnet title types because of the variety of abbreviations
    and usage across case names.

    :param cl_case_name: The CL case name
    :param harvard_case_names: The Harvard case name and abbreviation in a list
    :return: List of overlapping case names
    """
    overlaps = []
    for harvard_case_name in harvard_case_names:
        cl_case_name = re.sub(r"[^a-zA-Z0-9 ]", " ", cl_case_name)
        harvard_case_name = re.sub(r"[^a-zA-Z0-9 ]", " ", harvard_case_name)
        cl_case_name_list = cl_case_name.lower().split()
        harvard_case_name_list = harvard_case_name.strip().lower().split()

        matches = list(
            set(cl_case_name_list).intersection(harvard_case_name_list)
        )
        false_positive_list = [
            "et",
            "al",
            "respondent",
            "respondents",
            "appellant",
            "and",
            "personal",
            "restraint",
            "matter",
            "washington",
            "florida",
            "county" "city",
            "appellants",
            "of",
            "the",
            "state",
            "estate",
            "in",
            "inc",
            "st",
            "ex",
            "rel",
        ]
        overlaps = overlaps + [
            word
            for word in matches
            if len(word) > 1 and word not in false_positive_list
        ]
    return list(set(overlaps))


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

    # If we checked our subsets as we parsed- we wouldnt need to do this
    # filtering here. This is a good candiate for refactoring.
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
            "--volume",
            type=str,
            help="Volume number. If none provided, "
            "code will cycle through all volumes of reporter on IA.",
        )
        parser.add_argument(
            "--reporter",
            type=str,
            help="Reporter abbreviation as saved on IA.",
            required=False,
        )
        parser.add_argument(
            "--court-id",
            type=str,
            help="The CL Court ID",
            required=False,
        )
        parser.add_argument(
            "--make-searchable",
            action="store_true",
            help="Add items to solr as we create opinions. "
            "Items are not searchable unless flag is raised.",
        )
        parser.add_argument(
            "--no-debug",
            action="store_true",
            help="Turn off debug logging",
        )

    def handle(self, *args, **options):
        if options['no_debug']:
            logging.disable(logging.DEBUG)
        parse_harvard_opinions(options)
