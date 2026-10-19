from collections.abc import Iterable
from typing import ClassVar

from pydantic import Field

from celery import Task

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

    compose_redis_key: ClassVar[str] = "florida_docket_import:log"

    fill_case_transfer: bool = Field(
        alias="fill-case-transfer",
        default=False,
        description="Fill null dockets in CaseTransfer table",
    )
    skip_case_merge: bool = Field(
        alias="skip-case-merge",
        default=False,
        description="Skip merging cases from the inventory file",
    )

    @staticmethod
    def transform_inventory_iterator(
        csv_reader: Iterable[list[str]],
    ) -> Iterable[tuple[str, str]]:
        return map(lambda r: (r[0].strip(), r[1].strip()), csv_reader)

    @staticmethod
    def download_task() -> Task:
        return fl_corpus_download_task

    @staticmethod
    def merge_task() -> Task:
        return fl_ingest_docket_task

    def run(self):
        if not self.skip_case_merge:
            super().run()
        if self.fill_case_transfer:
            CaseTransfer.fill_null_dockets()
