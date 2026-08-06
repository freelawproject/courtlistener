from collections.abc import Iterable

from cl.celery_init import app
from cl.corpus_importer.management.utils import (
    CorpusImporterCommand,
)
from cl.corpus_importer.tasks import (
    fl_corpus_download_task,
    fl_ingest_docket_task,
)
from cl.search.models import CaseTransfer


class Command(CorpusImporterCommand):
    help = "Import Florida dockets from S3 using an inventory CSV."

    compose_redis_key = "florida_docket_import:log"

    @staticmethod
    def transform_inventory_iterator(
        csv_reader: Iterable[list[str]],
    ) -> Iterable[tuple[str, str]]:
        return map(lambda r: (r[0].strip(), r[1].strip()), csv_reader)

    @staticmethod
    def download_task() -> app.Task:
        return fl_corpus_download_task

    @staticmethod
    def merge_task() -> app.Task:
        return fl_ingest_docket_task

    def handle(self, *args, **options):
        super().handle(*args, **options)
        CaseTransfer.fill_null_dockets()
