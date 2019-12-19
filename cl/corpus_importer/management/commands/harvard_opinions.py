# !/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
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
from django.utils.text import slugify

from reporters_db import REPORTERS


def validate_dt(date_text):
    """
    Check if the date string is only year-month. If partial date string, make
    date string the first of the month and mark the date as an estimate.

    date_text is the date string we receive from the harvard corpus

    :param date_text:
    :returns: Date or date estimate and
    boolean indicating estimated date or actual date
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
        return

    for file_path in filepath_list(reporter, volume):
        ia_download_url = "/".join(
            ["https://archive.org/download", file_path.split("/", 9)[-1]]
        )

        if OpinionCluster.objects.filter(filepath_local=file_path):
            logger.info("Skipping - already in system %s" % ia_download_url)
            continue

        try:
            with open(file_path) as json_data:
                data = json.load(json_data)
        except ValueError:
            logger.warning("Empty json: missing case at: %s" % ia_download_url)
            continue
        except Exception as e:
            logger.warning("Unknown error %s for: %s" % (e, ia_download_url))

        vol = data["volume"]["volume_number"]
        cite = data["citations"][0]["cite"]
        page = cite.split(" ")[-1]
        rep = cite.split(" ", 1)[1].rsplit(" ", 1)[0]

        if rep not in REPORTERS.keys():
            logger.info("Court (%s) not found in reporter db" % rep)
            continue

        cite_type = REPORTERS[rep][0]["cite_type"]
        try:
            assert " ".join([vol, rep, page]) == cite, (
                "Reporter extraction failed for %s != %s"
                % (cite, " ".join([vol, rep, page]))
            )
        except (ValueError, Exception):
            logger.info("Case: %s failed to resolve correctly" % cite)
            continue

        cite_search = (
            Citation.objects.all()
            .filter(reporter=rep)
            .filter(page=page)
            .filter(volume=vol)
        )

        pg_count = 1 + int(data["last_page"]) - int(data["first_page"])

        # Handle duplicate citations.  By comparing date filed and page count
        # I find it unlikely two cases would both start and also stop on the
        # same page.  So we use page count as a proxy for it.
        if cite_search.count() > 0:
            cluster_id = cite_search[0].cluster_id
            cluster = OpinionCluster.objects.filter(id=cluster_id)[0]
            if cluster.date_filed is not None:
                date_filed, is_approximate = validate_dt(data["decision_date"])
                if str(cluster.date_filed) != str(date_filed):
                    logger.info("Duplicate cite string different date filed")
                elif cluster.page_count != pg_count:
                    logger.info("Duplicate cite string but diff page count")
                else:
                    logger.info("%s Already in CL." % cite)
                    continue

        court = match_court_string(
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
        judges = ", ".join(
            list(set(itertools.chain.from_iterable(judge_list + author_list)))
        )
        docket_string = (
            data["docket_number"]
            .replace("Docket No.", "")
            .replace("Docket Nos.", "")
        )
        docket_dictionary = {
            "case_name": data["name"],
            "docket_number": docket_string,
            "court_id": court,
            "source": Docket.HARVARD,
            "ia_needs_upload": False,
            "slug": slugify(data["name"]),
        }
        logger.info("Adding docket for: %s", cite)
        docket = Docket.objects.create(**docket_dictionary)
        data_set = {}

        # Iterate over other xml fields in Harvard data set
        # and save for further processing at a later date.
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
        while json_fields:
            cd = {}
            key = json_fields.pop(0)
            iterations = 0
            for item in [x.text for x in soup.find_all(key)]:
                cd[str(iterations)] = item
                iterations += 1
            if cd == {}:
                cd = ""
            data_set[key] = cd

        # Handle partial dates by adding -01 to YYYY-MM dates
        date_filed, is_approximate = validate_dt(data["decision_date"])

        cluster = {
            "case_name": data["name"],
            "precedential_status": "Published",
            "docket_id": docket.id,
            "source": "U",  # Key for Harvard
            "slug": slugify(data["name"]),
            "date_filed": date_filed,
            "date_filed_is_approximate": is_approximate,
            "attorneys": data_set["attorneys"],
            "disposition": data_set["disposition"],
            "syllabus": data_set["syllabus"],
            "summary": data_set["summary"],
            "history": data_set["history"],
            "other_date": data_set["otherdate"],
            "cross_reference": data_set["seealso"],
            "headnotes": data_set["headnotes"],
            "correction": data_set["correction"],
            "judges": judges,
            "html_harvard": str(soup),
            "sha1": sha1_of_json_data(json.dumps(data)),
            "page_count": pg_count,
            "image_missing": missing_images,
            "filepath_local": file_path,
        }
        logger.info("Adding cluster for: %s", cite)
        cluster = OpinionCluster.objects.create(**cluster)

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
            **{
                "volume": vol,
                "reporter": rep,
                "page": page,
                "type": model_cite_type,
                "cluster_id": cluster.id,
            }
        )
        for op in soup.find_all("opinion"):
            joined_by_str = " ".join(
                list(set(itertools.chain.from_iterable(judge_list)))
            )
            author_str = " ".join(
                list(set(itertools.chain.from_iterable(author_list)))
            )
            if op.get("type") == "unanimous":
                op_type = "015unamimous"
            elif op.get("type") == "majority":
                op_type = "020lead"
            elif op.get("type") == "plurality":
                op_type = "025plurality"
            elif op.get("type") == "concurrence":
                op_type = "030concurrence"
            elif op.get("type") == "concurring-in-part-and-dissenting-in-part":
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
            opinion_data = {
                "type": op_type,
                "cluster_id": cluster.id,
                "author_str": author_str,
                "download_url": ia_download_url,
                "html_harvard": str(op),
                "joined_by_str": joined_by_str,
            }
            logger.info("Adding opinion for: %s", cite)
            Opinion.objects.create(**opinion_data)

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
