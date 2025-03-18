from celery import chain

from django.conf import settings

from cl.lib.command_utils import VerboseCommand
from cl.search.models import Opinion
from cl.search.tasks import create_opinion_text_embeddings, save_embeddings
from cl.lib.string_utils import get_token_count_from_string


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
        min_opinion_size = settings.MIN_OPINION_SIZE

        opinions = (
            Opinion.objects.filter(id__gte=options["start_id"])
            .order_by("pk")
            .with_best_text()
        )
        # Limit opinions to retrieve if count was provided.
        opinions = opinions[:count] if count is not None else opinions

        current_batch: list[int] = []
        current_batch_size = 0
        for opinion in opinions.iterator():
            token_count = get_token_count_from_string(opinion.best_text)
            if token_count < min_opinion_size:
                continue
            # Check if adding this opinion would exceed the batch size.
            if current_batch_size + token_count > batch_size:
                # Send the current batch since adding this opinion would break the limit.
                send_batch(current_batch, embedding_queue, upload_queue,
                           database)
                current_batch = []
                current_batch_size = 0

            current_batch.append(opinion.id)
            current_batch_size += token_count

        # Send any remainder
        if current_batch:
            send_batch(current_batch, embedding_queue, upload_queue, database)
