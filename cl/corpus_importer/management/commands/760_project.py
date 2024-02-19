import argparse
import csv
import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.task_canvases import get_district_attachment_pages
from cl.corpus_importer.tasks import (
    get_appellate_docket_by_docket_number,
    get_docket_by_pacer_case_id,
    get_pacer_case_id_and_title,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Court, RECAPDocument
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)

TAG = "QAV5K6HU93A67WS6-760"


def get_dockets(options):
    """Download the dockets described in the CSV according to the `tasks`
    option.
    """
    f = options["file"]
    reader = csv.DictReader(f)
    q = options["queue"]
    task = options["task"]
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    for i, row in enumerate(reader):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break
        if row["Too Old"] == "Yes":
            continue
        if row["Appellate/District"].lower() != task:
            # Only do appellate when appellate, and district when district.
            continue

        # All tests pass. Get the docket.
        logger.info("Doing row %s: %s", i, row)
        throttle.maybe_wait()
        if task == "appellate":
            chain(
                get_appellate_docket_by_docket_number.s(
                    docket_number=row["Cleaned case_No"],
                    court_id=row["fjc_court_id"],
                    cookies=session.cookies,
                    tag_names=[TAG],
                    **{
                        "show_docket_entries": True,
                        "show_orig_docket": True,
                        "show_prior_cases": True,
                        "show_associated_cases": True,
                        "show_panel_info": True,
                        "show_party_atty_info": True,
                        "show_caption": True,
                    },
                ).set(queue=q),
                add_or_update_recap_docket.s().set(queue=q),
            ).apply_async()
        elif task == "district":
            chain(
                get_pacer_case_id_and_title.s(
                    pass_through=None,
                    docket_number=row["Cleaned case_No"],
                    court_id=row["fjc_court_id"],
                    cookies=session.cookies,
                    case_name=row["Title"],
                ).set(queue=q),
                get_docket_by_pacer_case_id.s(
                    court_id=row["fjc_court_id"],
                    cookies=session.cookies,
                    tag_names=[TAG],
                    **{
                        "show_parties_and_counsel": True,
                        "show_terminated_parties": True,
                        "show_list_of_member_cases": True,
                    },
                ).set(queue=q),
                add_or_update_recap_docket.s().set(queue=q),
            ).apply_async()


def get_att_pages(options):
    rd_pks = RECAPDocument.objects.filter(
        tags__name=TAG,
        docket_entry__docket__court__jurisdiction__in=[
            Court.FEDERAL_DISTRICT,
            Court.FEDERAL_BANKRUPTCY,
        ],
    ).values_list("pk", flat=True)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    get_district_attachment_pages(
        options=options, rd_pks=rd_pks, tag_names=[TAG], session=session
    )


class Command(VerboseCommand):
    help = "Look up dockets from a spreadsheet for a client and download them."

    allowed_tasks = [
        "appellate",
        "district",
        "district_attachments",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
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
            "--task",
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )
        parser.add_argument(
            "--file",
            type=argparse.FileType("r"),
            help="Where is the CSV that has the information about what to "
            "download?",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        if options["task"] in ["district", "appellate"]:
            if not options["file"]:
                raise argparse.ArgumentError(
                    "The 'file' argument is required for that action."
                )
            get_dockets(options)
        elif options["task"] == "district_attachments":
            get_district_attachment_pages(options)
