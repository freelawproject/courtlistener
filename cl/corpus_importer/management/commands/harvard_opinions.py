# !/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
import difflib
import itertools

from glob import glob
from datetime import datetime
from bs4 import BeautifulSoup

from cl.lib.crypto import sha1_of_json_data
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Opinion, OpinionCluster, Docket, Citation
from cl.corpus_importer.import_columbia.parse_judges import find_judge_names
from cl.corpus_importer.court_regexes import match_court_string

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from juriscraper.lib.string_utils import titlecase

from reporters_db import REPORTERS


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
    This code is a variation of find_closest_match used in juriscraper.
    It checks if the case name we are trying to add matches any duplicate
    citation cases already in the system.
    :param new_case: The importing case name
    :param possibilities: The array of cases already in the
    system with the same citation
    :return: Returns the match if any, otherwise returns None.
    """
    try:
        match = difflib.get_close_matches(
            new_case, possibilities, n=1, cutoff=0.7
        )[0]
        return match
    except IndexError:
        # No good matches.
        return None


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

        if OpinionCluster.objects.filter(filepath_local=file_path):
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

        vol = data["volume"]["volume_number"]
        cite = data["citations"][0]["cite"]
        page = cite.split(" ")[-1]
        reporter = cite.split(" ", 1)[1].rsplit(" ", 1)[0]

        if reporter not in REPORTERS.keys():
            logger.info("Reporter '%s' not found in reporter db" % reporter)
            continue

        cite_type = REPORTERS[reporter][0]["cite_type"]
        try:
            assert " ".join([vol, reporter, page]) == cite, (
                "Reporter extraction failed for %s != %s"
                % (cite, " ".join([vol, reporter, page]))
            )
        except (ValueError, Exception):
            logger.info("Case: %s failed to resolve correctly" % cite)
            continue

        cite_search = Citation.objects.filter(
            reporter=reporter, page=page, volume=vol
        )

        # Handle duplicate citations.  By comparing date filed and page count
        # It is unlikely two cases would both start and also stop on the
        # same page.  So we use page count as a proxy for it.
        if cite_search.count() > 0:
            cluster_case_names = OpinionCluster.objects.filter(
                citations=cite_search
            ).values_list("case_name", flat=True)
            if check_for_match(data["name"], cluster_case_names) is not None:
                logger.info("Looks like we already have %s." % data["name"])
                continue
            logger.info("Duplicate cite string but appears to be a new case")

        # TODO: Generalize this to handle all court types somehow.
        court_id = match_court_string(
            data["court"]["name"],
            state=True,
            federal_appeals=True,
            federal_district=True,
        )

        soup = BeautifulSoup(data["casebody"]["data"], "lxml")
        content = data["casebody"]["data"]

        # Some documents contain images in the HTML
        # Flag them for a later crawl by using the placeholder '[[Image]]'
        missing_images = True if content.find("[[Image here]]") > -1 else False
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
        )
        with transaction.atomic():
            logger.info("Adding docket for: %s", cite)
            docket = Docket.objects.create(
                case_name=data["name"],
                docket_number=docket_string,
                court_id=court_id,
                source=Docket.HARVARD,
                ia_needs_upload=False,
                slug=slugify(data["name"]),
            )
            # Iterate over other xml fields in Harvard data set
            # and save as string list   for further processing at a later date.
            json_fields = [
                "attorneys",
                "disposition",
                "syllabus",
                "summary",
                "history",
                "otherdate",
                "seealso",
                "headnotes",
                "correction",
            ]
            data_set = {}
            while json_fields:
                key = json_fields.pop(0)
                data_set[key] = "|".join([x.text for x in soup.find_all(key)])

            # Handle partial dates by adding -01v to YYYY-MM dates
            date_filed, is_approximate = validate_dt(data["decision_date"])

            # Calculate the page count
            pg_count = 1 + int(data["last_page"]) - int(data["first_page"])

            logger.info("Adding cluster for: %s", cite)
            cluster = OpinionCluster.objects.create(
                case_name=data["name"],
                precedential_status="Published",
                docket_id=docket.id,
                source="U",
                slug=slugify(data["name"]),
                date_filed=date_filed,
                date_filed_is_approximate=is_approximate,
                attorneys=data_set["attorneys"],
                disposition=data_set["disposition"],
                syllabus=data_set["syllabus"],
                summary=data_set["summary"],
                history=data_set["history"],
                other_dates=data_set["otherdate"],
                cross_reference=data_set["seealso"],
                headnotes=data_set["headnotes"],
                correction=data_set["correction"],
                judges=judges,
                xml_harvard=str(soup),
                sha1=sha1_of_json_data(json.dumps(data)),
                page_count=pg_count,
                image_missing=missing_images,
                filepath_local=file_path,
            )

            if cite_type == "specialty":
                model_cite_type = Citation.SPECIALTY
            elif cite_type == "federal":
                model_cite_type = Citation.FEDERAL
            elif cite_type == "state":
                model_cite_type = Citation.STATE
            elif cite_type == "state_regional":
                model_cite_type = Citation.STATE_REGIONAL
            elif cite_type == "neutral":
                model_cite_type = Citation.NEUTRAL
            elif cite_type == "lexis":
                model_cite_type = Citation.LEXIS
            elif cite_type == "west":
                model_cite_type = Citation.WEST
            elif cite_type == "scotus_early":
                model_cite_type = Citation.SCOTUS_EARLY
            else:
                model_cite_type = None

            logger.info("Adding citation for: %s", cite)
            Citation.objects.create(
                volume=vol,
                reporter=reporter,
                page=page,
                type=model_cite_type,
                cluster_id=cluster.id,
            )
            for op in soup.find_all("opinion"):
                joined_by_str = titlecase(
                    " ".join(
                        list(set(itertools.chain.from_iterable(judge_list)))
                    )
                )
                author_str = titlecase(
                    " ".join(
                        list(set(itertools.chain.from_iterable(author_list)))
                    )
                )

                if op.get("type") == "unanimous":
                    op_type = "015unamimous"
                elif op.get("type") == "majority":
                    op_type = "020lead"
                elif op.get("type") == "plurality":
                    op_type = "025plurality"
                elif op.get("type") == "concurrence":
                    op_type = "030concurrence"
                elif (
                    op.get("type") == "concurring-in-part-and-dissenting-in"
                    "-part"
                ):
                    op_type = "035concurrenceinpart"
                elif op.get("type") == "dissent":
                    op_type = "040dissent"
                elif op.get("type") == "remittitur":
                    op_type = "060remittitur"
                elif op.get("type") == "rehearing":
                    op_type = "070rehearing"
                elif op.get("type") == "on-the-merits":
                    op_type = "080onthemerits"
                elif op.get("type") == "on-motion-to-strike-cost-bill":
                    op_type = "090onmotiontostrike"
                else:
                    op_type = "010combined"
                opinion_xml = str(op)
                logger.info("Adding opinion for: %s", cite)
                Opinion.objects.create(
                    type=op_type,
                    cluster_id=cluster.id,
                    author_str=author_str,
                    download_url=ia_download_url,
                    xml_harvard=opinion_xml,
                    joined_by_str=joined_by_str,
                )

        logger.info("Finished: %s", cite)


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
