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


class Command(CorpusImporterCommand):
    help = "Import Texas dockets from S3 using an inventory CSV."

    compose_redis_key = "texas_docket_import:log"

    @staticmethod
    def transform_inventory_iterator(
        csv_reader: Iterable[list[str]],
    ) -> Iterable[tuple[tuple[str, str], tuple[str, str]]]:
        html_rows = filter(
            lambda r: Path(r[1]).suffix == ".html" and "searches" not in r[1],
            map(lambda r: (r[0].strip(), r[1].strip()), csv_reader),
        )

        previous_key_stem = None
        for html_row in html_rows:
            html_bucket, html_key = html_row
            html_path = Path(html_key)
            docket_name = html_path.stem
            if previous_key_stem and docket_name.startswith(previous_key_stem):
                continue
            else:
                previous_key_stem = docket_name
            meta_key = str(html_path.with_name(f"{docket_name}_meta.json"))
            yield (
                (html_bucket, html_key),
                (html_bucket, meta_key),
            )

    @staticmethod
    def download_task() -> app.Task:
        return texas_corpus_download_task

    @staticmethod
    def merge_task() -> app.Task:
        return texas_ingest_docket_task
