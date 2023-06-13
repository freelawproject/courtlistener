# !/usr/bin/python
# -*- coding: utf-8 -*-
import csv
import itertools
import os
import re
from typing import TypedDict, cast

from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.bulk_utils import make_bankr_docket_number
from cl.corpus_importer.tasks import (
    make_list_of_creditors_key,
    query_and_save_list_of_creditors,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.redis_utils import create_redis_semaphore

CLIENT_PACER_USERNAME = os.environ.get("CLIENT_PACER_USERNAME", "")
CLIENT_PACER_PASSWORD = os.environ.get("CLIENT_PACER_PASSWORD", "")


class OptionsType(TypedDict):
    base_path: str
    offset: int
    limit: int
    files: str
    queue: str


def enqueue_get_list_of_creditors(
    court_id: str, d_number_file_name: str
) -> bool:
    """Get list of creditors semaphore"""
    key = make_list_of_creditors_key(court_id, d_number_file_name)
    return create_redis_semaphore("CACHE", key, ttl=60 * 60)


def query_and_save_creditors_data(options: OptionsType) -> None:
    """Queries and parses claims activity for a list of courts and a specified
     date range.

    :param options: The options of the command.
    :return: None, output files are stored in disk.
    """

    if CLIENT_PACER_USERNAME == "" or CLIENT_PACER_PASSWORD == "":
        logger.info(
            "You must set CLIENT_PACER_USERNAME and CLIENT_PACER_PASSWORD "
            "env vars to continue..."
        )
        return None

    q = cast(str, options["queue"])
    regex = re.compile(r"([^/]+).csv")
    base_path = options["base_path"]
    csv_files = []
    for file in options["files"]:
        f = open(f"{base_path}/{file}", "r", encoding="utf-8")
        reader = csv.DictReader(f)
        match = regex.search(file)
        if match:
            court_id = match.group(1)
            court_id = map_cl_to_pacer_id(court_id)
            file_tuple = (court_id, reader)
            csv_files.append(file_tuple)
        else:
            raise ValueError(f"Bad file name {file}")

    session = PacerSession(
        username=CLIENT_PACER_USERNAME, password=CLIENT_PACER_PASSWORD
    )
    session.login()
    throttle = CeleryThrottle(queue_name=q)
    completed = 0
    for i, rows in enumerate(
        itertools.zip_longest(*(t[1] for t in csv_files), fillvalue=None)
    ):
        # Iterate over all the courts files at the same time.
        for j, row in enumerate(rows):
            # Iterate over each court and row court.
            completed += 1
            if completed < options["offset"]:
                continue
            if completed >= options["limit"] > 0:
                break

            court_id = csv_files[j][0]
            if row is None:
                # Some courts have fewer rows than others; if a row in this
                # court is empty, skip it.
                continue

            logger.info(f"Doing {court_id} and row {i} ...")
            docket_number = make_bankr_docket_number(
                row["DOCKET"], row["OFFICE"]
            )
            d_number_file_name = docket_number.replace(":", "-")

            # Check if the reports directory already exists
            html_path = os.path.join(
                settings.MEDIA_ROOT, "list_of_creditors", "reports"
            )
            if not os.path.exists(html_path):
                # Create the directory if it doesn't exist
                os.makedirs(html_path)

            # Check if the court_id directory already exists
            court_id_path = os.path.join(
                settings.MEDIA_ROOT, "list_of_creditors", "reports", court_id
            )
            if not os.path.exists(court_id_path):
                # Create the court_id if it doesn't exist
                os.makedirs(court_id_path)

            html_file = os.path.join(
                settings.MEDIA_ROOT,
                "list_of_creditors",
                "reports",
                court_id,
                f"{court_id}-{d_number_file_name}.html",
            )

            if os.path.exists(html_file):
                logger.info(
                    f"The report {html_file} already exist court: {court_id}"
                )
                continue

            newly_enqueued = enqueue_get_list_of_creditors(
                court_id, d_number_file_name
            )
            if newly_enqueued:
                logger.info(
                    f"Enqueueing case: {docket_number}, court:{court_id}..."
                )
                throttle.maybe_wait()
                query_and_save_list_of_creditors.si(
                    session.cookies,
                    court_id,
                    d_number_file_name,
                    docket_number,
                    html_file,
                    i,
                    row,
                ).set(queue=q).apply_async()
            else:
                logger.info(
                    f"The report {html_file} is currently being processed in "
                    f"another task, court: {court_id}"
                )


class Command(VerboseCommand):
    help = "Query List of creditors and store the reports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
            "skip none.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
            "with the offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            "--base_path",
            type=str,
            help="The base path where to find the CSV files to process.",
            default="/opt/courtlistener/cl/assets/media/list_of_creditors",
        )
        parser.add_argument(
            "--files",
            type=str,
            help="A list of files that has the CSV containing the cases "
            "to query. Use the format court_id.csv",
            nargs="+",
            required=True,
        )
        parser.add_argument(
            "--queue",
            type=str,
            default="celery",
            help="The celery queue where the tasks should be processed.",
            required=True,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        query_and_save_creditors_data(options)
