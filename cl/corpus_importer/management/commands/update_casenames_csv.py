"""
Update case names from a csv file

The csv must have this two columns: cluster_id and new_casename

For example:
"cluster_id","new_casename"
"774888","1000 Friends of Maryland v. Carol Browner"
"542985","101 Ranch v. United States"
"298695","1507 Corporation v. Henderson"

How to run the command:
manage.py update_casenames_csv --csv /opt/courtlistener/cl/assets/media/casenames_to_update.csv

# Pass a custom delay to wait between object updates
manage.py update_casenames_csv --csv /opt/courtlistener/cl/assets/media/casenames_to_update.csv --delay 0.1

# Start from specified row
manage.py update_casenames_csv --csv /opt/courtlistener/cl/assets/media/casenames_to_update.csv --start-row 2600000

Note: If --limit is greater than --end-row, end row will be ignored

"""

import argparse
import os
import time

import pandas as pd
from django.core.management import BaseCommand
from juriscraper.lib.string_utils import harmonize, titlecase
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.lib.command_utils import logger
from cl.search.models import OpinionCluster


def load_csv_file(options: dict) -> DataFrame | TextFileReader:
    """Load csv file from absolute path

    :param options: options passed to command
    :return: loaded data
    """

    end_row = None

    if options["end_row"] or options["limit"]:
        end_row = (
            options["limit"]
            if options["limit"] > options["end_row"]
            else options["end_row"]
        )

    column_names = None
    header = 0

    if options["start_row"]:
        # Keep header columns because if skiprows is used, it will ignore the header.
        column_names = pd.read_csv(options["csv"], nrows=1).columns
        header = None

    data = pd.read_csv(
        options["csv"],
        delimiter=",",
        skiprows=options["start_row"] - 1 if options["start_row"] else None,
        nrows=end_row,
        na_filter=False,
        header=header,
        names=column_names,
    )

    logger.info(f"Found {len(data.index)} rows in csv file: {options['csv']}")
    return data


def process_csv_data(data: DataFrame | TextFileReader, delay_s: float) -> None:
    """Process case names from csv file

    :param data: rows from csv file
    :param delay_s: how long to wait to update each cluster and docket
    :return: None
    """

    for index, row in data.iterrows():
        cluster_id = row.get("cluster_id")
        new_casename = row.get("new_casename")

        if not OpinionCluster.objects.filter(id=cluster_id).exists():
            logger.info(f"Opinion cluster doesn't exist: {cluster_id}")
            continue

        if cluster_id and new_casename:
            # We add a delay on each save because it will trigger ES indexing for
            # cluster and docket
            logger.info(f"Updating case name for cluster id: {cluster_id}")
            cluster = OpinionCluster.objects.get(id=cluster_id)
            cluster.case_name = titlecase(harmonize(new_casename))
            cluster.save()
            time.sleep(delay_s)

            if cluster.docket:
                logger.info(
                    f"Updating case name for docket id: {cluster.docket_id}"
                )
                cluster.docket.case_name = titlecase(harmonize(new_casename))
                cluster.docket.save()
                time.sleep(delay_s)


class Command(BaseCommand):
    help = "Update case names in clusters and dockets using a csv file"

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
            help="Absolute path to a CSV file containing the case names and "
            "cluster_ids.",
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
            default=0.3,
            help="How long to wait between object updates (in seconds, allows floating "
            "numbers).",
        )

    def handle(self, *args, **options):
        if options["end_row"] and options["start_row"] > options["end_row"]:
            logger.info("--start-row can't be greater than --end-row")
            return

        data = load_csv_file(options)

        if data.empty:
            logger.info("CSV file is empty or start/end row returned no rows.")
            return

        process_csv_data(data, options["delay"])
