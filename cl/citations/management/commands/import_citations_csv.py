"""
Import citations from csv file

The csv file must have the following structure:
"cluster_id","citation"
2155423, "2003 WL 22508842"

How to run the command:
manage.py import_citations_csv --csv /opt/courtlistener/cl/assets/media/wl_citations_1.csv

"""

from typing import Optional

import numpy as np
import pandas as pd
from django.core.management import BaseCommand
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.corpus_importer.utils import add_citations_to_cluster
from cl.lib.command_utils import logger
from cl.search.models import OpinionCluster


def load_citations_file(csv_path: str) -> DataFrame | TextFileReader:
    """Load csv file from absolute path

    :param csv_path: csv path
    :return: loaded data
    """

    data = pd.read_csv(csv_path, delimiter=",")
    # Replace nan in dataframe
    data = data.replace(np.nan, "", regex=True)
    logger.info(f"Found {len(data.index)} rows in csv file: {csv_path}")
    return data


def process_csv_data(
    data: DataFrame | TextFileReader,
    limit: int,
    start_row: Optional[int] = None,
    end_row: Optional[int] = None,
) -> None:
    """Process citations from csv file

    :param data: rows from csv file
    :param limit: limit number of rows to process
    :param start_row: start row
    :param end_row: end row
    :return: None
    """
    start = False if start_row else True
    end = False
    total_processed = 0

    for index, row in data.iterrows():
        if not start and start_row == index:
            start = True
        if not start:
            continue

        if end_row is not None and (end_row == index):
            end = True

        cluster_id = int(row.get("cluster_id"))
        citation_to_add = row.get("citation")

        if not OpinionCluster.objects.filter(id=cluster_id).exists():
            logger.info(
                f"Row: {index} - Opinion cluster doesn't exist: {cluster_id}"
            )
            continue

        if cluster_id and citation_to_add:
            add_citations_to_cluster([citation_to_add], cluster_id)

        total_processed += 1
        if limit and total_processed >= limit:
            logger.info(f"Finished {limit} rows")
            return

        if end:
            return


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
            help="Start row (inclusive)." "file.",
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

    def handle(self, *args, **options):
        if options["csv"]:
            if (
                options["start_row"] is not None
                and options["end_row"] is not None
            ):
                if options["start_row"] > options["end_row"]:
                    print("--start-row can't be greater than --end-row")
                    return

            data = load_citations_file(options["csv"])
            if not data.empty:
                process_csv_data(
                    data,
                    options["limit"],
                    options["start_row"],
                    options["end_row"],
                )
            else:
                print("CSV file empty")
