import time
from itertools import batched

from celery import chain

from cl.corpus_importer.tasks import download_scotus_document_pdf
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.tasks import extract_pdf_document
from cl.search.models import SCOTUSDocument


def download_and_extract_scotus_pdfs(
    download_queue: str,
    extraction_queue: str,
    delay: float,
) -> None:
    """Download and extract PDFs for SCOTUSDocuments missing a local file.

    Queries SCOTUSDocument instances that have a URL but no filepath_local,
    then schedules a download -> extraction chain for each.

    :param download_queue: The celery queue for download tasks.
    :param extraction_queue: The celery queue for extraction tasks.
    :param delay: Seconds to sleep between scheduling tasks.
    :return: None
    """
    docs = (
        SCOTUSDocument.objects.exclude(url="")
        .filter(filepath_local="")
        .values_list("pk", flat=True)
        .order_by()
    )
    count = docs.count()
    logger.info("Found %s SCOTUSDocuments needing download.", count)
    throttle = CeleryThrottle(queue_name=download_queue)
    processed_count = 0
    for pk in docs.iterator():
        throttle.maybe_wait()
        chain(
            download_scotus_document_pdf.si(pk).set(queue=download_queue),
            extract_pdf_document.s(
                check_if_needed=False,
                model_name="search.SCOTUSDocument",
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
        "Scheduled %s/%s (%s)",
        processed_count,
        count,
        f"{processed_count / count:.0%}",
    )


def extract_scotus_pdfs(
    extraction_queue: str,
    chunk_size: int,
    delay: float,
) -> None:
    """Extract text from SCOTUSDocuments that have a file but no plain_text.

    Queries SCOTUSDocument instances that already have a filepath_local but
    have not been extracted yet (empty plain_text).

    :param extraction_queue: The celery queue for extraction tasks.
    :param chunk_size: The number of items to extract per celery task batch.
    :param delay: Seconds to sleep between scheduling tasks.
    :return: None
    """
    docs = (
        SCOTUSDocument.objects.exclude(filepath_local="")
        .filter(plain_text="")
        .values_list("pk", flat=True)
        .order_by()
    )
    count = docs.count()
    logger.info("Found %s SCOTUSDocuments needing extraction.", count)
    throttle = CeleryThrottle(queue_name=extraction_queue)
    processed_count = 0
    for chunk in batched(docs.iterator(), chunk_size):
        throttle.maybe_wait()
        processed_count += len(chunk)
        extract_pdf_document.si(
            list(chunk),
            check_if_needed=False,
            model_name="search.SCOTUSDocument",
        ).set(queue=extraction_queue).apply_async()
        logger.info(
            "Scheduled %s/%s (%s)",
            processed_count,
            count,
            f"{processed_count / count:.0%}",
        )
        time.sleep(delay)


class Command(VerboseCommand):
    help = (
        "Download and extract PDFs for SCOTUSDocument instances. "
        "By default, downloads missing PDFs and extracts them. "
        "Use --only-extraction to skip downloads and only extract "
        "already-downloaded files."
    )

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
            action="store_true",
            default=False,
            help="Only extract text from already-downloaded PDFs. "
            "Skips the download step.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=10,
            help="The number of PDFs to extract in a single celery task "
            "(only used with --only-extraction).",
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

        if options["only_extraction"]:
            chunk_size = options["chunk_size"]
            logger.info(
                "Extracting SCOTUSDocument PDFs (extraction only)."
            )
            extract_scotus_pdfs(extraction_queue, chunk_size, delay)
        else:
            download_queue = options["download_queue"]
            logger.info(
                "Downloading and extracting SCOTUSDocument PDFs."
            )
            download_and_extract_scotus_pdfs(
                download_queue, extraction_queue, delay
            )
