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

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--fill-case-transfer",
            action="store_true",
            help="Fill null dockets in CaseTransfer table",
            default=False,
        )
        parser.add_argument(
            "--skip-case-merge",
            action="store_true",
            help="Skip merging cases from the inventory file",
            default=False,
        )

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

    def handle(
        self, *args, fill_case_transfer: bool, skip_case_merge: bool, **options
    ):
        if not skip_case_merge:
            super().handle(*args, **options)
        if fill_case_transfer:
            CaseTransfer.fill_null_dockets()
