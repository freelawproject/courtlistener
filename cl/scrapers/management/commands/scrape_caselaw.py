import json
import os
from pathlib import Path
from typing import TypedDict, Union

import requests
from django.conf import settings

from cl.lib.command_utils import VerboseCommand, logger

reporters_slugs = dict()


class CaseLawOptionsType(TypedDict):
    """Define caselaw scraper command option types"""

    court: str
    jurisdiction: str
    last_updated: str
    last_updated_filter: str
    ordering: str
    body_format: str
    full_case: bool
    reporter_id: int
    source: str


def get_data(url: str, params=None) -> Union[dict, None]:
    """Request GET method endpoint
    :param url: endpoint url
    :param params: additional params to pass to the request
    :return: json response or None
    """
    header = {}
    logger.info(f"Processing endpoint: {url}")
    try:
        request = requests.get(url, headers=header, params=params, timeout=10)

        if request.status_code == 401:
            logger.warning("Invalid token header or No credentials provided")
            return None
        if request.status_code == 404:
            logger.warning("Endpoint doesn't exist")
            return None
        if request.status_code == 500:
            logger.warning("Case.law server error")
            return None

        return request.json()

    except requests.exceptions.ConnectionError:
        return None

    except requests.exceptions.ReadTimeout:
        logger.warning("Case.law server timeout, url: ", url)
        return None


def get_reporter_slug(reporter_endpoint: str) -> Union[str, None]:
    """Get reporter slug from reporter endpoint
    :param reporter_endpoint: Reporter instance endpoint
    :return: reporter slug or None
    """
    global reporters_slugs
    if reporters_slugs.get(reporter_endpoint):
        # Check if slug is already stored in global variable to avoid
        # unnecessary requests
        return reporters_slugs.get(reporter_endpoint)
    data = get_data(reporter_endpoint)
    if data:
        frontend_url = data.get("frontend_url")
        if frontend_url:
            url = [y for y in frontend_url.split("/") if y]
            if url:
                # Store and return reporter slug from url
                reporters_slugs[reporter_endpoint] = url[-1]
                return url[-1]
    return None


