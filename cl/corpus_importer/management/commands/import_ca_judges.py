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
from cl.people_db.models import Person
from cl.search.models import Court, Position


def build_position_from_json(json, counties):
    """Convert positionJson into a Position model object to save

    :param json: {
        id,
        salutation,
        jobTitle,
        title,
        fullName,
        lastFirstMiddleName,
        firstName,
        lastName,
        judicialIndicator,
        orgType,
        orgName,
        orgDivision,
        experienceStatus,
        experienceStatusReason,
        experienceStatusEffectiveDate,
        expId,
        barAdmissionDate,
        deceasedDate,
        judicialPositionId,
        judicialPositionJobClass,
        judicialPositionJobTitle,
        judicialPositionOrgType,
        judicialPositionOrgName,
        judicialPositionLocationName,
        judicialExperienceDivsionName,
        judicialPositionOrgCounty,
        judicialPositionActiveDate,
        judicialPositionInactiveDate,
        judicialExperiencePendingStatus,
        judicialExperiencePendingSubType,
        JudicialExperienceInactiveStatus,
        judicialExperienceAppointmentDate,
        judicialExperienceActiveDate,
        judicialExperienceInactiveDate,
        judicialExperienceTermEndDate
    }
    :param counties: CountyJson
    :return {
        court: ForeignKey,
        job_title: CharField,
        organization_name: CharField,
        date_start: DateField,
        position_type: POSITION_TYPES enum,
        how_selected: CharField,
        appointer: ForeignKey,
        date_termination: DateField,
        termination_reason: CharField
    }
    """

    court = find_court(json, counties)

    position_type = get_position_type(json["judicialPositionJobTitle"])
    how_selected = get_how_selected(json["judicialExperiencePendingStatus"])

    appointer = None
    if how_selected == Position.APPOINTMENT_GOVERNOR:
        appointer = get_appointer(json["judicialExperiencePendingSubType"])

    termination_reason = get_termination_reason(
        json["judicialExperienceInactiveStatus"]
    )

    position = {
        "court": court,
        "appointer": appointer,
        "how_selected": how_selected,
        "position_type": position_type,
        "job_title": json["judicialPositionJobTitle"],
        "organization_name": json["orgName"],
        "date_start": json["judicialExperienceActiveDate"],
        "date_termination": json["judicialExperienceInactiveDate"],
        termination_reason: termination_reason,
    }
    logging.info(f"Built Position object {position}")
    return position


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

    # TODO: Create Person Pre-Processing
    # Check that date periods don't overlap
    # Handle election as Presiding Judge
    # the spreadsheet lists the Presiding Position as concurrent
    # rather than sequential

    for info in judge_info:
        fullname = info["fullName"]
        positions = info["positions"]

        logging.info(f"\nProcessing {fullname}\n--------------------")

        judge = find_or_create_judge(info, counties)

        for i, position in enumerate(positions):

            logging.info(f"----------------------\nProcessing Position #{i}")

            item = build_position_from_json(position)

            new_position = Position(item)


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
