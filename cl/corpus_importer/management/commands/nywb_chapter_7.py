import argparse
import csv
import os

from celery.canvas import chain
from juriscraper.pacer import PacerSession

from cl.corpus_importer.bulk_utils import (
    get_petitions,
    make_bankr_docket_number,
)
from cl.corpus_importer.tasks import (
    get_docket_by_pacer_case_id,
    get_pacer_case_id_and_title,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get("PACER_USERNAME", "UNKNOWN!")
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", "UNKNOWN!")

TAG = "nywb-bankr-ch7-round-2"
TAG_PETITIONS = 'nywb-bankr-ch7-petitions-round-2"'


def get_dockets(options):
    """Download the dockets described in the CSV"""
    f = options["file"]
    reader = csv.DictReader(f)
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    pacer_session = PacerSession(
        username=PACER_USERNAME, password=PACER_PASSWORD
    )
    pacer_session.login()
    for i, row in enumerate(reader):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break

        if i % 1000 == 0:
            pacer_session = PacerSession(
                username=PACER_USERNAME, password=PACER_PASSWORD
            )
            pacer_session.login()
            logger.info(f"Sent {i} tasks to celery so far.")
        logger.info("Doing row %s", i)
        throttle.maybe_wait()
        chain(
            get_pacer_case_id_and_title.s(
                pass_through=None,
                docket_number=make_bankr_docket_number(
                    row["DOCKET"], row["OFFICE"]
                ),
                court_id="nywb",
                cookies=pacer_session.cookies,
                office_number=row["OFFICE"],
                docket_number_letters="bk",
            ).set(queue=q),
            get_docket_by_pacer_case_id.s(
                court_id="nywb",
                cookies=pacer_session.cookies,
                tag_names=[TAG],
                **{
                    "doc_num_start": 1,
                    "doc_num_end": 1,
                    "show_parties_and_counsel": False,
                    "show_terminated_parties": False,
                    "show_list_of_member_cases": False,
                },
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = "Purchase dockets and bankruptcy filings from PACER"

    allowed_tasks = [
        "get_dockets",
        "get_petitions",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch0",
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
            "--file",
            type=argparse.FileType("r"),
            help="Where is the CSV that has the information about what to "
            "download?",
        )
        parser.add_argument(
            "--task",
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        if options["task"] == "get_dockets":
            get_dockets(options)
        elif options["task"] == "get_petitions":
            get_petitions(
                options, PACER_USERNAME, PACER_PASSWORD, TAG, TAG_PETITIONS
            )
