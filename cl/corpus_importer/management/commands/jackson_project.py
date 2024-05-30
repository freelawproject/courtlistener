import os

from celery import chain
from django.conf import settings

from cl.corpus_importer.tasks import get_docket_by_pacer_case_id
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer_session import ProxyPacerSession
from cl.search.models import Docket
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)

JACKSON_TAG = "ketanji-jackson-2022-02-28"


def get_dockets(options):
    """Get the dockets by the particular judge."""
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = ProxyPacerSession(
        username=PACER_USERNAME, password=PACER_PASSWORD
    )
    session.login()

    jackson_id = 1609
    ds = Docket.objects.filter(court_id="dcd", assigned_to_id=jackson_id)

    logger.info("Got %s dockets to download", ds.count())
    for i, d in enumerate(ds):
        if i < options["skip_until"]:
            continue
        if i >= options["limit"] > 0:
            break

        throttle.maybe_wait()
        logger.info("%s: Doing docket with pk: %s", i, d.pk)
        chain(
            get_docket_by_pacer_case_id.s(
                data={"pacer_case_id": d.pacer_case_id},
                court_id=d.court_id,
                cookies=session.cookies,
                docket_pk=d.pk,
                tag_names=[JACKSON_TAG],
                **{
                    "show_parties_and_counsel": True,
                    "show_terminated_parties": True,
                    "show_list_of_member_cases": False,
                },
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = """Get all relevant cases by a Judge Ketanji Jackson"""

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

    def handle(self, *args, **options):
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        # Get dockets for all of the relevant cases
        get_dockets(options)
