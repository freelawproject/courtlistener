import time
from itertools import batched

from django.db.models import Q

from cl.corpus_importer.tasks import (
    download_texas_document_pdf_unthrottled,
    logger,
)
from cl.corpus_importer.utils import paginate_docs_queryset
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.scrapers.tasks import extract_pdf_document
from cl.search.models import TexasDocument


def compose_redis_key() -> str:
    """Compose a Redis key for Texas document download log.
    :return: A Redis key as a string.
    """
    return "texas_document_download:log"


def extract_texas_documents(
    extraction_queue: str,
    batch_size: int,
    delay: float,
    page_limit: int,
) -> None:
    """Run the extraction task for TexasDocument instances needing OCR.

    Queries TexasDocument instances that already have a filepath_local but
    whose OCR status is not complete or unnecessary. Documents with a
    page_count exceeding page_limit are skipped, allowing smaller documents
    to be processed first.

    :param extraction_queue: The celery queue for PDF extraction tasks.
    :param batch_size: The batch size for PDF extraction tasks.
    :param delay: Seconds to sleep between scheduling tasks.
    :param page_limit: Skip documents with more pages than this value.
    :return: None
    """
    docs = TexasDocument.objects.exclude(
        Q(filepath_local="")
        | Q(
            ocr_status__in=(
                TexasDocument.OCR_UNNECESSARY,
                TexasDocument.OCR_COMPLETE,
            )
        )
    ).values_list("pk", flat=True)
    total_count = docs.count()
    filtered_docs = docs.filter(
        Q(page_count__lte=page_limit) | Q(page_count__isnull=True)
    )
    filtered_count = filtered_docs.count()
    skipped_count = total_count - filtered_count
    logger.info("Found %s TexasDocuments needing extraction.", total_count)
    throttle = CeleryThrottle(queue_name=extraction_queue)
    processed_count = 0
    for chunk in batched(paginate_docs_queryset(filtered_docs), batch_size):
        throttle.maybe_wait()
        processed_count += len(chunk)
        extract_pdf_document.si(
            pks=list(chunk),
            check_if_needed=False,
            model_name="search.TexasDocument",
        ).set(queue=extraction_queue).apply_async()
        logger.info(
            "Scheduled %s/%s (%s)",
            processed_count,
            total_count,
            f"{processed_count / total_count:.0%}",
        )
        time.sleep(delay)
    logger.info(
        "Done. Scheduled %s, skipped %s (over %s pages).",
        processed_count,
        skipped_count,
        page_limit,
    )


def download_texas_documents(
    download_queue: str,
    delay: float,
    download_order: str = "asc",
    auto_resume: bool = False,
) -> None:
    """Download PDFs for TexasDocument instances missing a local file.

    Queries TexasDocument instances that have no filepath_local, then
    schedules a download task for each.

    :param download_queue: The celery queue for download tasks.
    :param delay: Seconds to sleep between scheduling tasks.
    :param download_order: Sort order for the queryset by pk ("asc" or "desc").
    :param auto_resume: Resume from last pk stored in Redis.
    :return: None
    """
    desc = download_order == "desc"
    docs = TexasDocument.objects.filter(filepath_local="").values_list(
        "pk", flat=True
    )

    if auto_resume:
        last_pk = get_last_parent_document_id_processed(compose_redis_key())
        if last_pk:
            logger.info("Auto-resuming from pk %s.", last_pk)
            if desc:
                docs = docs.filter(pk__lt=last_pk)
            else:
                docs = docs.filter(pk__gt=last_pk)

    count = docs.count()
    logger.info("Found %s TexasDocuments needing download.", count)
    throttle = CeleryThrottle(queue_name=download_queue)
    processed_count = 0
    for pk in paginate_docs_queryset(docs, desc=desc):
        throttle.maybe_wait()
        download_texas_document_pdf_unthrottled.si(pk).set(
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
            log_last_document_indexed(pk, compose_redis_key())
        time.sleep(delay)
    logger.info(
        "Scheduled %s/%s",
        processed_count,
        count,
    )


class Command(VerboseCommand):
    help = (
        "Download and extract PDFs for TexasDocument instances. "
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
            "--batch-size",
            type=int,
            default=10,
            help="The batch size for PDF extraction tasks "
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
        parser.add_argument(
            "--download-order",
            type=str,
            choices=["asc", "desc"],
            default="asc",
            help="Sort order for downloading documents by pk (default: asc).",
        )
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            default=False,
            help="Resume from last pk stored in Redis.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        delay = options["delay"]

        if options["only_extraction"]:
            batch_size = options["batch_size"]
            page_limit = options["page_limit"]
            extraction_queue = options["extraction_queue"]
            logger.info(
                "Extracting TexasDocument PDFs (page limit: %s).",
                page_limit,
            )
            extract_texas_documents(
                extraction_queue, batch_size, delay, page_limit
            )
        else:
            download_queue = options["download_queue"]
            logger.info("Downloading TexasDocument PDFs.")
            download_order = options["download_order"]
            auto_resume = options["auto_resume"]
            download_texas_documents(
                download_queue, delay, download_order, auto_resume
            )
