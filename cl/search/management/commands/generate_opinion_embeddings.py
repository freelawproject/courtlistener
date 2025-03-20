from celery import chain
from django.conf import settings

from cl.lib.command_utils import VerboseCommand
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.lib.string_utils import get_token_count_from_string
from cl.search.management.commands.pacer_bulk_fetch import (
    append_value_in_cache,
)
from cl.search.models import SEARCH_TYPES, Opinion
from cl.search.tasks import create_opinion_text_embeddings, save_embeddings


def compose_redis_key() -> str:
    """Compose a Redis key based on the search type for embedding log.
    :return: A Redis key as a string.
    """
    return f"{SEARCH_TYPES.OPINION}_inception_embedding:log"


def long_document_key() -> str:
    """Compose a Redis key based on the search type for embedding log.
    :return: A Redis key as a string.
    """
    return f"{SEARCH_TYPES.OPINION}_long_document"


def send_batch(
    batch: list[int],
    embedding_queue: str,
    upload_queue: str,
    database: str,
) -> None:
    chain(
        create_opinion_text_embeddings.si(batch, database).set(
            queue=embedding_queue
        ),
        save_embeddings.s().set(queue=upload_queue),
    ).apply_async()


class Command(VerboseCommand):
    help = "Gets text embeddings for opinions and stores them in S3."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            type=str,
            default="default",
            help="Let the user decide which DB name to use",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            help="How many tokens per batch.",
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
            help="The number of opinions embedding to generate.",
        )
        parser.add_argument(
            "--embedding-queue",
            type=str,
            help="Which celery queue to use for embedding.",
        )
        parser.add_argument(
            "--upload-queue",
            type=str,
            default="batch1",
            help="which celery queue to use for uploading to S3",
        )

    def handle(self, *args, **options):
        embedding_queue = options["embedding_queue"]
        upload_queue = options["upload_queue"]
        database = options["database"]
        batch_size = options["batch_size"]
        count = options.get("count", None)
        auto_resume = options["auto_resume"]
        min_opinion_size = settings.MIN_OPINION_SIZE
        start_id = options["start_id"]
        if auto_resume:
            start_id = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            self.stdout.write(
                f"Auto-resume enabled starting embedding from ID: {start_id}."
            )

        opinions = (
            Opinion.objects.filter(id__gte=start_id)
            .order_by("pk")
            .with_best_text()
        )
        # Limit opinions to retrieve if count was provided.
        opinions = opinions[:count] if count is not None else opinions
        count = opinions.count()
        current_batch: list[int] = []
        current_batch_size = 0
        processed_count = 0
        for opinion in opinions.iterator():
            opinion_id = opinion.pk
            processed_count += 1
            token_count = get_token_count_from_string(opinion.best_text)
            if token_count < min_opinion_size:
                continue
            if token_count > batch_size:
                # Log documents that individually exceed the batch size.
                append_value_in_cache(long_document_key(), opinion_id)
                continue
            # Check if adding this opinion would exceed the batch size.
            if current_batch_size + token_count > batch_size:
                # Send the current batch since adding this opinion would break the limit.
                send_batch(
                    current_batch, embedding_queue, upload_queue, database
                )
                current_batch = []
                current_batch_size = 0

            current_batch.append(opinion_id)
            current_batch_size += token_count
            self.stdout.write(
                "\rProcessed {}/{}, ({:.0%}), last ID requested for embedding: {},".format(
                    processed_count,
                    count,
                    processed_count * 1.0 / count,
                    opinion_id,
                )
            )
            if not processed_count % 1000:
                # Log every 1000 documents processed.
                log_last_document_indexed(opinion_id, compose_redis_key())

        # Send any remainder
        if current_batch:
            send_batch(current_batch, embedding_queue, upload_queue, database)

        self.stdout.write(
            f"Successfully requested for embedding {processed_count} items from"
            f" pk {start_id}."
        )
