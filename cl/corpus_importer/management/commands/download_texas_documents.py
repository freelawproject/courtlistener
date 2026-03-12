import time

from celery import chain
from django.db.models import Q

from cl.corpus_importer.tasks import download_texas_document_pdf, logger
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.scrapers.tasks import extract_pdf_document
from cl.search.models import TexasDocument


def download_and_extract_texas_documents(
    download_queue: str, extraction_queue: str, delay: float
) -> None:
    """
    Download and extract attachments for TexasDocument with a missing or stale
    local file.

    Queries TexasDocument instances that have no filepath_local or have
    `ocr_status` not unnecessary or complete, then schedules a download ->
    extraction chain for each.

    :param download_queue: The celery queue for download tasks.
    :param extraction_queue: The celery queue for extraction tasks.
    :param delay: Seconds to sleep between scheduling tasks.
    :return: None
    """
    docs = (
        TexasDocument.objects.filter(Q(filepath_local=""))
        .exclude(
            ocr_status__notin=(
                TexasDocument.OCR_UNNECESSARY,
                TexasDocument.OCR_COMPLETE,
            )
        )
        .values_list("pk", flat=True)
        .order_by()
    )
    count = docs.count()
    logger.info(
        "Found %s TexasDocuments needing download or extraction.", count
    )
    throttle = CeleryThrottle(queue_name=extraction_queue)
    processed_count = 0
    for pk in docs.iterator():
        throttle.maybe_wait()
        chain(
            download_texas_document_pdf.si(pk).set(queue=download_queue),
            extract_pdf_document.s(
                check_if_needed=False,
                model_name="search.TexasDocument",
            ).set(queue=extraction_queue),
        ).apply_async()
        processed_count += 1
        if processed_count % 100 == 0:
            logger.info(
                "Scheduled %s/%s (%s)",
                processed_count,
                count,
                f"{processed_count / count:.0%}",
            )
        time.sleep(delay)
    logger.info(
        "Scheduled %s/%s",
        processed_count,
        count,
    )


class Command(VerboseCommand):
    help = "Download and extract PDFs for TexasDocument instances which have missing or stale local files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--download-queue",
            type=str,
            default="celery",
            help="The celery queue for PDF download tasks.",
        )
        parser.add_argument(
            "--extraction-queue",
            type=str,
            default="celery",
            help="The celery queue for PDF extraction tasks.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Seconds to sleep between scheduling tasks.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        extraction_queue = options["extraction_queue"]
        delay = options["delay"]
        download_queue = options["download_queue"]

        logger.info("Downloading and extracting TexasDocument attachments...")
        download_and_extract_texas_documents(
            download_queue, extraction_queue, delay
        )
