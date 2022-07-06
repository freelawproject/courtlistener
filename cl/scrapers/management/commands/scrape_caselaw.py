import json
import os
from pathlib import Path
from typing import TypedDict
from urllib.parse import parse_qs, urlparse

import requests
from django.conf import settings

from cl.lib.command_utils import VerboseCommand, logger


class OptionsType(TypedDict):
    type: str
    cursor: str


def get_data(url, params=None):
    header = {}
    logger.info(f"Processing endpoint: {url}")
    try:
        request = requests.get(url, headers=header, params=params, timeout=10)

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
    type = options["type"]
    cursor = options["cursor"]
    allowed_types = ["jurisdictions", "courts", "reporters"]
    base_url = "https://api.case.law"
    version = "v1"
    params = {}
    endpoint = None
    page_size = 1000

    # TODO allow to pass last_updated to cases so we can get only updated cases
    # TODO test how many cases can we collect, there's api calls limit for registered user?
    # TODO store each element from response in separate files? or store per page?

    if not type:
        logger.error("You didn't provide the type. Exiting.")
        return

    if type not in allowed_types:
        logger.error("You didn't provide the type. Exiting.")
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
        params["ordering"] = "court"

    directory = Path(settings.MEDIA_ROOT, "case.law", type)

    if cursor:
        params["cursor"] = cursor

    i = 1

    while endpoint:
        # We only need to pass the params on first request
        data = get_data(endpoint, params=params)
        current_cursor = None

        if data:
            results_count = data.get("count", None)
            old_endpoint = endpoint
            endpoint = data.get("next", None)
            if endpoint:
                url_params = parse_qs(urlparse(old_endpoint).query)
                if "cursor" in url_params:
                    # Get cursor from url
                    current_cursor = url_params.get("cursor")

            if current_cursor:
                current_cursor = current_cursor[0]
                file_path = Path(directory, f"{i}.{current_cursor}.json")
            else:
                file_path = Path(directory, f"{i}.json")

            if os.path.exists(file_path):
                logger.info("Already captured: %s", old_endpoint)
                i = i + 1
                continue

            Path(directory).mkdir(parents=True, exist_ok=True)

            with open(file_path, "w") as outfile:
                json.dump(data, outfile, indent=2)
                i = i + 1

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

    def handle(self, *args, **options):
        get_from_caselaw(options)
