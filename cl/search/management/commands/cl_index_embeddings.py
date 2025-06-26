import csv
import re

import boto3
from celery import chain
from django.core.management import CommandError

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
        self.retrieval_queue = None
        self.indexing_queue = None
        self.batch_size = None

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
            help="Which opinion ID or CSV row should we start with, in case it crashes?",
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
        parser.add_argument(
            "--s3-bucket",
            type=str,
            help="The related inventory S3 bucket.",
            default="com-courtlistener-storage",
        )
        parser.add_argument(
            "--inventory",
            type=str,
            help="The inventory file to process embeddings.",
        )
        parser.add_argument(
            "--inventory-rows",
            type=int,
            help="The number of rows in the inventory file.",
        )

    def maybe_schedule_chunk(
        self,
        chunk: list[int],
        processed_count: int,
        count: int,
    ) -> None:
        """Schedule a chunk of IDs for embedding retrieval and indexing if the
        batch is ready.

        :param chunk: List of opinion IDs to be processed in the current batch.
        :param processed_count: Number of items processed so far.
        :param count: Total number of items to process.
        :return: None
        """
        last_item = count == processed_count
        if processed_count % self.batch_size == 0 or last_item:
            self.throttle.maybe_wait()
            chain(
                retrieve_embeddings.si(chunk).set(queue=self.retrieval_queue),
                index_embeddings.s().set(queue=self.indexing_queue),
            ).apply_async()
            chunk.clear()

    @staticmethod
    def maybe_log_progress(processed_count: int, opinion_id: int, total: int):
        """Log progress and store a checkpoint in Redis
        during indexing every 1000 items.

        :param processed_count: Number of items processed so far.
        :param opinion_id: The last opinion ID processed.
        :param total: Total number of items to process.
        :return: None
        """
        if processed_count % 1000 == 0:
            logger.info(
                "Processed %s/%s, (%s), last ID/row requested for embeddings indexing: %s",
                processed_count,
                total,
                f"{processed_count * 1.0 / total:.0%}",
                opinion_id,
            )
            log_last_document_indexed(opinion_id, compose_redis_key())

    def handle(self, *args, **options):
        self.retrieval_queue = options["retrieval_queue"]
        self.indexing_queue = options["indexing_queue"]
        self.batch_size = options["batch_size"]
        count = options["count"]
        auto_resume = options["auto_resume"]
        start_id = options["start_id"]
        throttle_min_items = options["throttle_min_items"]
        s3_bucket = options["s3_bucket"]
        inventory_key = options.get("inventory")
        inventory_rows = options.get("inventory_rows")

        if inventory_key and not inventory_rows:
            raise CommandError(
                "--inventory-rows is required for --inventory processing."
            )

        self.throttle = CeleryThrottle(
            queue_name=self.indexing_queue, min_items=throttle_min_items
        )
        if auto_resume:
            start_id = get_last_parent_document_id_processed(
                compose_redis_key()
            )
            self.stdout.write(
                f"Auto-resume enabled starting embeddings indexing from ID: {start_id}."
            )

        chunk: list[int] = []
        processed_count = 0
        if inventory_key:
            # Process opinions from the inventory file.
            # Set the count based on the remaining rows to process if auto-resume is enabled
            count = (
                inventory_rows - start_id if auto_resume else inventory_rows
            )
            id_pattern = re.compile(r"/(\d+)\.json$")
            s3 = boto3.client("s3")
            response = s3.get_object(Bucket=s3_bucket, Key=inventory_key)
            body = response["Body"].iter_lines(chunk_size=1024)
            reader = csv.reader(line.decode("utf-8") for line in body)
            for idx, row in enumerate(reader):
                if auto_resume and idx < start_id:
                    # Skip row if auto-resume is enabled
                    continue
                opinion_id_match = id_pattern.search(row[1])
                opinion_id = int(opinion_id_match.group(1))
                chunk.append(opinion_id)
                processed_count += 1
                self.maybe_schedule_chunk(chunk, processed_count, count)
                self.maybe_log_progress(processed_count, idx, count)
        else:
            # Process opinions from DB.
            opinions = Opinion.objects.filter(id__gte=start_id).order_by("pk")
            # Limit opinions to retrieve if count was provided.
            opinions_to_process = (
                opinions[:count] if count is not None else opinions
            )
            count = opinions_to_process.count()
            for opinion in opinions_to_process.iterator():
                opinion_id = opinion.pk
                chunk.append(opinion_id)
                processed_count += 1
                self.maybe_schedule_chunk(chunk, processed_count, count)
                self.maybe_log_progress(processed_count, opinion_id, count)

        logger.info(
            "Successfully requested for embeddings indexing %s items from pk %s.",
            processed_count,
            start_id,
        )
