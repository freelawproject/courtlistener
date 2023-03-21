# !/usr/bin/python
# -*- coding: utf-8 -*-

import json
import os
import re
import time
from pathlib import Path
from typing import List, Optional, TypedDict

import internetarchive as ia
import requests
from django.conf import settings
from internetarchive import ArchiveSession
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from cl.lib.argparse_types import _argparse_volumes
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.utils import human_sort


class OptionsType(TypedDict):
    reporter: str
    volumes: Optional[range]


def fetch_ia_volumes(
    ia_session: ArchiveSession,
    options: OptionsType,
) -> List[str]:
    """Find and order volumes for a reporter (if found).

    :param ia_session: The IA archive session object
    :param options: The reporter and volume dictionary from argparse
    :return: List of volumes to download from IA
    """

    reporter = options["reporter"]
    volumes = options["volumes"]

    if volumes and len(volumes) == 1:
        reporter_key = f"law.free.cap.{reporter}.{volumes[0]}"
    else:
        reporter_key = f"law.free.cap.{reporter}"

    query = ia_session.search_items(reporter_key)

    # Remove partial matches
    filtered_query = [
        row for row in query if f".{reporter}." in row["identifier"]
    ]
    results = human_sort(filtered_query, "identifier")

    if not volumes:
        return results

    # Return only the volumes requested, if specified
    vol_pattern = "|".join(
        f"(.*{reporter}.{volume}(_\d+)?$)" for volume in volumes
    )
    results = [
        res for res in results if re.match(vol_pattern, res["identifier"])  # type: ignore
    ]
    return results


def download_file(ia_key: str, file_name) -> None:
    """Check if we have file, and download new files

    :param ia_key: The IA key
    :param file_name: The file name
    :return: None
    """
    url = f"https://archive.org/download/{ia_key}/{file_name}"
    if "_" in ia_key:
        ia_key = ia_key.split("_")[0]

    directory = Path(settings.MEDIA_ROOT, "harvard_corpus", ia_key)
    file_path = Path(directory, file_name)

    if os.path.exists(file_path):
        logger.info("Already captured: %s", url)
        return

    logger.info("Capturing: %s", url)
    Path(directory).mkdir(parents=True, exist_ok=True)
    # Create session to retry timeouts with backoff events
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
    data = session.get(url, timeout=15).json()
    with open(file_path, "w") as outfile:
        json.dump(data, outfile, indent=2)


def create_ia_session() -> ArchiveSession:
    """Generate IA Session object

    :return: IA session object
    """
    logger.info("Creating IA session...")
    access_key = settings.IA_ACCESS_KEY
    secret_key = settings.IA_SECRET_KEY
    return ia.get_session({"s3": {"access": access_key, "secret": secret_key}})


def get_from_ia(options: OptionsType) -> None:
    """Find and download files from IA

    Download cases from internet archive via case law and write them to
    disk.

    :param options: Pass the reporter and volume parameters from command line
    :return: None
    """
    ia_session = create_ia_session()
    volumes_ids_for_reporter = fetch_ia_volumes(ia_session, options)
    if not volumes_ids_for_reporter:
        logger.info("No volumes found.")
        return

    for ia_volume in volumes_ids_for_reporter:
        ia_key = ia_volume["identifier"]
        ia_items = ia_session.get_item(ia_key)

        # Fetch items from archive - glob pattern excludes metadata
        # and the curious double-json files.
        files = ia_items.get_files(glob_pattern="[0-9]*")
        # Convert to dict to use human sort
        files = [file.__dict__ for file in files]
        files = human_sort(files, "name")

        for file in files:
            download_file(ia_key, file["name"])


class Command(VerboseCommand):
    help = "Download and save Harvard corpus on IA to disk."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reporter",
            help="Reporter abbreviation as saved on IA.",
            required=True,
        )
        parser.add_argument(
            "--volumes",
            required=False,
            type=_argparse_volumes,
            help="Ex. '2:10' will fetch volumes 2 to 10 inclusive;"
            "'1:' will start at 1 and to 2000; '5' will do volume 5",
        )

    def handle(self, *args, **options):
        get_from_ia(options)
