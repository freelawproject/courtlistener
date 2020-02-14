# !/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
import difflib
import itertools

from glob import glob
from datetime import datetime
from bs4 import BeautifulSoup
from juriscraper.lib.diff_tools import normalize_phrase

from cl.citations.utils import map_reporter_db_cite_type
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Opinion, OpinionCluster, Docket, Citation
from cl.search.tasks import add_items_to_solr
from cl.corpus_importer.import_columbia.parse_judges import find_judge_names
from cl.corpus_importer.court_regexes import match_court_string
from cl.citations.find_citations import get_citations

from django.conf import settings
from django.db import transaction

from juriscraper.lib.string_utils import titlecase, CaseNameTweaker, harmonize

from reporters_db import REPORTERS

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
            settings.MEDIA_ROOT, "harvard_corpus", "%s/*.json" % reporter_key
        )
    elif reporter:
        reporter_key = ".".join(["law.free.cap", reporter])
        glob_path = os.path.join(
            settings.MEDIA_ROOT, "harvard_corpus", "%s.*/*.json" % reporter_key
        )
    else:
        glob_path = os.path.join(
            settings.MEDIA_ROOT, "harvard_corpus", "law.free.cap.*/*.json"
        )
    return sorted(glob(glob_path))


def check_for_match(new_case, possibilities):
    """
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
            citations=cite_search
        ).values_list("case_name", "filepath_json_harvard")
        case_names = [s[0] for s in case_data]
        found_filepaths = [s[1] for s in case_data]
        if check_for_match(case_name, case_names) is not None:

            for found_filepath in found_filepaths:
                if found_filepath == file_path or found_filepath == "":
                    # Check if all same citations are Harvard imports
                    # If all Harvard data - match on file_path
                    # If no match assume different case
                    logger.info("Looks like we already have %s." % case_name)
                    return True

        logger.info("Duplicate cite string but appears to be a new case")
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
                elements.append("<p>%s</p>" % elem.text)
            else:
                elements.append(elem.text)
        if long_field:
            data_set[field] = " ".join(elements)
        else:
            data_set[field] = ", ".join(elements)

    return data_set


def parse_harvard_opinions(reporter, volume, make_searchable):
    """
    Parse downloaded CaseLaw Corpus from internet archive and add them to our
    database.

    Optionally uses a reporter abbreviation to identify cases to download as
    used by IA.  (Ex. T.C. => tc)

    Optionally uses a volume integer.

    If neither is provided, code will cycle through all downloaded files.

    :param volume: The volume (int) of the reporters (optional) (ex 10)
    :param reporter: Reporter string as slugify'd (optional) (tc) for T.C.
    :param make_searchable: Boolean to indicate saving to solr
    :return: None
    """
    if not reporter and volume:
        logger.error("You provided a volume but no reporter. Exiting.")
        return

    for file_path in filepath_list(reporter, volume):
        ia_download_url = "/".join(
            ["https://archive.org/download", file_path.split("/", 9)[-1]]
        )

        if OpinionCluster.objects.filter(
            filepath_json_harvard=file_path
        ).exists():
            logger.info("Skipping - already in system %s" % ia_download_url)
            continue

        try:
            with open(file_path) as f:
                data = json.load(f)
        except ValueError:
            logger.warning("Empty json: missing case at: %s" % ia_download_url)
            continue
        except Exception as e:
            logger.warning("Unknown error %s for: %s" % (e, ia_download_url))
            continue

        cites = get_citations(data["citations"][0]["cite"], html=False)
        if not cites:
            logger.info(
                "No citation found for %s." % data["citations"][0]["cite"]
            )
            continue

        case_name = harmonize(data["name_abbreviation"])
        case_name_short = cnt.make_case_name_short(case_name)
        case_name_full = harmonize(data["name"])

        citation = cites[0]
        if skip_processing(citation, case_name, file_path):
            continue

        # TODO: Generalize this to handle all court types somehow.
        court_id = match_court_string(
            data["court"]["name"],
            state=True,
            federal_appeals=True,
            federal_district=True,
        )

        soup = BeautifulSoup(data["casebody"]["data"], "lxml")

        # Some documents contain images in the HTML
        # Flag them for a later crawl by using the placeholder '[[Image]]'
        judge_list = [
            find_judge_names(x.text) for x in soup.find_all("judges")
        ]
        author_list = [
            find_judge_names(x.text) for x in soup.find_all("author")
        ]
        # Flatten and dedupe list of judges
        judges = ", ".join(
            list(set(itertools.chain.from_iterable(judge_list + author_list)))
        )
        judges = titlecase(judges)
        docket_string = (
            data["docket_number"]
            .replace("Docket No.", "")
            .replace("Docket Nos.", "")
            .strip()
        )

        with transaction.atomic():
            logger.info("Adding docket for: %s", citation.base_citation())
            docket = Docket.objects.create(
                case_name=case_name,
                case_name_short=case_name_short,
                case_name_full=case_name_full,
                docket_number=docket_string,
                court_id=court_id,
                source=Docket.HARVARD,
                ia_needs_upload=False,
            )
            # Iterate over other xml fields in Harvard data set
            # and save as string list for further processing at a later date.
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

            # Handle partial dates by adding -01v to YYYY-MM dates
            date_filed, is_approximate = validate_dt(data["decision_date"])

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
            Citation.objects.create(
                volume=citation.volume,
                reporter=citation.reporter,
                page=citation.page,
                type=map_reporter_db_cite_type(
                    REPORTERS[citation.canonical_reporter][0]["cite_type"]
                ),
                cluster_id=cluster.id,
            )
            new_op_pks = []
            for op in soup.find_all("opinion"):
                # This code cleans author tags for processing.
                # It is particularly useful for identifiying Per Curiam
                for elem in [op.find("author")]:
                    if elem is not None:
                        [x.extract() for x in elem.find_all("page-number")]

                auth = op.find("author")
                if auth is not None:
                    author_tag_str = titlecase(auth.text.strip(":"))
                    author_str = titlecase(
                        "".join(find_judge_names(author_tag_str))
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
                    cluster_id=cluster.id,
                    type=op_type,
                    author_str=author_str,
                    xml_harvard=opinion_xml,
                    per_curiam=per_curiam,
                    extracted_by_ocr=True,
                )
                # Don't index now; do so later if desired
                op.save(index=False)
                new_op_pks.append(op.pk)

        if make_searchable:
            add_items_to_solr.delay(new_op_pks, "search.Opinion")

        logger.info("Finished: %s", citation.base_citation())


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
            help="Volume number. If none provided, "
            "code will cycle through all volumes of reporter on IA.",
        )
        parser.add_argument(
            "--reporter",
            help="Reporter abbreviation as saved on IA.",
            required=False,
        )

        parser.add_argument(
            "--make-searchable",
            action="store_true",
            help="Add items to solr as we create opinions. "
            "Items are not searchable unless flag is raised.",
        )

    def handle(self, *args, **options):
        reporter = options["reporter"]
        volume = options["volume"]
        make_searchable = options["make_searchable"]
        parse_harvard_opinions(reporter, volume, make_searchable)
