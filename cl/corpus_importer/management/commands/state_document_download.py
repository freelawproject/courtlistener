"""Command and utilities to download state docket entry attachments."""

from django.apps import apps
from django.core.management import CommandParser
from django.core.management.base import CommandError

from cl.corpus_importer.tasks import download_state_document
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.search.state.shared import AbstractStateDocument


class Command(VerboseCommand):
    """Command to download state docket entry attachments."""

    help = "Download state docket entry attachments."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--model",
            type=str,
            help="The model to download (app_label.ModelName).",
            required=True,
        )
        parser.add_argument(
            "--queue",
            type=str,
            help="The celery queue to use for downloads.",
            default="celery",
        )
        parser.add_argument(
            "--throttle-min-items",
            type=int,
            default=5,
            help="CeleryThrottle min_items parameter.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=1000,
            help="The size of chunks to retrieve from the DB.",
        )

    def handle(
        self,
        *args,
        model: str,
        queue: str,
        throttle_min_items: int,
        chunk_size: int,
        **options,
    ) -> None:
        """Download state docket entry attachments.

        :param model: The model to download (app_label.ModelName).
        :param queue: The celery queue to use for downloads.
        :param throttle_min_items: CeleryThrottle min_items parameter.
        :param chunk_size: The size of chunks to retrieve from the DB."""
        super().handle(*args, **options)
        model_cls = apps.get_model(model)
        if not issubclass(model_cls, AbstractStateDocument):
            raise CommandError(
                f"Model {model} must be an AbstractStateDocument subclass."
            )
        throttle = CeleryThrottle(
            min_items=throttle_min_items, queue_name=queue
        )
        for pk in (
            model_cls.objects.filter(filepath_local="")
            .exclude(url="")
            .values_list("pk", flat=True)
            .iterator(chunk_size=chunk_size)
        ):
            throttle.maybe_wait()
            download_state_document.si(model_cls._meta.label, pk).set(
                queue=queue
            ).apply_async()
