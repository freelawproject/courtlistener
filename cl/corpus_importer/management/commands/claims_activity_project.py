# !/usr/bin/python
# -*- coding: utf-8 -*-

import json
import os
from datetime import date

import pandas as pd
from django.conf import settings
from django.contrib.auth.models import User
from juriscraper.pacer import ClaimsActivity, PacerSession

from cl.lib.argparse_types import valid_date
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.search.models import Court


def query_and_parse_claims_activity(
    courts: list[str], date_start: date, date_end: date
) -> None:
    """Queries and parses claims activity for a list of courts and a specified
     date range.

    :param courts: List of courts to query the reports.
    :param date_start: Start date for the date range to query.
    :param date_end: End date for the date range to query.
    :return: None, output files are stored in disk.
    """

    if not courts:
        bankr_courts = (
            Court.federal_courts.bankruptcy_pacer_courts().all().only("pk")
        )
        courts = [court.pk for court in bankr_courts]

    creditor_names = {
        "international_flavors": "International Flavors",
        "symrise": "Symrise",
        "givaudan": "Givaudan",
        "firmenich": "Firmenich",
    }

    recap_user = User.objects.get(username="recap")
    cookies = get_or_cache_pacer_cookies(
        recap_user.pk, settings.PACER_USERNAME, settings.PACER_PASSWORD
    )
    s = PacerSession(cookies=cookies)
    for court in courts:
        for alias, creditor_name in creditor_names.items():
            logger.info(f"Doing {court} and creditor {alias}")

            # Check if the creditor directory already exists
            html_path = os.path.join(
                settings.MEDIA_ROOT, "claims_activity", f"{alias}"
            )
            if not os.path.exists(html_path):
                # Create the directory if it doesn't exist
                os.makedirs(html_path)

            html_file = os.path.join(
                settings.MEDIA_ROOT,
                "claims_activity",
                f"{alias}",
                f"{court}-{alias}.html",
            )
            try:
                report = ClaimsActivity(court, s)
            except AssertionError:
                # This is not a bankruptcy court.
                logger.warning(f"Court {court} is not a bankruptcy court.")
                continue

            if not os.path.exists(html_file):
                # If the HTML report for this creditor and court doesn't exist
                # query it from PACER.
                logger.info(f"File {html_file} doesn't exist.")
                logger.info(
                    f"Querying report, court_id: {court}, creditor_name: "
                    f"{creditor_name}, date_start: {date_start}, date_end: "
                    f"{date_end}."
                )

                report.query(
                    pacer_case_id="",
                    docket_number="",
                    creditor_name=creditor_name,
                    date_start=date_start,
                    date_end=date_end,
                )

                # Save report HTML in disk.
                with open(html_file, "w") as file:
                    file.write(report.response.text)

            else:
                logger.info(
                    f"File {html_file} already exists court: {court}, "
                    f"creditor_name: {alias}, skipping report query."
                )

            json_file = os.path.join(
                settings.MEDIA_ROOT,
                "claims_activity",
                f"{alias}",
                f"{court}-{alias}.json",
            )
            if not os.path.exists(json_file):
                # If not json_file for court and creditor, parse it from HTML.
                with open(html_file, "rb") as file:
                    text = file.read().decode("utf-8")
                report._parse_text(text)
                with open(json_file, "w") as file:
                    json.dump(
                        report.data,
                        file,
                        default=serialize_json,
                        indent=2,
                        sort_keys=True,
                    )
            make_csv_if_required(alias, court, json_file)


def serialize_json(obj: date) -> str:
    """Serialize a date object to ISO format string.

    :param obj: A JSON object.
    :return: A string date in ISO format.
    """

    if isinstance(obj, date):
        return obj.isoformat()
    return ""


def make_csv_if_required(alias: str, court_id: str, json_file: str):
    """Generate a CSV file if it does not already exist, based on the data in
    the given JSON file.

    :param alias: The creditor alias.
    :param court_id: The court id.
    :param json_file: The path to the JSON file containing the data to be
    processed.
    :return: None, The function saves a CSV file in disk.
    """

    csv_file = os.path.join(
        settings.MEDIA_ROOT,
        "claims_activity",
        f"{alias}",
        f"{court_id}-{alias}.csv",
    )
    with open(json_file) as f:
        data = json.load(f)

    if not os.path.exists(csv_file) and not data == {} and not data == []:
        logger.info(
            f"Generating {csv_file}, court: {court_id}, alias: {alias}"
        )
        dataframe = pd.DataFrame()
        for row in data:
            # Create rows for claims without attachments.
            if not len(row["claim"]["attachments"]):
                del row["claim"]["attachments"]
                row_df = pd.json_normalize(row)
                empty_att_row = {
                    "att_claim_doc_seq": "",
                    "att_claim_id": "",
                    "att_claim_number": "",
                    "att_short_description": "",
                    "att_pacer_case_id": "",
                }
                empty_att_row_df = pd.json_normalize(empty_att_row)
                dataframe = pd.concat(
                    [dataframe, pd.concat([row_df, empty_att_row_df], axis=1)],
                    ignore_index=True,
                )
                continue

            # Create rows for claims with attachments.
            for i, att_row in enumerate(row["claim"]["attachments"]):
                # Rename attachment fields with att_ prefix.
                att_row_renamed = {f"att_{k}": v for k, v in att_row.items()}
                pd_att = pd.json_normalize(att_row_renamed)
                if i == 0:
                    del row["claim"]["attachments"]
                pd_row = pd.json_normalize(row)
                dataframe = pd.concat(
                    [dataframe, pd.concat([pd_row, pd_att], axis=1)],
                    ignore_index=True,
                )

        # Set columns with a custom order.
        column_order = [
            "court_id",
            "docket_number",
            "case_name",
            "chapter",
            "office",
            "assigned_to_str",
            "trustee_str",
            "last_date_to_file_claims",
            "last_date_to_file_govt",
            "claim.amends_no",
            "claim.amount_allowed",
            "claim.amount_claimed",
            "claim.claim_id",
            "claim.claim_number",
            "claim.creditor_id",
            "claim.creditor_name_address",
            "claim.date_entered",
            "claim.date_filed",
            "claim.description",
            "claim.entered_by",
            "claim.filed_by",
            "claim.pacer_case_id",
            "claim.priority_claimed",
            "claim.remarks",
            "claim.secured_claimed",
            "claim.status",
            "att_claim_doc_seq",
            "att_claim_id",
            "att_claim_number",
            "att_short_description",
            "att_pacer_case_id",
        ]
        dataframe.to_csv(csv_file, columns=column_order, index=False)

    if data == {} or data == []:
        logger.warning(
            f"Report for court: {court_id} and alias: {alias} is "
            f"empty, skipping CSV generation."
        )


class Command(VerboseCommand):
    help = "Query claims activity and parse them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--courts",
            help="A list of bankruptcy courts.",
            nargs="+",
        )

        parser.add_argument(
            "--date_start",
            help="Date start to query the report Y-m-d.",
            type=valid_date,
            default=date(2017, 1, 1),
        )

        parser.add_argument(
            "--date_end",
            help="Date end to query the report Y-m-d.",
            type=valid_date,
            default=date.today(),
        )

    def handle(self, *args, **options):
        date_start = options["date_start"]
        date_end = options["date_end"]
        query_and_parse_claims_activity(
            options["courts"], date_start, date_end
        )
