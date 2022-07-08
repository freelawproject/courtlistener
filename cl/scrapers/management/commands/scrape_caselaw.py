import json
import os
from pathlib import Path
from typing import TypedDict

import requests
from django.conf import settings

from cl.lib.command_utils import VerboseCommand, logger
from cl.settings import CASELAW_API_KEY


class OptionsType(TypedDict):
    type: str
    cursor: str
    court: str
    jurisdiction: str
    last_updated: str
    last_updated_filter: str
    ordering: str
    body_format: str
    full_case: bool


def get_data(url, params=None):
    header = {"Authorization": f"Token {CASELAW_API_KEY}"}
    logger.info(f"Processing endpoint: {url}")
    try:
        request = requests.get(url, headers=header, params=params, timeout=10)

        print(request.url)

        if request.status_code == 401:
            logger.error("Invalid token header or No credentials provided")
            return None
        if request.status_code == 404:
            logger.error("Endpoint doesn't exist")
            return None
        if request.status_code == 500:
            logger.error("Case.law server error")
            return None

        return request.json()

    except requests.exceptions.ConnectionError:
        return None

    except requests.exceptions.ReadTimeout:
        logger.error("Case.law server timeout, url: ", url)
        return None


def get_from_caselaw(options: OptionsType):
    """Read options, fetch endpoint and store results

    :param options: dict with options passed to management command
    Usage examples:

    Get the cases from 'md' court with last updated date greater than or equal to year
    2022, with full case text in xml
    manage.py scrape_caselaw --type cases --full-case True --body-format xml --court md
    --last- updated 2022 --last-updated-filter gte

    Get all the courts
    manage.py scrape_caselaw --type courts

    """
    type = options["type"]
    cursor = options["cursor"]
    court = options["court"]
    jurisdiction = options["jurisdiction"]
    last_updated = options["last_updated"]
    last_updated_filter = options["last_updated_filter"]
    ordering = options["ordering"]
    body_format = options["body_format"]
    full_case = options["full_case"]
    allowed_types = ["jurisdictions", "courts", "reporters", "cases"]
    base_url = "https://api.case.law"
    version = "v1"
    params = {}
    endpoint = None
    page_size = 1000

    # TODO test how many cases can we collect, there's api calls limit for registered user?

    # TODO handle error_auth_required or error_limit_exceeded when want to get casebody

    if not type:
        logger.error("You didn't provide the type. Exiting.")
        return

    if type not in allowed_types:
        logger.error("You didn't provide the type. Exiting.")
        return

    if last_updated and last_updated_filter:
        if last_updated_filter not in ["gt", "gte", "lt", "lte"]:
            logger.error(
                f"{last_updated_filter} not in options gt, gte, lt, lte."
            )
            return

    if not last_updated and last_updated_filter:
        logger.error(
            "You can't set last-update-filter without passing last-update argument."
        )
        return

    if last_updated and not last_updated_filter:
        logger.error(
            "You can't filter by last-update without passing last-update-filter "
            "argument."
        )
        return

    if full_case and not body_format:
        logger.error(
            "You need to set body-format argument to get full case text. Exiting."
        )
        return

    if not full_case and body_format:
        logger.error(
            "You can't set body-format argument without setting the full-case "
            "argument to True. Exiting. "
        )
        return

    if type == "jurisdictions":
        endpoint = f"{base_url}/{version}/jurisdictions/"
    elif type == "courts":
        endpoint = f"{base_url}/{version}/courts/"
    elif type == "reporters":
        endpoint = f"{base_url}/{version}/reporters/"
    elif type == "cases":
        endpoint = f"{base_url}/{version}/cases/"
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

    # Directory to store data based on type
    directory = Path(settings.MEDIA_ROOT, "case.law", type)

    if cursor:
        # Start from specific cursor
        params["cursor"] = cursor

    while endpoint:
        # We only need to pass the params on first request
        data = get_data(endpoint, params=params)

        if data:
            results_count = data.get("count", None)
            old_endpoint = endpoint
            endpoint = data.get("next", None)
            results = data.get("results", [])

            for result in results:
                # We go through each result
                id = result.get("id")
                filename = f"{id}.json"
                if type == "cases":
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
                    filename = f"{first_page}.{id}.json"
                    # Specific directory tree for cases
                    directory = Path(
                        settings.MEDIA_ROOT,
                        "case.law",
                        type,
                        f"reporter_{reporter_id}",
                        f"volume_{volume_number}",
                    )

                file_path = Path(directory, filename)

                if os.path.exists(file_path):
                    logger.info("Already captured: %s", file_path)
                    continue

                Path(directory).mkdir(parents=True, exist_ok=True)

                with open(file_path, "w") as outfile:
                    json.dump(result, outfile, indent=2)

        else:
            # Something happened, we should probably stop and check what's going on.
            return


class Command(VerboseCommand):
    help = "Download and save Case.law corpus to disk."

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            help="Type to fetch.",
            required=True,
        )

        parser.add_argument(
            "--cursor",
            help="Cursor pagination parameter",
            required=False,
        )

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
            help="Case body format: html or xml. Default: xml.",
            required=False,
        )

        parser.add_argument(
            "--full-case",
            help="Load the case body if true. Default: True.",
            default=False,
            required=False,
        )

    def handle(self, *args, **options):
        get_from_caselaw(options)
