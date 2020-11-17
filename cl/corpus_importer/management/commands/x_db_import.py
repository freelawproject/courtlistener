# !/usr/bin/python
# -*- coding: utf-8 -*-

import json
import re
from datetime import datetime
from glob import iglob
from typing import Optional, Tuple

from bs4 import BeautifulSoup as bs4
from django.db import transaction
from django.db.utils import OperationalError
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from reporters_db import REPORTERS

from cl.citations.find_citations import get_citations
from cl.citations.utils import map_reporter_db_cite_type
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_utils import trunc
from cl.search.models import Opinion, OpinionCluster, Docket, Citation
from cl.search.tasks import add_items_to_solr

cnt = CaseNameTweaker()


def validate_dt(date_str) -> Tuple[datetime.date, bool]:
    """Validate datetime string
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


def find_cites(data: dict) -> list:
    """Extract citations from raw string

    :param data:
    :return: Found citations.
    """
    found_citations = []
    cites = re.findall(r"\"(.*?)\"", data["lexis_ids_normalized"], re.DOTALL)
    for cite in cites:
        fc = get_citations(cite)
        if len(fc) > 0:
            found_citations.append(fc[0])
    return found_citations


def should_we_add_opinion(cluster_id: int) -> bool:
    """Check if we previously added this document.

    :param cluster_id:
    :return: bool
    """
    ops = Opinion.objects.filter(cluster_id=cluster_id).exclude(html_2020_X="")
    if len(ops) > 0:
        return False
    return True


def check_publication_status(found_cites) -> str:
    """Identify if the opinion is published in a specific reporter

    We can use BTA TC and TC No to identify if the cases are published.

    :param found_cites: Citations found
    :return: Status of the opinion
    """
    for cite in found_cites:
        if cite.reporter == "B.T.A.":
            return "Published"
        if cite.reporter == "T.C.":
            return "Published"
        if cite.reporter == "T.C. No.":
            return "Published"
    return "Unpublished"


def add_only_opinion(soup, cluster_id) -> None:
    """Add opinion to opinion cluster with X db import.

    If already in the system, just add opinion to cluster and move on.

    :param soup: HTML object to save
    :param cluster_id: Cluster ID for the opinion to save
    :return:None
    """
    html_str = str(soup.find("div", {"class": "container"}).decode_contents())
    op = Opinion(
        cluster_id=cluster_id,
        type=Opinion.COMBINED,
        html_2020_X_db=html_str,
        extracted_by_ocr=False,
    )
    op.save()


def check_if_new(cites: list) -> Optional[int]:
    """Check if citation in our system

    :param cites: Array of citations parsed from string
    :return: cluster id for citations
    """
    for citation in cites:
        cite_query = Citation.objects.filter(
            reporter=citation.reporter,
            page=citation.page,
            volume=citation.volume,
        )
        if len(cite_query) > 0:
            return cite_query[0].cluster_id
    return None


def import_x_db(import_dir, skip_until, make_searchable):
    """Import from X db.

    :param test_dir: Location of files to import
    :param skip_until: Skip processing until directory
    :param make_searchable: Should we add content to SOLR
    :return: None
    """

    directories = iglob(f"{import_dir}/*/????-*.json")
    for dir in directories:
        try:
            logger.info(f"Importing: {dir}")
            if skip_until:
                if skip_until in dir:
                    continue
                skip_until = False
            with open(dir, "rb") as f:
                data = json.load(f)

            with open(dir.replace("json", "html"), "rb") as f:
                soup = bs4(f.read(), "html.parser")
            case_name_full = str(
                soup.find("div", {"class": "fullcasename"}).decode_contents()
            )
            found_cites = find_cites(data)

            if found_cites is not None:
                cluser_id = check_if_new(found_cites)
                if cluser_id is not None:
                    add_opinion = should_we_add_opinion(cluser_id)
                    if add_opinion:
                        logger.info(f"Adding opinion to cluster {cluser_id}.")
                        add_only_opinion(soup, cluser_id)
                    else:
                        logger.info(f"Opinion in system at {cluser_id}.")
                    continue

            case_name = harmonize(data["name"])
            case_name_short = cnt.make_case_name_short(case_name)
            case_name_full = harmonize(case_name_full)
            if data["court"] == "United States Tax Court":
                court_id = "tax"
            else:
                court_id = "bta"
            with transaction.atomic():
                logger.info(
                    "Creating docket for: %s", found_cites[0].base_citation()
                )
                try:
                    date_argued, is_approximate = validate_dt(
                        data["date_argued"]
                    )
                except:
                    date_argued, is_approximate = None, None

                docket = Docket(
                    case_name=case_name,
                    case_name_short=case_name_short,
                    case_name_full=case_name_full,
                    docket_number=data["docket_number"],
                    court_id=court_id,
                    source=Docket.X,
                    ia_needs_upload=False,
                    date_argued=date_argued,
                )
                try:
                    with transaction.atomic():
                        docket.save()
                except OperationalError as e:
                    if "exceeds maximum" in str(e):
                        docket.docket_number = (
                            "%s, See Corrections for full Docket Number"
                            % trunc(
                                data["docket_number"],
                                length=5000,
                                ellipsis="...",
                            )
                        )
                        docket.save()
                try:
                    date_filed, is_approximate = validate_dt(
                        data["date_filed"]
                    )
                except:
                    date_filed, is_approximate = validate_dt(
                        data["date_standard"]
                    )
                logger.info(
                    "Adding cluster for: %s", found_cites[0].base_citation()
                )
                status = check_publication_status(found_cites)
                cluster = OpinionCluster(
                    case_name=case_name,
                    case_name_short=case_name_short,
                    case_name_full=case_name_full,
                    precedential_status=status,
                    docket_id=docket.id,
                    source=docket.X,
                    date_filed=date_filed,
                    date_filed_is_approximate=is_approximate,
                    attorneys=data["representation"]
                    if data["representation"] is not None
                    else "",
                    disposition=data["summary_disposition"]
                    if data["summary_disposition"] is not None
                    else "",
                    summary=data["summary_court"]
                    if data["summary_court"] is not None
                    else "",
                    history=data["history"]
                    if data["history"] is not None
                    else "",
                    other_dates=data["date_standard"]
                    if data["date_standard"] is not None
                    else "",
                    cross_reference=data["history_docket_numbers"]
                    if data["history_docket_numbers"] is not None
                    else "",
                    correction=data["publication_status_note"]
                    if data["publication_status_note"] is not None
                    else "",
                    judges=data["judges"].replace("{", "").replace("}", "")
                    if data["judges"] is not None
                    else "",
                )
                cluster.save(index=False)

                for citation in found_cites:
                    logger.info(
                        "Adding citation for: %s", citation.base_citation()
                    )
                    Citation.objects.create(
                        volume=citation.volume,
                        reporter=citation.reporter,
                        page=citation.page,
                        type=map_reporter_db_cite_type(
                            REPORTERS[citation.canonical_reporter][0][
                                "cite_type"
                            ]
                        ),
                        cluster_id=cluster.id,
                    )
                if len(str(soup)) < 10:
                    logger.info(f"Failed: HTML is empty at {dir}")
                    raise MissingDocumentError("Missing HTML content")

                html_str = str(
                    soup.find("div", {"class": "container"}).decode_contents()
                )
                op = Opinion(
                    cluster_id=cluster.id,
                    type=Opinion.COMBINED,
                    html_2020_X=html_str,
                    extracted_by_ocr=False,
                )
                op.save()

                if make_searchable:
                    add_items_to_solr.delay([op.pk], "search.Opinion")

            logger.info("Finished: %s", found_cites[0].base_citation())
            break
        except MissingDocumentError:
            logger.info(f"HTML was empty for {dir}")
        except Exception as e:
            print(str(e))
            logger.info(f"Failed to save {dir} to database.")


class MissingDocumentError(Exception):
    """The document could not be opened or was empty"""

    def __init__(self, message):
        Exception.__init__(self, message)


class Command(VerboseCommand):
    help = "Import X db."

    def add_arguments(self, parser):

        parser.add_argument(
            "--make-searchable",
            action="store_true",
            help="Add items to solr as we create opinions. "
            "Items are not searchable unless flag is raised.",
        )
        parser.add_argument(
            "--import-dir",
            default="cl/assets/media/x-db/all_dir/",
            required=False,
            help="Glob path to the json objects to import",
        )

        parser.add_argument(
            "--skip-until",
            type=str,
            help="Skip processing until we reach the path supplied"
            "at this location is encountered.",
        )

    def handle(self, *args, **options):
        skip_until = options["skip_until"]
        import_dir = options["import_dir"]
        make_searchable = options["make_searchable"]
        import_x_db(import_dir, skip_until, make_searchable)
