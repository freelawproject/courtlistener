# !/usr/bin/python
# -*- coding: utf-8 -*-

import requests
from django.db.utils import OperationalError
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.model_helpers import clean_docket_number
from cl.lib.string_utils import trunc
from cl.search.models import Docket

cnt = CaseNameTweaker()


def download_file(file_path: str) -> dict[str, str | int]:
    """Download the opinion from IA.

    :param file_path: The opinion file path to download.
    :return: A dict containing the opinion content.
    """

    ia_path = file_path.split("/storage/harvard_corpus/")[1]
    url = f"https://archive.org/download/{ia_path}"
    logger.info(f"Downloading: {url}")
    session = requests.Session()
    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=Retry(
                total=5,
                backoff_factor=10,
            )
        ),
    )
    return session.get(url, timeout=15).json()


def add_docket(
    case_name: str,
    case_name_short: str,
    case_name_full: str,
    docket_number: str,
    court_id: str,
):
    """Create a new docket from the opinion data.

    :param case_name: The docket case name
    :param case_name_short: The docket case name short
    :param case_name_full: The docket case name full
    :param docket_number: The docket number
    :param court_id: The docket court id
    """

    docket = Docket(
        case_name=case_name,
        case_name_short=case_name_short,
        case_name_full=case_name_full,
        docket_number=docket_number,
        court_id=court_id,
        source=Docket.HARVARD,
        ia_needs_upload=False,
    )

    try:
        docket.save()
    except OperationalError as e:
        if "exceeds maximum" in str(e):
            docket.docket_number = (
                "%s, See Corrections for full Docket Number"
                % trunc(docket_number, length=5000, ellipsis="...")
            )
            docket.save()

    return docket


def find_and_fix_mis_matched_dockets(fix: bool) -> list[Docket]:
    """Find and fix mis matched opinion dockets added by Harvard importer.

    :param fix: True if the mis matched docket should be fixed, otherwise it
    will only show a report.
    :return: A list of mis matched dockets.
    """

    logger.info("Finding mis matched dockets ...")
    dockets = Docket.objects.filter(
        source=Docket.HARVARD, pacer_case_id__isnull=False
    )

    mis_matched_dockets = []
    for d in dockets:
        opinion_cluster = d.clusters.all()
        if len(opinion_cluster) == 0:
            logger.info(f"No mis matched docket: {d.pk} ")
            continue
        if len(opinion_cluster) > 1:
            logger.info(
                f"Found more than one OpinionCluster for Docket: {d.pk}"
            )
            continue

        related_opinion = opinion_cluster[0]
        if related_opinion.filepath_json_harvard:
            json_from_ia = download_file(
                str(related_opinion.filepath_json_harvard)
            )
            if not json_from_ia:
                continue

            opinion_docket_number = clean_docket_number(
                str(json_from_ia["docket_number"])
            )
            current_docket_number = clean_docket_number(d.docket_number)
            if opinion_docket_number != current_docket_number:
                mis_matched_dockets.append(d)

                if fix:
                    logger.info(
                        f"Fixed docket for opinion: {related_opinion.pk} "
                    )
                    # Create a new docket based on the original opinion content
                    case_name = harmonize(json_from_ia["name_abbreviation"])
                    case_name_short = cnt.make_case_name_short(case_name)
                    case_name_full = harmonize(json_from_ia["name"])
                    docket_number = str(json_from_ia["docket_number"]).strip()
                    docket_fixed = add_docket(
                        case_name,
                        case_name_short,
                        case_name_full,
                        docket_number,
                        d.court.pk,
                    )

                    # Replace the opinion docket with the new one.
                    related_opinion.docket = docket_fixed
                    related_opinion.save()

                    # Fix mis matched docket source, set it to RECAP.
                    d.source = Docket.RECAP
                    d.save()

    logger.info("List of mis matched dockets: ")
    for md in mis_matched_dockets:
        print(f"https://www.courtlistener.com{md.get_absolute_url()}")

    return mis_matched_dockets


class Command(VerboseCommand):
    help = "Find mis matched opinions/dockets and fix them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Fix mis matched dockets.",
            default=False,
        )

    def handle(self, *args, **options):
        if options["fix"]:
            find_and_fix_mis_matched_dockets(fix=True)
        else:
            find_and_fix_mis_matched_dockets(fix=False)
