"""
Import citations from csv file

The csv file must have the following structure, the file should not have a header row:

"2155423", "2003 WL 22508842"
"7903720","520 A.2d 234"
"7903715","520 A.2d 233"

How to run the command:
manage.py import_citations_csv --csv /opt/courtlistener/cl/assets/media/wl_citations_1.csv

# Add all citations from the file and reindex existing ones
manage.py import_citations_csv --csv /opt/courtlistener/cl/assets/media/wl_citations_1.csv --reindex

# Add and index all citations from the file starting from row 2600000 and reindex existing ones
manage.py import_citations_csv --csv /opt/courtlistener/cl/assets/media/x.csv --start-row 2600000 --delay 0.1

Note: If --limit is greater than --end-row, end row will be ignored

"""

import argparse
import os.path
import time

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

    end_row = None

    dtype_mapping = {"cluster_id": "int", "citation_to_add": "str"}

    if options["end_row"] or options["limit"]:
        end_row = (
            options["limit"]
            if options["limit"] > options["end_row"]
            else options["end_row"]
        )

    data = pd.read_csv(
        options["csv"],
        names=["cluster_id", "citation_to_add"],
        dtype=dtype_mapping,
        delimiter=",",
        skiprows=options["start_row"] - 1 if options["start_row"] else None,
        nrows=end_row,
        na_filter=False,
    )

    logger.info(f"Found {len(data.index)} rows in csv file: {options['csv']}")
    return data


def process_csv_data(
    data: DataFrame | TextFileReader, delay_s: float, reindex: bool
) -> None:
    """Process citations from csv file

    :param data: rows from csv file
    :param delay_s: how long to wait to add each citation
    :param reindex: force reindex of citations
    :return: None
    """

    for index, row in data.iterrows():
        cluster_id = row.get("cluster_id")
        citation_to_add = row.get("citation_to_add")

        if not OpinionCluster.objects.filter(id=cluster_id).exists():
            logger.info(f"Opinion cluster doesn't exist: {cluster_id}")
            continue

        if cluster_id and citation_to_add:
            add_citations_to_cluster([citation_to_add], cluster_id, reindex)
            time.sleep(delay_s)


class Command(BaseCommand):
    help = "Add citations to clusters using a csv file"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def existing_path_type(self, path: str):
        """Validate file path exists

        :param path: path to validate
        :return: valid path
        """
        if not os.path.exists(path):
            raise argparse.ArgumentTypeError(
                f"Csv file: {path} doesn't exist."
            )
        return path

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            type=self.existing_path_type,
            help="Absolute path to a CSV file containing the citations to add.",
            required=True,
        )
        parser.add_argument(
            "--start-row",
            default=0,
            type=int,
            help="Start row (inclusive).",
        )
        parser.add_argument(
            "--end-row",
            default=0,
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
            help="How long to wait to add each citation (in seconds, allows floating "
            "numbers).",
        )
        parser.add_argument(
            "--reindex",
            action="store_true",
            default=False,
            help="Reindex citations if they are already in the system",
        )

    def handle(self, *args, **options):
        if options["end_row"] and options["start_row"] > options["end_row"]:
            logger.info("--start-row can't be greater than --end-row")
            return

        data = load_citations_file(options)

        if data.empty:
            logger.info("CSV file is empty or start/end row returned no rows.")
            return

        process_csv_data(data, options["delay"], options["reindex"])
