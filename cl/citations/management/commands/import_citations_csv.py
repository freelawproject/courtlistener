"""
Import citations from csv file

The csv file must have the following structure, the file should not have a header row:

"2155423", "2003 WL 22508842"
"7903720","520 A.2d 234"
"7903715","520 A.2d 233"

How to run the command:
manage.py import_citations_csv --csv /opt/courtlistener/cl/assets/media/wl_citations_1.csv

Note: If --limit is greater than --end-row, end row will be ignored

"""

import os.path
import time

import numpy as np
import pandas as pd
from django.core.management import BaseCommand
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.corpus_importer.utils import add_citations_to_cluster
from cl.lib.command_utils import logger
from cl.search.models import OpinionCluster


def load_citations_file(options: dict) -> DataFrame | TextFileReader:
    """Load csv file from absolute path

    :param options: options passed to command
    :return: loaded data
    """

    start_row = None
    end_row = None

    if options["start_row"] and options["end_row"]:
        start_row = options["start_row"] - 1 if options["start_row"] > 1 else 0
        end_row = options["end_row"] - options["start_row"] + 1  # inclusive

    if options["start_row"] and not options["end_row"]:
        start_row = options["start_row"] - 1 if options["start_row"] > 1 else 0

    if options["end_row"] and not options["start_row"]:
        end_row = options["end_row"]

    if options["limit"]:
        end_row = options["limit"]

    data = pd.read_csv(
        options["csv"],
        names=["cluster_id", "citation_to_add"],
        delimiter=",",
        skiprows=start_row,
        nrows=end_row,
    )

    # Replace nan in dataframe
    data = data.replace(np.nan, "", regex=True)
    logger.info(f"Found {len(data.index)} rows in csv file: {options['csv']}")
    return data


def process_csv_data(data: DataFrame | TextFileReader, options: dict) -> None:
    """Process citations from csv file

    :param data: rows from csv file
    :param options: options passed to command
    :return: None
    """

    for index, row in data.iterrows():
        cluster_id = int(row.get("cluster_id"))
        citation_to_add = row.get("citation_to_add")

        if not OpinionCluster.objects.filter(id=cluster_id).exists():
            logger.info(
                f"Row: {index} - Opinion cluster doesn't exist: {cluster_id}"
            )
            continue

        if cluster_id and citation_to_add:
            add_citations_to_cluster([citation_to_add], cluster_id)
            time.sleep(options["delay"])


class Command(BaseCommand):
    help = "Add citations to clusters using a csv file"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            help="Absolute path to a CSV file containing the citations to add.",
            required=True,
        )
        parser.add_argument(
            "--start-row",
            type=int,
            help="Start row (inclusive).",
        )
        parser.add_argument(
            "--end-row",
            type=int,
            help="End row (inclusive).",
        )
        parser.add_argument(
            "--limit",
            default=0,
            type=int,
            help="Limit number of rows to process.",
            required=False,
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="How long to wait to add each citation (in seconds, allows floating numbers).",
        )

    def handle(self, *args, **options):
        if options["start_row"] and options["end_row"]:
            if options["start_row"] > options["end_row"]:
                logger.info("--start-row can't be greater than --end-row")
                return

        if not os.path.exists(options["csv"]):
            logger.info(f"Csv file: {options['csv']} doesn't exist.")
            return

        data = load_citations_file(options)
        if not data.empty:
            process_csv_data(data, options)
        else:
            logger.info("CSV file is empty or start/end row returned no rows.")
