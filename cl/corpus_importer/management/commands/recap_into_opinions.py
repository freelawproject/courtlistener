from typing import Optional

from asgiref.sync import async_to_sync
from django.core.management import BaseCommand
from django.db.models import Q
from eyecite.tokenizers import HyperscanTokenizer
from httpx import (
    HTTPStatusError,
    NetworkError,
    RemoteProtocolError,
    Response,
    TimeoutException,
)

from cl.corpus_importer.tasks import ingest_recap_document
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import logger
from cl.lib.decorators import retry
from cl.lib.microservice_utils import microservice
from cl.search.models import SOURCES, Court, OpinionCluster, RECAPDocument

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


@retry(
    ExceptionToCheck=(
        NetworkError,
        TimeoutException,
        RemoteProtocolError,
        HTTPStatusError,
    ),
    tries=3,
    delay=5,
    backoff=2,
    logger=logger,
)
def extract_recap_document(rd: RECAPDocument) -> Response:
    """Call recap-extract from doctor with retries

    :param rd: the recap document to extract
    :return: Response object
    """
    response = async_to_sync(microservice)(
        service="recap-extract",
        item=rd,
        params={"strip_margin": True},
    )
    response.raise_for_status()
    return response


def import_opinions_from_recap(
    court_str: Optional[str] = None,
    skip_until: Optional[str] = None,
    total_count: int = 0,
    queue: str = "batch1",
) -> None:
    """Import recap documents into opinion db

    :param court: Court ID if any
    :param skip_until: Court ID to re-start at
    :param total_count: The number of new opinions to add
    :param queue: The queue to use for celery
    :return: None
    """
    if not court_str:
        filter_conditions = Q(jurisdiction=Court.FEDERAL_DISTRICT) & ~Q(
            id__in=["orld", "dcd"]
        )
        if skip_until:
            filter_conditions &= Q(id__gte=skip_until)
    else:
        filter_conditions = Q(pk=court_str)
    courts = Court.objects.filter(filter_conditions).order_by("id")

    count = 0
    for court in courts:
        logger.info(f"Importing RECAP documents for {court}")

        # Manually select the replica db which has an addt'l index added to
        # improve this query.
        latest_date_filed = (
            OpinionCluster.objects.using("replica")
            .filter(docket__court=court)
            .exclude(source=SOURCES.RECAP)
            .order_by("-date_filed")
            .values_list("date_filed", flat=True)
            .first()
        )
        if latest_date_filed == None:
            logger.error(
                msg=f"Court {court.id} has no opinion clusters for recap import"
            )
            continue

        recap_document_ids = (
            RECAPDocument.objects.filter(
                docket_entry__docket__court=court,
                docket_entry__date_filed__gt=latest_date_filed,
                is_available=True,
                is_free_on_pacer=True,
            )
            .only("id")
            .order_by("id")
        )

        throttle = CeleryThrottle(queue_name=queue)
        for recap_document_id in recap_document_ids.iterator():
            count += 1
            logger.info(
                f"{count}: Importing rd {recap_document_id.id} in {court.id}"
            )
            throttle.maybe_wait()
            ingest_recap_document.apply_async(
                args=[recap_document_id], queue=queue
            )
            if total_count > 0 and count >= total_count:
                logger.info(
                    f"RECAP import completed for {total_count} documents"
                )
                return


class Command(BaseCommand):
    help = "Import recap documents into opinions"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--court",
            help="Specific court ID to import - skip if want to ingest everything",
            type=str,
            required=False,
        )
        parser.add_argument(
            "--skip-until",
            help="Specific court ID to restart import with",
            type=str,
            required=False,
        )
        parser.add_argument(
            "--total",
            type=int,
            help="Number of files to import - set to 0 to import endlessly",
            default=10,
            required=False,
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed",
        )

    def handle(self, *args, **options):
        court = options.get("court")
        skip_until = options.get("skip_until")
        total_count = options.get("total")
        queue = options.get("queue")
        import_opinions_from_recap(court, skip_until, total_count, queue)
