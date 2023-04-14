# !/usr/bin/python
# -*- coding: utf-8 -*-
import csv
import os
from typing import TypedDict

import pandas as pd
from django.conf import settings
from juriscraper.pacer import (
    ListOfCreditors,
    PacerSession,
    PossibleCaseNumberApi,
)

from cl.corpus_importer.bulk_utils import make_bankr_docket_number
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer import map_cl_to_pacer_id

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)


class OptionsType(TypedDict):
    court: str
    offset: int
    limit: int
    file: str


def query_and_save_creditors_data(options: OptionsType) -> None:
    """Queries and parses claims activity for a list of courts and a specified
     date range.

    :param options: The options of the command.
    :return: None, output files are stored in disk.
    """

    f = open(options["file"], "r", encoding="utf-8")
    reader = csv.DictReader(f)
    court_id = options["court"]
    s = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    s.login()
    for i, row in enumerate(reader):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break

        court_id = map_cl_to_pacer_id(court_id)
        logger.info(f"Doing {court_id} and row {i} ...")
        docket_number = make_bankr_docket_number(row["DOCKET"], row["OFFICE"])
        d_number_file_name = docket_number.replace(":", "-")

        # Check if the reports directory already exists
        html_path = os.path.join(
            settings.MEDIA_ROOT, "list_of_creditors", "reports"
        )
        if not os.path.exists(html_path):
            # Create the directory if it doesn't exist
            os.makedirs(html_path)

        html_file = os.path.join(
            settings.MEDIA_ROOT,
            "list_of_creditors",
            "reports",
            f"{court_id}-{d_number_file_name}.html",
        )

        try:
            report = ListOfCreditors(court_id, s)
        except AssertionError:
            # This is not a bankruptcy court.
            logger.warning(f"Court {court_id} is not a bankruptcy court.")
            continue

        # Check if HTML report for this docket_number already exists, if so
        # omit it. Otherwise, query the pacer_case_id and the list of creditors
        # report
        if not os.path.exists(html_file):
            report_hidden_api = PossibleCaseNumberApi(court_id, s)
            report_hidden_api.query(docket_number)
            result = report_hidden_api.data(
                office_number=row["OFFICE"],
                docket_number_letters="bk",
            )
            if not result:
                logger.info(
                    f"Skipping row: {i}, docket: {docket_number}, no "
                    "result from hidden API"
                )
                continue

            pacer_case_id = result.get("pacer_case_id")
            if not pacer_case_id:
                logger.info(
                    f"Skipping row: {i}, docket: {docket_number}, no "
                    "pacer_case_id found."
                )
                continue

            logger.info(f"File {html_file} doesn't exist.")
            logger.info(
                f"Querying report, court_id: {court_id}, pacer_case_id: {pacer_case_id} "
                f"docket_number: {docket_number}"
            )
            report.query(
                pacer_case_id=pacer_case_id,
                docket_number=docket_number,
            )

            # Save report HTML in disk.
            with open(html_file, "w", encoding="utf-8") as file:
                file.write(report.response.text)

        else:
            logger.info(f"File {html_file} already exists court: {court_id}.")

        with open(html_file, "rb") as file:
            text = file.read().decode("utf-8")
            report._parse_text(text)

        pipe_limited_file = os.path.join(
            settings.MEDIA_ROOT,
            "list_of_creditors",
            "reports",
            f"{court_id}-{d_number_file_name}-raw.txt",
        )

        raw_data = report.data
        pipe_limited_data = raw_data["data"]
        # Save report HTML in disk.
        with open(pipe_limited_file, "w", encoding="utf-8") as file:
            file.write(pipe_limited_data)

        make_csv_file(pipe_limited_file, court_id, d_number_file_name)


def make_csv_file(
    pipe_limited_file: str, court_id: str, d_number_file_name: str
) -> None:
    """Generate a CSV based on the data of the txt files.

    :return: None, The function saves a CSV file in disk.
    """

    csv_file = os.path.join(
        settings.MEDIA_ROOT,
        "list_of_creditors",
        "reports",
        f"{court_id}-{d_number_file_name}.csv",
    )
    docket_number = d_number_file_name.replace("-", ":")
    # Read the pipe-delimited text into a pandas DataFrame
    data = pd.read_csv(pipe_limited_file, delimiter="|", header=None)
    data.insert(0, "docket_number", docket_number)
    # Drop the row number column.
    data.drop(0, axis=1, inplace=True)
    # Save the DataFrame as a CSV file
    data.to_csv(csv_file, index=False, header=False)


class Command(VerboseCommand):
    help = "Query List of creditors and store the reports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--court",
            help="The bankruptcy court.",
            required=True,
        )
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
            "--file",
            type=str,
            help="Where is the text file that has the CSV containing the cases "
            "to query?",
            required=True,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        query_and_save_creditors_data(options)
