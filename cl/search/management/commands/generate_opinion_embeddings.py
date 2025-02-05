from cl.lib.command_utils import VerboseCommand
from cl.search.models import Opinion
from cl.search.tasks import create_opinion_text_embeddings


def send_batch(
    batch: list[int],
    embedding_queue: str,
    upload_queue: str,
    database: str,
    bucket_name: str,
) -> None:
    create_opinion_text_embeddings.si(
        batch,
        upload_queue,
        database,
        bucket_name,
    ).apply_async(queue=embedding_queue)


class Command(VerboseCommand):
    help = "Gets text embeddings for opinions and stores them in S3."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            type=str,
            default="default",
            help="Let the user decide which DB name to use (default to 'default')",
        )
        parser.add_argument(
            "--bucket-name",
            type=str,
            help="Name of the bucket where embeddings will be stored.",
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
            help="Which opinion ID should we start with, in case it crashes? (default to 0)",
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
            help="which celery queue for uploading to S3 (default to 'batch1')",
        )

    def handle(self, *args, **options):
        embedding_queue = options["embedding_queue"]
        upload_queue = options["upload_queue"]
        database = options["database"]
        bucket_name = options["bucket_name"]
        batch_size = options["batch_size"]

        opinions = Opinion.objects.all()

        current_batch: list[int] = []
        current_batch_size = 0

        for opinion in opinions:
            token_count = opinion.token_count
            current_batch_size += token_count
            current_batch.append(opinion.id)
            if current_batch_size >= batch_size:
                send_batch(
                    current_batch,
                    embedding_queue,
                    upload_queue,
                    database,
                    bucket_name,
                )
                current_batch = []
                current_batch_size = 0
