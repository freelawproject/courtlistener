from collections.abc import Iterable
from pathlib import Path

from cl.celery_init import app
from cl.corpus_importer.management.utils import (
    CorpusImporterCommand,
)
from cl.corpus_importer.tasks import (
    texas_corpus_download_task,
    texas_ingest_docket_task,
)
from cl.search.models import CaseTransfer


class Command(CorpusImporterCommand):
    help = "Import Texas dockets from S3 using an inventory CSV."

    compose_redis_key = "texas_docket_import:log"

    @staticmethod
    def transform_inventory_iterator(
        csv_reader: Iterable[list[str]],
    ) -> Iterable[tuple[tuple[str, str], tuple[str, str]]]:
        meta_rows = filter(
            # Filter only for meta files which are not duplicates (don't end in "_X") and not for search result scrapes
            lambda r: "searches" not in r[1]
            and Path(r[1]).name.endswith("_meta.json"),
            map(lambda r: (r[0].strip(), r[1].strip()), csv_reader),
        )

        for meta_row in meta_rows:
            meta_bucket, meta_key = meta_row
            meta_path = Path(meta_key)
            docket_name = meta_path.stem.removesuffix("_meta")
            html_key = str(meta_path.with_name(f"{docket_name}.html"))
            yield (
                (meta_bucket, html_key),
                (meta_bucket, meta_key),
            )

    @staticmethod
    def download_task() -> app.Task:
        return texas_corpus_download_task

    @staticmethod
    def merge_task() -> app.Task:
        return texas_ingest_docket_task

    def handle(self, *args, **options):
        super().handle(*args, **options)
        CaseTransfer.fill_null_dockets()
