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
from cl.corpus_importer.import_columbia.parse_judges import find_judge_names
from cl.corpus_importer.court_regexes import match_court_string
from cl.citations.find_citations import get_citations

from django.conf import settings
from django.db import transaction

from juriscraper.lib.string_utils import titlecase, CaseNameTweaker, harmonize

from reporters_db import REPORTERS

cnt = CaseNameTweaker()


def validate_dt(date_text):
    """
    Check if the date string is only year-month. If partial date string, make
    date string the first of the month and mark the date as an estimate.

    :param date_text: a date string we receive from the harvard corpus
    :returns: Tuple of date or date estimate and boolean indicating estimated
    date or actual date
    """
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return date_text, False
    except ValueError:
        return date_text + "-01", True


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
            settings.MEDIA_ROOT, "harvard_corpus", "%s/*" % reporter_key
        )
    elif reporter:
        reporter_key = ".".join(["law.free.cap", reporter])
        glob_path = os.path.join(
            settings.MEDIA_ROOT, "harvard_corpus", "%s.*/*" % reporter_key
        )
    else:
        glob_path = os.path.join(
            settings.MEDIA_ROOT, "harvard_corpus", "law.free.cap.*/*"
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


def skip_processing(citation, case_name):
    """Run checks for whether to skip the item from being added to the DB

    Cheks include:
     - Is the reporter one we know about in the reporter DB?
     - Can we properly extract the reporter?
     - Can we find a duplicate of the item already in CL?

    :param citation: CL citation object
    :param case_name: The name of the case
    :return: True if the item should be skipped; else False
    """

    # Handle duplicate citations by checking for identical citations and
    # overly similar case names
    cite_search = Citation.objects.filter(
        reporter=citation.reporter, page=citation.page, volume=citation.volume
    )
    if cite_search.count() > 0:
        case_names = OpinionCluster.objects.filter(
            citations=cite_search
        ).values_list("case_name", flat=True)
        case_names = [s.replace("commissioner", "") for s in case_names]
        if check_for_match(case_name, case_names) is not None:
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


def parse_extra_fields(soup):
    """
    Parse the remaining extra fields into long or short strings

    Long fields (1) are wrapped in <p> tags.  Short fields (0) are simple
    commas separated strings
    :param soup: The bs4 representaion of the case data xml
    :return: Returns dictionary of data for saving.
    """
    extra_fields = {
        "attorneys": 0,
        "disposition": 0,
        "otherdate": 0,
        "seealso": 0,
        "syllabus": 1,
        "summary": 1,
        "history": 1,
        "headnotes": 1,
        "correction": 1,
    }

    data_set = {}
    for key, value in extra_fields.items():
        elements = []
        for elem in soup.find_all(key):
            [x.extract() for x in elem.find_all("page-number")]
            if value == 1:
                elements.append("<p>%s</p>" % elem.text)
            else:
                elements.append(elem.text)
        data_set[key] = ", ".join(elements)
    return data_set


def parse_harvard_opinions(reporter, volume):
    """
    Parse downloaded CaseLaw Corpus from internet archive and add them to our
    database.

    Optionally uses a reporter abbreviation to identify cases to download as
    used by IA.  (Ex. T.C. => tc)

    Optionally uses a volume integer.

    If neither is provided, code will cycle through all downloaded files.

    :param volume: The volume (int) of the reporters (optional) (ex 10)
    :param reporter: Reporter string as slugify'd (optional) (tc) for T.C.
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
        if skip_processing(citation, case_name):
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
            extra_fields = parse_extra_fields(soup)

            # Handle partial dates by adding -01v to YYYY-MM dates
            date_filed, is_approximate = validate_dt(data["decision_date"])

            logger.info("Adding cluster for: %s", citation.base_citation())
            cluster = OpinionCluster.objects.create(
                case_name=case_name,
                case_name_short=case_name_short,
                case_name_full=case_name_full,
                precedential_status="Published",
                docket_id=docket.id,
                source="U",
                date_filed=date_filed,
                date_filed_is_approximate=is_approximate,
                attorneys=extra_fields["attorneys"],
                disposition=extra_fields["disposition"],
                syllabus=extra_fields["syllabus"],
                summary=extra_fields["summary"],
                history=extra_fields["history"],
                other_dates=extra_fields["otherdate"],
                cross_reference=extra_fields["seealso"],
                headnotes=extra_fields["headnotes"],
                correction=extra_fields["correction"],
                judges=judges,
                filepath_json_harvard=file_path,
            )

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
            for op in soup.find_all("opinion"):
                # This code cleans author tags for processing.
                # It is particularly useful for identifiying Per Curiam
                for elem in [op.find("author")]:
                    [x.extract() for x in elem.find_all("page-number")]

                author_tag_str = op.find("author").text.strip(":")
                author_str = titlecase("".join(find_judge_names(author_tag_str)))
                per_curiam = True if author_tag_str == "Per Curiam" else False
                # If Per Curiam is True set author string to Per Curiam
                if per_curiam:
                    author_str = "Per Curiam"

                op_type = map_opinion_type(op.get("type"))
                opinion_xml = str(op)
                logger.info("Adding opinion for: %s", citation.base_citation())
                Opinion.objects.create(
                    cluster_id=cluster.id,
                    type=op_type,
                    author_str=author_str,
                    xml_harvard=opinion_xml,
                    per_curiam=per_curiam,
                    extracted_by_ocr=True,
                )

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

    def handle(self, *args, **options):
        reporter = options["reporter"]
        volume = options["volume"]
        parse_harvard_opinions(reporter, volume)
