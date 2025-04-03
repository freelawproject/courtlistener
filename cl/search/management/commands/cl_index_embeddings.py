from celery import chain

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.models import SEARCH_TYPES, Opinion
from cl.search.tasks import index_embeddings, retrieve_embeddings


def compose_redis_key() -> str:
    """Compose a Redis key based on the search type for embedding indexing log.
    :return: A Redis key as a string.
    """
    return f"{SEARCH_TYPES.OPINION}_embedding_indexing:log"


class Command(VerboseCommand):
    help = "Retrieve opinion embeddings from S3 and index them into ES."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.throttle = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            help="How many embeddings to index per batch.",
            required=True,
        )
        parser.add_argument(
            "--start-id",
            type=int,
            default=0,
            help="Which opinion ID should we start with, in case it crashes?",
        )
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            default=False,
            help="Auto resume the command using the last document_id logged in Redis. "
            "If --start-id is provided, it'll be ignored.",
        )
        parser.add_argument(
            "--count",
            type=int,
            help="The number of opinions to process.",
        )
        parser.add_argument(
            "--indexing-queue",
            type=str,
            default="batch1",
            help="Which celery queue to use for embeddings indexing.",
        )
        parser.add_argument(
            "--retrieval-queue",
            type=str,
            default="batch1",
            help="Which celery queue to use for S3 retrieval.",
        )
        parser.add_argument(
            "--throttle-min-items",
            type=int,
            default=5,
            help="The celery throttle min items.",
        )

    def handle(self, *args, **options):
        retrieval_queue = options["retrieval_queue"]
        indexing_queue = options["indexing_queue"]
        batch_size = options["batch_size"]
        count = options["count"]
        auto_resume = options["auto_resume"]
        start_id = options["start_id"]
        throttle_min_items = options["throttle_min_items"]
        self.throttle = CeleryThrottle(
            queue_name=indexing_queue, min_items=throttle_min_items
        )
        if auto_resume:
            start_id = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            self.stdout.write(
                f"Auto-resume enabled starting embeddings indexing from ID: {start_id}."
            )

        opinions = Opinion.objects.filter(id__gte=start_id)
        # Limit opinions to retrieve if count was provided.
        opinions_to_process = (
            opinions[:count] if count is not None else opinions
        )
        count = opinions_to_process.count()
        chunk: list[int] = []
        processed_count = 0
        for opinion in opinions_to_process.iterator():
            opinion_id = opinion.pk
            chunk.append(opinion_id)
            processed_count += 1
            last_item = count == processed_count
            if processed_count % batch_size == 0 or last_item:
                self.throttle.maybe_wait()
                chain(
                    retrieve_embeddings.si(chunk).set(queue=retrieval_queue),
                    index_embeddings.s().set(queue=indexing_queue),
                ).apply_async()
                chunk = []

            logger.info(
                "\rProcessed %s/%s, (%s), last ID requested for embeddings indexing: %s",
                processed_count,
                count,
                f"{processed_count * 1.0 / count:.0%}",
                opinion_id,
            )
            if not processed_count % 1000:
                # Log every 1000 documents processed.
                log_last_document_indexed(opinion_id, compose_redis_key())

        logger.info(
            "Successfully requested for embeddings indexing %s items from pk %s.",
            processed_count,
            start_id,
        )
