import argparse
import json
import logging
import os
from glob import glob
from typing import IO, Union

from dateutil import parser
from django.utils.encoding import force_bytes

from cl.lib.command_utils import VerboseCommand
from cl.people_db.import_judges.ca_judges_import_helpers import (
    find_court,
    find_or_create_judge,
    get_appointer,
    get_how_selected,
    get_position_type,
    get_termination_reason,
    load_json_file,
)
from cl.people_db.import_judges.ca_judges_position_helpers import (
    convert_date_to_gran_format,
    process_positions,
    string_to_date,
)
from cl.people_db.models import GRANULARITY_DAY, Person, Position
from cl.search.models import Court


def import_ca_judges(
    log: bool,
    file: IO,
) -> None:
    """Import CA Judges

    :param log: Should we view logging info
    :param file: Location of our overriding data json file
    :return: None
    """

    if log:
        logging.getLogger().setLevel(logging.INFO)

    logging.info("Starting import")

    logging.info("Loading json of CA County abbreviations")
    counties = load_json_file("ca_counties.json")

    # shape of returned json
    # { count: string, judges: JudgeJson[] }
    all_judges_json = load_json_file("ca_judges.json")

    count = all_judges_json["count"]
    logging.info(f"Processing {count} unique judges")

    # shape of judgeJson
    # { fullName: string, positions: Position[] }
    judge_info = all_judges_json["judges"]

    for i, info in enumerate(judge_info):
        fullname = info["fullName"]
        positions = info["positions"]

        logging.info(f"\nProcessing {fullname}\n--------------------")

        judge = find_or_create_judge(info, counties, i)

        processed = process_positions(positions, counties)

        for pos in processed:
            # remove uneeded fields
            del pos["pending_status"]
            del pos["inactive_status"]

            if pos["court"]:
                del pos["organization_name"]

            if pos["position_type"]:
                del pos["job_title"]

            # convert date start to proper format
            if pos["date_start"]:
                pos["date_start"] = convert_date_to_gran_format(
                    pos["date_start"]
                )
                pos["date_granularity_start"] = GRANULARITY_DAY
                logging.info("date start is %s", pos["date_start"])

            if pos["date_termination"]:
                pos["date_termination"] = convert_date_to_gran_format(
                    pos["date_termination"]
                )
                pos["date_granularity_termination"] = GRANULARITY_DAY
            else:
                # if the date is empty, delete the key from the po
                del pos["date_termination"]
                del pos["termination_reason"]

            Position.objects.create(**pos, person=judge)


class Command(VerboseCommand):
    help = "Import CA judge data received from CA State Court Dump."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input-file",
            type=argparse.FileType("r"),
            help="The filepath to our preprocessed data file.",
            required=True,
        )
        parser.add_argument(
            "--log",
            action="store_true",
            default=False,
            help="Choose to view info log lines.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        import_ca_judges(
            options["log"],
            options["input_file"],
        )
