from celery import chain
from django.conf import settings

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.models import SEARCH_TYPES, Opinion
from cl.search.tasks import create_opinion_text_embeddings, save_embeddings


def compose_redis_key() -> str:
    """Compose a Redis key based on the search type for embedding log.
    :return: A Redis key as a string.
    """
    return f"{SEARCH_TYPES.OPINION}_inception_embedding:log"


class Command(VerboseCommand):
    help = "Gets text embeddings for opinions and stores them in S3."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.throttle = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            type=str,
            default="default",
            help="Let the user decide which DB name to use",
        )
        parser.add_argument(
            "--token-count",
            type=int,
            help="How many tokens per batch.",
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
            "--embedding-queue",
            type=str,
            default="batch1",
            help="Which celery queue to use for embedding.",
        )
        parser.add_argument(
            "--upload-queue",
            type=str,
            default="batch1",
            help="which celery queue to use for uploading to S3.",
        )
        parser.add_argument(
            "--throttle-min-items",
            type=int,
            default=5,
            help="The celery throttle min items.",
        )

    def send_batch(
        self,
        batch: list[int],
        embedding_queue: str,
        upload_queue: str,
        database: str,
    ) -> None:
        """Send a batch of items for embedding creation and saving to S3.

        :param batch: A list of Opinion IDs representing the batch to process.
        :param embedding_queue: The name of the queue to process the embedding task.
        :param upload_queue: The name of the queue to process the saving task.
        :param database: The database to be used during processing.
        :return: None.
        """
        self.throttle.maybe_wait()
        chain(
            create_opinion_text_embeddings.si(batch, database).set(
                queue=embedding_queue
            ),
            save_embeddings.s().set(queue=upload_queue),
        ).apply_async()

    def handle(self, *args, **options):
        embedding_queue = options["embedding_queue"]
        upload_queue = options["upload_queue"]
        database = options["database"]
        token_count_limit = options["token_count"]
        count = options.get("count", None)
        auto_resume = options["auto_resume"]
        min_opinion_size = settings.MIN_OPINION_SIZE
        start_id = options["start_id"]
        throttle_min_items = options["throttle_min_items"]
        self.throttle = CeleryThrottle(
            queue_name=embedding_queue, min_items=throttle_min_items
        )
        if auto_resume:
            start_id = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            self.stdout.write(
                f"Auto-resume enabled starting embedding from ID: {start_id}."
            )

        opinions = Opinion.objects.using(database).filter(id__gte=start_id)
        # Limit opinions to retrieve if count was provided.
        opinions_to_process = (
            opinions[:count] if count is not None else opinions
        )
        opinions_with_best_text = opinions.order_by("pk").with_best_text()
        opinions_with_best_text = (
            opinions_with_best_text[:count] if count is not None else opinions
        )

        logger.info("Getting count of opinions to process.")
        count = opinions_to_process.count()
        logger.info("Count finished.")
        current_batch: list[int] = []
        current_batch_size = 0
        processed_count = 0
        for opinion in opinions_with_best_text.iterator(chunk_size=1000):
            opinion_id = opinion.pk
            processed_count += 1
            token_count = opinion.token_count
            if token_count < min_opinion_size:
                continue
            if token_count > token_count_limit:
                # Log documents that individually exceed the batch size.
                logger.error(
                    "The opinion ID:%s exceeds the batch size limit.",
                    opinion_id,
                )
                continue
            # Check if adding this opinion would exceed the batch size.
            if current_batch_size + token_count > token_count_limit:

                # Send the current batch since adding this opinion would break the limit.
                self.send_batch(
                    current_batch, embedding_queue, upload_queue, database
                )
                current_batch = []
                current_batch_size = 0

            current_batch.append(opinion_id)
            current_batch_size += token_count
            if not processed_count % 1000:
                # Log every 1000 documents processed.
                log_last_document_indexed(opinion_id, compose_redis_key())
                logger.info(
                    "Processed %s/%s, (%s), last ID requested for embedding: %s",
                    processed_count,
                    count,
                    f"{processed_count * 1.0 / count:.0%}",
                    opinion_id,
                )

        # Send any remainder
        if current_batch:
            self.send_batch(
                current_batch, embedding_queue, upload_queue, database
            )

        logger.info(
            "Successfully requested for embedding %s items from pk %s.",
            processed_count,
            start_id,
        )
