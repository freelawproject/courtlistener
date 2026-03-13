import time
from itertools import batched

from celery import chain
from django.db.models import Q

from cl.corpus_importer.tasks import download_texas_document_pdf, logger
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.scrapers.tasks import extract_pdf_document
from cl.search.models import TexasDocument


def extract_texas_documents(
    extraction_queue: str, batch_size: int, delay: float
) -> None:
    """
    Run the extraction task for TexasDocument instances where ocr_status is not
    OCR_UNNECESSARY or OCR_COMPLETE.

    :param extraction_queue: The celery queue for PDF extraction tasks.
    :param batch_size: The batch size for PDF extraction tasks.
    :param delay: Seconds to sleep between scheduling tasks.

    :return: None
    """
    docs = (
        TexasDocument.objects.exclude(
            Q(filepath_local="")
            | Q(
                ocr_status__in=(
                    TexasDocument.OCR_UNNECESSARY,
                    TexasDocument.OCR_COMPLETE,
                )
            )
        )
        .values_list("pk", flat=True)
        .order_by()
    )
    count = docs.count()
    logger.info("Found %s TexasDocuments needing extraction.", count)
    throttle = CeleryThrottle(queue_name=extraction_queue)
    processed_count = 0
    for pks in batched(docs.iterator(), batch_size):
        throttle.maybe_wait()
        extract_pdf_document.si(
            pks=pks,
            check_if_needed=False,
            model_name="search.TexasDocument",
        ).set(queue=extraction_queue).apply_async()
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


def download_and_extract_texas_documents(
    download_queue: str, extraction_queue: str, delay: float
) -> None:
    """
    Download and extract attachments for TexasDocument with a missing or stale
    local file.

    Queries TexasDocument instances that have no filepath_local, then schedules
    a download -> extraction chain for each.

    :param download_queue: The celery queue for download tasks.
    :param extraction_queue: The celery queue for extraction tasks.
    :param delay: Seconds to sleep between scheduling tasks.

    :return: None
    """
    docs = (
        TexasDocument.objects.filter(filepath_local="")
        .values_list("pk", flat=True)
        .order_by()
    )
    count = docs.count()
    logger.info(
        "Found %s TexasDocuments needing download and extraction.", count
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
            "--only-extraction",
            type=bool,
            default=False,
            help="Skip downloading attachments and only run the extraction task.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="The batch size for PDF extraction tasks. Only used if --only-extraction is true.",
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
        only_extraction = options["only_extraction"]

        if only_extraction:
            batch_size = options["batch_size"]
            logger.info("Running extraction for TexasDocuments...")
            extract_texas_documents(extraction_queue, batch_size, delay)
        else:
            download_queue = options["download_queue"]
            logger.info(
                "Downloading and extracting TexasDocument attachments..."
            )
            download_and_extract_texas_documents(
                download_queue, extraction_queue, delay
            )
