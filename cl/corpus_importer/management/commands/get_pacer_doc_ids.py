import os
from typing import Any

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings

from cl.corpus_importer.tasks import get_pacer_doc_id_with_show_case_doc_url
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer_session import log_into_pacer
from cl.search.models import Court, RECAPDocument

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)


async def get_pacer_doc_ids(options: dict[str, Any]) -> None:
    """Get pacer_doc_ids for any item that needs them."""
    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    row_pks = (
        RECAPDocument.objects.filter(pacer_doc_id=None)
        .exclude(document_number=None)
        .exclude(docket_entry__docket__pacer_case_id=None)
        .exclude(
            docket_entry__docket__court__jurisdiction__in=Court.BANKRUPTCY_JURISDICTIONS,
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if options["start_pk"] > 0:
        row_pks = row_pks.filter(pk__gte=options["start_pk"])
    if options["count"] > 0:
        row_pks = row_pks[: options["count"]]

    completed = 0
    session = None
    async for row_pk in row_pks.aiterator():
        await sync_to_async(throttle.maybe_wait)()
        if session is None or completed % 1000 == 0:
            session = await log_into_pacer(
                username=PACER_USERNAME, password=PACER_PASSWORD
            )
            logger.info(
                f"Sent {completed} tasks to celery so far. Latest pk: {row_pk}"
            )
        await sync_to_async(
            get_pacer_doc_id_with_show_case_doc_url.apply_async
        )(args=(row_pk, session), queue=q)
        completed += 1


class Command(VerboseCommand):
    help = "Get pacer_doc_id values for any item that's missing them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=0,
            help="The number of items to do. Default is to do all of them.",
        )
        parser.add_argument(
            "--start-pk",
            type=int,
            default=0,
            help="Skip any primary keys lower than this value. (Useful for "
            "restarts.)",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        async_to_sync(get_pacer_doc_ids)(options)
