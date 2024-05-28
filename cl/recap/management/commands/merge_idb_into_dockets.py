import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.lib.string_utils import CaseNameTweaker

from cl.corpus_importer.tasks import (
    get_pacer_case_id_and_title,
    make_fjc_idb_lookup_params,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import CommandUtils, VerboseCommand, logger
from cl.lib.pacer_session import ProxyPacerSession
from cl.lib.utils import chunks
from cl.recap.constants import CV_2017, CV_2020, CV_2021
from cl.recap.models import FjcIntegratedDatabase
from cl.recap.tasks import (
    create_or_merge_from_idb_chunk,
    update_docket_from_hidden_api,
)
from cl.search.models import Docket

cnt = CaseNameTweaker()

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)


class Command(VerboseCommand, CommandUtils):
    help = (
        "Iterate over the IDB data and merge it into our existing "
        "datasets. Where we lack a Docket object for an item in the IDB, "
        "create one."
    )

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
            "--court-id",
            type=str,
            required=False,
            default="",
            help="Provide a CL court ID to focus this on a particular "
            "jurisdiction",
        )

    def handle(self, *args, **options):
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        if options["task"] == "merge_and_create":
            self.join_fjc_with_dockets(options)
        elif options["task"] == "update_case_ids":
            self.update_any_missing_pacer_case_ids(options)

    @staticmethod
    def join_fjc_with_dockets(options):
        idb_rows = (
            FjcIntegratedDatabase.objects.filter(
                dataset_source__in=[CV_2017, CV_2020, CV_2021],
            )
            .values_list("pk", flat=True)
            .order_by("pk")
        )
        if options["court_id"]:
            idb_rows = idb_rows.filter(district_id=options["court_id"])

        logger.info("%s items will be merged or created.", idb_rows.count())
        q = options["queue"]
        throttle = CeleryThrottle(queue_name=q)
        chunk_size = 25
        for i, idb_chunk in enumerate(chunks(idb_rows.iterator(), chunk_size)):
            # Iterate over all items in the IDB and find them in the Docket
            # table. If they're not there, create a new item.
            # Consume the chunk so the iterator works properly
            idb_chunk = list(idb_chunk)
            if i < options["offset"]:
                continue
            if i >= options["limit"] > 0:
                break
            throttle.maybe_wait()
            msg = "%s: Merging/creating new dockets for IDB chunk of %s items"
            logger.info(msg, i, chunk_size)
            create_or_merge_from_idb_chunk.apply_async(
                args=(idb_chunk,), queue=q
            )

    @staticmethod
    def update_any_missing_pacer_case_ids(options):
        """The network requests were making things far too slow and had to be
        disabled during the first pass. With this method, we update any items
        that are missing their pacer case ID value.
        """
        ds = Docket.objects.filter(idb_data__isnull=False, pacer_case_id=None)
        q = options["queue"]
        throttle = CeleryThrottle(queue_name=q)
        session = ProxyPacerSession(
            username=PACER_USERNAME, password=PACER_PASSWORD
        )
        session.login()
        for i, d in enumerate(ds.iterator()):
            if i < options["offset"]:
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
            logger.info("Getting pacer_case_id for item %s", d)
            params = make_fjc_idb_lookup_params(d.idb_data)
            chain(
                get_pacer_case_id_and_title.s(
                    pass_through=d.pk,
                    docket_number=d.idb_data.docket_number,
                    court_id=d.idb_data.district_id,
                    cookies=session.cookies,
                    **params,
                ).set(queue=q),
                update_docket_from_hidden_api.s().set(queue=q),
            ).apply_async()
