import os
from argparse import RawTextHelpFormatter

from celery import chain
from django.conf import settings

from cl.corpus_importer.management.commands.everything_project import (
    NOS_EXCLUSIONS,
)
from cl.corpus_importer.tasks import (
    get_docket_by_pacer_case_id,
    make_docket_by_iquery,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer_session import ProxyPacerSession
from cl.search.models import Docket
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)

NYSD_TAG = "ljNwRSfxpxnCceEoBBIb"
BUCKWALD_TAG = "GhkcARCmMnPeDrXqqKTX"


def add_all_nysd_to_cl(options):
    """Alas, there's only one way to get all the cases about a particular
    judge: Get all the cases in the entire jurisdiction. We do that here using
    the iquery.pl endpoint.

    Once added to the DB we'll ensure they're tagged. In the next step, we'll
    download all the tagged items.
    """
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = ProxyPacerSession(
        username=PACER_USERNAME, password=PACER_PASSWORD
    )
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
            session = ProxyPacerSession(
                username=PACER_USERNAME, password=PACER_PASSWORD
            )
            session.login()

        throttle.maybe_wait()
        logger.info("Doing pacer_case_id: %s", pacer_case_id)
        make_docket_by_iquery.apply_async(
            args=("nysd", pacer_case_id, "default", [NYSD_TAG]),
            queue=q,
        )


def get_dockets(options):
    """Get the dockets by the particular judge now that we have run iquery
    for all of the cases in the jurisdiction, and now that we have
    """
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = ProxyPacerSession(
        username=PACER_USERNAME, password=PACER_PASSWORD
    )
    session.login()

    buchwald_id = 450
    ds = (
        Docket.objects.filter(
            court_id="nysd", assigned_to_id=buchwald_id, tags__name=NYSD_TAG
        )
        .exclude(idb_data__nature_of_suit__in=NOS_EXCLUSIONS)
        .exclude(idb_data__isnull=True)
    )
    logger.info("Got %s dockets to download", ds.count())
    for i, d in enumerate(ds):
        if i < options["skip_until"]:
            continue
        if i >= options["limit"] > 0:
            break

        if i % 5000 == 0:
            # Re-authenticate just in case the auto-login mechanism isn't
            # working.
            session = ProxyPacerSession(
                username=PACER_USERNAME, password=PACER_PASSWORD
            )
            session.login()

        throttle.maybe_wait()
        logger.info("%s: Doing docket with pk: %s", i, d.pk)
        chain(
            get_docket_by_pacer_case_id.s(
                data={"pacer_case_id": d.pacer_case_id},
                court_id=d.court_id,
                cookies_data=(session.cookies, session.proxy_address),
                docket_pk=d.pk,
                tag_names=[BUCKWALD_TAG],
                **{
                    "show_parties_and_counsel": True,
                    "show_terminated_parties": True,
                    "show_list_of_member_cases": False,
                },
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = """Get all relevant cases by a Judge Buchwald in SDNY

1. Start with the earliest case in 2013 (13-cv-00001, pacer_case_id 405990)
1. For every case between that and today (1:20-cv-06900, pacer_case_id 543051),
   run the iquery page and parse the docket number.
1. Use merge_idb_into_dockets to link IDB data with data from iquery look ups
1. If the judge matches (Naomi Reice Buchwald, NRB), check the NOS in the FJC
   DB.
1. If the NOS is valid, get and tag the docket.

Checks:
 - Buchwald has been at that court the whole time.
 - The FJC data is up to date.

Limitations:
 - In multi-defendant criminal cases, this may fail (OK b/c this project
   limited to civil)

"""

    def create_parser(self, *args, **kwargs):
        parser = super().create_parser(*args, **kwargs)
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
            help="Stop when you reach this pacer_case_id. Default is to do "
            "all of them.",
        )
        parser.add_argument(
            "--task",
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        if options["task"] == "iquery":
            # Run iquery for all of the cases in the district during the time
            # period.
            add_all_nysd_to_cl(options)
        elif options["task"] == "dockets":
            # Get dockets for all of the relevant cases
            get_dockets(options)
        else:
            print(f"Unknown task: {options['task']}")