def get_from_caselaw(options: CaseLawOptionsType):
    """Read options, fetch endpoint and store results
    :param options: dict with options passed to management command

    Usage examples:

    Get the cases from 'md' court with last updated date greater than or equal to year
    2022, with full case text in xml
    manage.py scrape_caselaw --full-case True --body-format xml --court md
    --last- updated 2022 --last-updated-filter gte

    Get all fastcase cases
    manage.py scrape_caselaw --source Fastcase --full-case True --body-format xml

    """
    court = options["court"]
    jurisdiction = options["jurisdiction"]
    last_updated = options["last_updated"]
    last_updated_filter = options["last_updated_filter"]
    ordering = options["ordering"]
    body_format = options["body_format"]
    full_case = options["full_case"]
    reporter_id = options["reporter_id"]
    source = options["source"]

    base_url = "https://api.case.law"
    version = "v1"
    params = {}
    page_size = 1000

    if last_updated and last_updated_filter:
        if last_updated_filter not in ["gt", "gte", "lt", "lte"]:
            logger.warning(
                f"{last_updated_filter} not in options gt, gte, lt, lte."
            )
            return

    if not last_updated and last_updated_filter:
        logger.warning(
            "You can't set last-update-filter without passing last-update argument."
        )
        return

    if last_updated and not last_updated_filter:
        logger.warning(
            "You can't filter by last-update without passing last-update-filter "
            "argument."
        )
        return

    if full_case and not body_format:
        logger.warning(
            "You need to set body-format argument to get full case text. Exiting."
        )
        return

    if not full_case and body_format:
        logger.warning(
            "You can't set body-format argument without setting the full-case "
            "argument to True. Exiting. "
        )
        return

    if source and source not in ["Harvard", "Fastcase"]:
        logger.warning(
            "Invalid source. Valid sources: Harvard or Fastcase. Exiting. "
        )
        return

    # Cases endpoint
    endpoint = f"{base_url}/{version}/cases/"

    # Add params to dict
    params["page_size"] = page_size
    if ordering:
        params["ordering"] = ordering
    if court:
        params["court"] = court
    if jurisdiction:
        params["jurisdiction"] = jurisdiction
    if full_case:
        params["full_case"] = "true" if full_case else "false"
    if body_format:
        params["body_format"] = body_format
    if last_updated and last_updated_filter:
        params[f"last_updated__{last_updated_filter}"] = last_updated
    if reporter_id:
        params["reporter"] = reporter_id
    if source:
        params["source"] = source

    while endpoint:
        data = get_data(endpoint, params=params)
        last_endpoint_call = endpoint
        # We only need to pass the params on first request
        params = {}

        if data:
            endpoint = data.get("next", None)
            results = data.get("results", [])

            for result in results:
                # We go through each result
                id = result.get("id")

                volume_number = (
                    result.get("volume").get("volume_number")
                    if result.get("volume")
                    else None
                )
                first_page = result.get("first_page")
                reporter_id = (
                    result.get("reporter").get("id")
                    if result.get("reporter")
                    else None
                )
                reporter_url = (
                    result.get("reporter").get("url")
                    if result.get("reporter")
                    else None
                )

                reporter_slug = get_reporter_slug(reporter_url)

                if not reporter_slug:
                    # No slug from url, use reporter id, this will be used to
                    # set reporter and volume output directory
                    reporter_slug = reporter_id

                filename = f"{first_page}.{id}.json"
                # Specific directory tree for cases
                directory = Path(
                    settings.MEDIA_ROOT,
                    "harvard_corpus",
                    f"law.free.cap.{reporter_slug}.{volume_number}",
                )

                file_path = Path(directory, filename)

                if os.path.exists(file_path):
                    logger.info("Already captured: %s", file_path)
                    continue

                Path(directory).mkdir(parents=True, exist_ok=True)

                try:
                    # x mode to avoid overwriting files
                    with open(file_path, "x") as outfile:
                        json.dump(result, outfile, indent=2)
                except FileExistsError:
                    # The file already exists, but somehow an attempt was made to save
                    # it again.
                    logger.info("Already captured: %s", file_path)
                    continue

        else:
            # Something happened, we should probably stop and check what's going on.
            # Probably a server error from case.law
            logger.warning(
                f"Problem during request, url: {last_endpoint_call}"
            )
            return


class Command(VerboseCommand):
    help = "Download and save Case.law corpus to disk."

    def add_arguments(self, parser):
        parser.add_argument(
            "--court",
            help="Filter cases by court slug",
            required=False,
        )

        parser.add_argument(
            "--jurisdiction",
            help="Filter cases by jurisdiction slug",
            required=False,
        )

        parser.add_argument(
            "--last-updated",
            help="Filter cases by last update. Format: YYYY-MM-DDTHH:MM:SS or "
                 "YYYY-MM-DD or YYYY-MM or YYYY",
            required=False,
        )

        parser.add_argument(
            "--last-updated-filter",
            help="Indicate filter by last update is gt, gte, lt, lte. Default: None ("
                 "exact match).",
            required=False,
        )

        parser.add_argument(
            "--ordering",
            help="Sort cases by field name",
            required=False,
        )

        parser.add_argument(
            "--body-format",
            help="Case body format: html or xml.",
            required=False,
        )

        parser.add_argument(
            "--full-case",
            help="Load the case body if true. Default: False.",
            default=False,
            required=False,
        )

        parser.add_argument(
            "--reporter-id",
            help="Filter cases by reporter id. Ids from "
                 "https://api.case.law/v1/reporters/",
            default=False,
            required=False,
        )

        parser.add_argument(
            "--source",
            help="Filter by source. Harvard or Fastcase.",
            default=False,
            required=False,
        )

    def handle(self, *args, **options):
        get_from_caselaw(options)
