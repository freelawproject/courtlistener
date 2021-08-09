# !/usr/bin/python
# -*- coding: utf-8 -*-

import difflib
import itertools
import json
import os
import re
from datetime import datetime, timedelta, date
from glob import glob
from typing import List, Dict, Optional, Any

from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction
from django.db.utils import OperationalError
from eyecite.find_citations import get_citations
from juriscraper.lib.diff_tools import normalize_phrase
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize, titlecase
from reporters_db import REPORTERS

from cl.citations.utils import map_reporter_db_cite_type
from cl.corpus_importer.court_regexes import match_court_string
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_utils import trunc
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.search.models import Citation, Docket, Opinion, OpinionCluster
from cl.search.tasks import add_items_to_solr

cnt = CaseNameTweaker()


def validate_dt(date_str):
    """
    Check if the date string is only year-month or year.
    If partial date string, make date string the first of the month
    and mark the date as an estimate.

    If unable to validate date return an empty string, True tuple.

    :param date_str: a date string we receive from the harvard corpus
    :returns: Tuple of date obj or date obj estimate
    and boolean indicating estimated date or actual date.
    """
    date_approx = False
    add_ons = ["", "-15", "-07-01"]
    for add_on in add_ons:
        try:
            date_obj = datetime.strptime(date_str + add_on, "%Y-%m-%d").date()
            break
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


def check_for_match(new_case, possibilities):
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


def parse_harvard_opinions(options: Dict[str, Any]) -> None:
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
    make_searchable = options["make_searchable"]
    court_id = options["court_id"]

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
        if skip_processing(citation, case_name, file_path):
            continue

        # TODO: Generalize this to handle all court types somehow.
        if not options["court_id"]:
            # Sometimes courts can't match just one court
            # This is used to alleviate certain circumstances
            court_id = match_court_string(
                data["court"]["name"],
                state=True,
                federal_appeals=True,
                federal_district=True,
            )
        # Handle partial dates by adding -01v to YYYY-MM dates
        date_filed, is_approximate = validate_dt(data["decision_date"])
        case_body = data["casebody"]["data"]

        previously_imported_case = find_previously_imported_cases(
            court_id, date_filed, case_body, data["docket_number"]
        )
        if previously_imported_case:
            with transaction.atomic():
                add_citations(
                    data["citations"], cluster_id=previously_imported_case.id
                )
            continue

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
                list(
                    set(
                        itertools.chain.from_iterable(judge_list + author_list)
                    )
                )
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

            logger.info("Adding cluster for: %s", citation.base_citation())
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

            logger.info("Adding citation for: %s", citation.base_citation())
            add_citations(data["citations"], cluster.id)
            new_op_pks = add_opinions(soup, cluster.id, citation)

        if make_searchable:
            add_items_to_solr.delay(new_op_pks, "search.Opinion")

        logger.info("Finished: %s", citation.base_citation())


def add_citations(cites: List, cluster_id: int) -> None:
    """Add citations to OpinionClusters

    :param cites: Harvard Citation data
    :param cluster_id: Cluster of found opinion in DB
    :return:
    """
    for cite in cites:
        citation = get_citations(cite["cite"])
        if not citation:
            continue

        # Because of non-canonical reporters this code breaks for states like
        # Washington.  This is a temporary solution.
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

    :param soup: The bs4 representaion of the case data xml
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


def clean_body_content(case_body: str) -> str:
    """Strip all non alphanumeric characters

    :param case_body: Opinion text
    :return:Opinion text with only alphanumeric characters
    """
    soup = BeautifulSoup(case_body, "lxml")
    return re.sub(r"[^[a-zA-Z]", "", soup.text)


def match_based_text(
    case_body: str, possible_cases: List, docket_number: str
) -> Optional[OpinionCluster]:
    """Compare CL text to Harvard content to establish duplicates

    :param case_body: Harvard case body to compare
    :param possible_cases: List of opinions to check against
    :param docket_number: The docket number
    :return: OpinionCluster or None
    """
    harvard_characters = clean_body_content(case_body)
    for case in possible_cases:
        cl_case_body = get_opinion_content(case)
        cl_characters = clean_body_content(cl_case_body)
        if (
            len(harvard_characters) / len(cl_characters) < 0.3
            or len(harvard_characters) / len(cl_characters) > 3
        ):
            # Content too dissimilar in length to compare
            continue

        percent_match = compare_documents(harvard_characters, cl_characters)
        if percent_match < 45:
            continue
        if len(harvard_characters) < 500:
            if not percent_match in range(98, 102):
                continue
            clean_docket = clean_docket_number(docket_number)
            if clean_docket not in case.docket.docket_number:
                continue
        return case
    return None


def find_previously_imported_cases(
    court_id: str,
    date_filed: date,
    case_body: str,
    docket_number: str,
) -> Optional[OpinionCluster]:
    """Check if opinion is in Courtlistener

    :param court_id: Court ID
    :param date-filed: The date filed
    :param case_body: Date of opinion
    :param docket_number: The docket number
    :return:
    """
    possible_cases = OpinionCluster.objects.filter(
        date_filed=date_filed,
        docket__court_id=court_id,
    ).order_by("id")
    month = timedelta(days=31)
    broad_search = OpinionCluster.objects.filter(
        date_filed__range=[date_filed - month, date_filed + month],
        docket__court_id=court_id,
    ).order_by("id")

    match = match_based_text(case_body, possible_cases, docket_number)
    if not match:
        possible_cases = [
            case for case in broad_search if case.date_filed != date_filed
        ]
        match = match_based_text(case_body, possible_cases, docket_number)
    return match


def compare_documents(harvard_characters: str, cl_characters: str) -> int:
    """Compare Harvard text to CL opinion text

    This code iterates over two opinions logging similar stretches and then
    returns a percentage of the total overlapping characters

    :param harvard_characters: The stripped down opinion text from Harvard
    :param cl_characters: The stripped down opinion text on Courtlistener
    :return: Percentage (as integer) overlapping content
    """

    start, stop, count = 0, 0, 0
    max_string = ""
    hit = False
    while start < len(harvard_characters):
        if start > len(harvard_characters) or stop > len(harvard_characters):
            break
        stop += 1
        if harvard_characters[start:stop] in cl_characters:
            if len(harvard_characters) - start < len(max_string):
                percent_match = int(
                    100
                    * (
                        count
                        / min([len(harvard_characters), len(cl_characters)])
                    )
                )
                return percent_match
            max_string = harvard_characters[start:stop]
            hit = True
        else:
            if hit == True:
                # Only count strings 10 characters or longer
                if len(max_string) > 10:
                    count += len(max_string)
                hit = False
            start = stop + 1
            stop = start + 1
    if len(max_string) > 10:
        count += len(max_string)
    percent_match = int(
        100 * (count / min([len(harvard_characters), len(cl_characters)]))
    )
    return percent_match


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

    def handle(self, *args, **options):
        parse_harvard_opinions(options)
