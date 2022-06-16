import os
import time

from celery import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import (
    get_docket_by_pacer_case_id,
    get_pacer_case_id_and_title,
    make_fjc_idb_lookup_params,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.constants import PATENT, PATENT_ANDA
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import Docket
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)
PATENT_TAGS = ["wdtx_ded_patent"]


def get_dockets(options: dict) -> None:
    """Get Patent litigation from the past 10 years.

    :param options: Options for scraping
    :return: None
    """

    start = options["skip_until"]
    stop = options["limit"]
    # Add code to simplify the logic for iterating.
    if stop:
        if start:
            stop = start + stop
        else:
            stop = 1 + stop

    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()

    NOS_CODES = [PATENT, PATENT_ANDA]
    DISTRICTS = ["ded", "txwd"]
    START_DATE = "2012-01-01"
    items = FjcIntegratedDatabase.objects.filter(
        nature_of_suit__in=NOS_CODES,
        date_filed__gt=START_DATE,
        district__in=DISTRICTS,
    ).order_by("date_filed")
    i = 0
    for item in items:
        i += 1
        if start and (i < start):
            # Start processing case at # if not none.
            logger.info(f"Skipping row #{i}")
            continue
        if stop and (i == stop):
            # Stop processing case at # if not none.
            logger.info(f"Stopping at row #{i}")
            break
        # Add timed sleep to avoid banning in Western Texas
        time.sleep(1)
        logger.info(f"{i}: Doing FJC_ID with pk: {item.id}")

        dockets = Docket.objects.filter(idb_data=item)
        docket_in_system = dockets.exists()
        throttle.maybe_wait()
        if not docket_in_system:
            params = make_fjc_idb_lookup_params(item)
            chain(
                get_pacer_case_id_and_title.s(
                    pass_through=None,
                    docket_number=item.docket_number,
                    court_id=item.district_id,
                    cookies=session.cookies,
                    **params,
                ).set(queue=q),
                get_docket_by_pacer_case_id.s(
                    court_id=item.district_id,
                    cookies=session.cookies,
                    tag_names=PATENT_TAGS,
                    **{
                        "show_parties_and_counsel": True,
                        "show_terminated_parties": True,
                        "show_list_of_member_cases": False,
                        "doc_num_end": "",  # No end doc num
                    },
                ).set(queue=q),
                add_or_update_recap_docket.s().set(queue=q),
            ).apply_async()
        else:
            d = dockets[0]
            logger.info(f"{i} Doing docket with pk: {d.pk}")
            chain(
                get_docket_by_pacer_case_id.s(
                    data={"pacer_case_id": d.pacer_case_id},
                    court_id=d.court_id,
                    cookies=session.cookies,
                    docket_pk=d.pk,
                    tag_names=PATENT_TAGS,
                    **{
                        "show_parties_and_counsel": True,
                        "show_terminated_parties": True,
                        "show_list_of_member_cases": False,
                    },
                ).set(queue=q),
                add_or_update_recap_docket.s().set(queue=q),
            ).apply_async()


class Command(VerboseCommand):
    help = """Get all patent dockets since 2012 in TXWD and DED"""

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
            help="Skip until this many items are processed",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop when you reach this row number. Default is to do "
            "all of them.",
        )

    def handle(self, *args, **options):
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        if PACER_USERNAME == "mlissner.flp":
            raise "This is for a client. Do not use FLP credentials"
        get_dockets(options)
