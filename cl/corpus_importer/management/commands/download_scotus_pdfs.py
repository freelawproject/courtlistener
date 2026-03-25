import time

from django.db.models import Q

from cl.corpus_importer.tasks import download_scotus_document_pdf
from cl.corpus_importer.utils import paginate_docs_queryset
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.tasks import extract_pdf_document
from cl.search.models import SCOTUSDocument


def download_scotus_pdfs(
    download_queue: str,
    delay: float,
) -> None:
    """Download PDFs for SCOTUSDocuments missing a local file.

    Queries SCOTUSDocument instances that have no filepath_local,
    then schedules a download task for each.

    :param download_queue: The celery queue for download tasks.
    :param delay: Seconds to sleep between scheduling tasks.
    :return: None
    """
    docs = SCOTUSDocument.objects.filter(filepath_local="").values_list(
        "pk", flat=True
    )
    count = docs.count()
    logger.info("Found %s SCOTUSDocuments needing download.", count)
    throttle = CeleryThrottle(queue_name=download_queue)
    processed_count = 0
    for pk in paginate_docs_queryset(docs):
        throttle.maybe_wait()
        download_scotus_document_pdf.si(pk).set(
            queue=download_queue
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


def extract_scotus_pdfs(
    extraction_queue: str,
    chunk_size: int,
    delay: float,
    page_limit: int,
) -> None:
    """Extract text from SCOTUSDocuments that have a file but incomplete OCR.

    Queries SCOTUSDocument instances that already have a filepath_local but
    whose OCR status is not complete or unnecessary. Documents with a
    page_count exceeding page_limit are skipped, allowing smaller documents
    to be processed first.

    :param extraction_queue: The celery queue for extraction tasks.
    :param chunk_size: The number of items to extract per celery task batch.
    :param delay: Seconds to sleep between scheduling tasks.
    :param page_limit: Skip documents with more pages than this value.
    :return: None
    """
    docs = (
        SCOTUSDocument.objects.exclude(filepath_local="")
        .exclude(
            Q(ocr_status=SCOTUSDocument.OCR_COMPLETE)
            | Q(ocr_status=SCOTUSDocument.OCR_UNNECESSARY)
        )
        .values_list("pk", "page_count")
    )
    count = docs.count()
    logger.info("Found %s SCOTUSDocuments needing extraction.", count)
    throttle = CeleryThrottle(queue_name=extraction_queue)
    processed_count = 0
    skipped_count = 0
    chunk: list[int] = []
    for pk, page_count in paginate_docs_queryset(docs):
        if page_count is not None and page_count > page_limit:
            skipped_count += 1
            continue
        chunk.append(pk)
        if len(chunk) < chunk_size:
            continue
        throttle.maybe_wait()
        processed_count += len(chunk)
        extract_pdf_document.si(
            chunk,
            check_if_needed=False,
            model_name="search.SCOTUSDocument",
        ).set(queue=extraction_queue).apply_async()
        logger.info(
            "Scheduled %s/%s (%s)",
            processed_count,
            count,
            f"{processed_count / count:.0%}",
        )
        chunk = []
        time.sleep(delay)
    if chunk:
        throttle.maybe_wait()
        processed_count += len(chunk)
        extract_pdf_document.si(
            chunk,
            check_if_needed=False,
            model_name="search.SCOTUSDocument",
        ).set(queue=extraction_queue).apply_async()
        logger.info(
            "Scheduled %s/%s (%s)",
            processed_count,
            count,
            f"{processed_count / count:.0%}",
        )
    logger.info(
        "Done. Scheduled %s, skipped %s (over %s pages).",
        processed_count,
        skipped_count,
        page_limit,
    )


class Command(VerboseCommand):
    help = (
        "Download and extract PDFs for SCOTUSDocument instances. "
        "By default, downloads missing PDFs. "
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
            "--page-limit",
            type=int,
            default=50,
            help="Skip documents with more pages than this value "
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

        delay = options["delay"]

        if options["only_extraction"]:
            chunk_size = options["chunk_size"]
            page_limit = options["page_limit"]
            extraction_queue = options["extraction_queue"]
            logger.info(
                "Extracting SCOTUSDocument PDFs (page limit: %s).",
                page_limit,
            )
            extract_scotus_pdfs(
                extraction_queue, chunk_size, delay, page_limit
            )
        else:
            download_queue = options["download_queue"]
            logger.info("Downloading SCOTUSDocument PDFs.")
            download_scotus_pdfs(download_queue, delay)
