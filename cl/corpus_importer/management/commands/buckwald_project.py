import os
from argparse import RawTextHelpFormatter

from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.corpus_importer.tasks import make_docket_by_iquery

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)

TAG = "ljNwRSfxpxnCceEoBBIb"


def add_all_nysd_to_cl(options):
    """Alas, there's only one way to get all the cases about a particular
    judge: Get all the cases in the entire jurisdiction. We do that here using
    the iquery.pl endpoint.

    Once added to the DB we'll ensure they're tagged. In the next step, we'll
    download all the tagged items.
    """
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()

    # IDs obtained by binary search of docket numbers on PACER website.
    earliest_id = 405990
    latest_id = 543051
    for pacer_case_id in range(earliest_id, latest_id):
        if pacer_case_id < options["skip_until"]:
            continue
        if pacer_case_id >= options["limit"] > 0:
            break

        if pacer_case_id % 5000 == 0:
            # Re-authenticate just in case the auto-login mechanism isn't
            # working.
            session = PacerSession(
                username=PACER_USERNAME, password=PACER_PASSWORD
            )
            session.login()

        logger.info("Doing pacer_case_id: %s", pacer_case_id)
        throttle.maybe_wait()
        make_docket_by_iquery.delay(
            "nysd", pacer_case_id, session.cookies, [TAG]
        )


class Command(VerboseCommand):
    help = u"""Get all relevant cases by a Judge Buchwald in SDNY

1. Start with the earliest case in 2013 (13-cv-00001, pacer_case_id 405990)
2. For every case between that and today (1:20-cv-06900, pacer_case_id 543051),
   run the iquery page and parse the docket number.
3. If the judge matches (Naomi Reice Buchwald, NRB), check the NOS in the FJC
   DB.
4. If the NOS is valid, get and tag the docket.

Checks:
 - Buchwald has been at that court the whole time.
 - The FJC data is up to date.
 -
"""

    def create_parser(self, *args, **kwargs):
        parser = super(Command, self).create_parser(*args, **kwargs)
        parser.formatter_class = RawTextHelpFormatter
        return parser

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--skip-until",
            type=int,
            default=0,
            help="Skip until you reach the item with this pacer_case_id. "
            "Default is to skip none.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop when you reach this pacer_case_id. Default is to do all "
            "of them.",
        )
        parser.add_argument(
            "--task",
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        if options["task"] == "iquery":
            add_all_nysd_to_cl(options)
        else:
            print("Unknown task: %s" % options["task"])
