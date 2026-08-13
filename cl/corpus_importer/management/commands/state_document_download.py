"""Command and utilities to download state docket entry attachments."""

import time
from itertools import batched
from typing import Literal

from django.apps import apps
from django.core.management import CommandParser
from django.core.management.base import CommandError
from django.db.models import Q

from cl.corpus_importer.tasks import download_state_document
from cl.corpus_importer.utils import paginate_docs_queryset
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.scrapers.tasks import extract_formatted_text_document
from cl.search.state.shared import AbstractStateDocument


def compose_redis_key(model: type[AbstractStateDocument]) -> str:
    """Compose a Redis key for state document download log.
    :return: A Redis key as a string.
    """
    return f"{model.__name__}_download:log"


def extract_state_documents(
    model: type[AbstractStateDocument],
    throttle_min_items: int,
    extraction_queue: str,
    batch_size: int,
    delay: float,
    page_limit: int,
) -> None:
    """Run the extraction task for state document instances needing extraction.

    Queries state document instances that already have a filepath_local but
    whose OCR status is not complete or unnecessary. MP3 files are excluded
    since they cannot be text-extracted. Non-PDF documents (HTML, WPD) are
    extracted with strip_html_tags=True so that plain_text contains plain
    text rather than markup. Documents with a page_count exceeding
    page_limit are skipped, allowing smaller documents to be processed first.

    :param model: The state document model to extract.
    :param throttle_min_items: CeleryThrottle min_items parameter.
    :param extraction_queue: The celery queue for extraction tasks.
    :param batch_size: The batch size for extraction tasks.
    :param delay: Seconds to sleep between scheduling tasks.
    :param page_limit: Skip documents with more pages than this value.
    :return: None
    """
    extension_query = Q()
    if not model.extractable_extensions():
        raise TypeError(
            f"{model.__name__} returned no extractable extensions."
        )
    for extension in model.extractable_extensions():
        extension_query |= Q(filepath_local__endswith=f"{extension}")
    base_query = (
        model.objects.exclude(
            filepath_local="",
        )
        .exclude(
            ocr_status__in=(model.OCR_UNNECESSARY, model.OCR_COMPLETE),
        )
        .filter(extension_query)
        .values_list("pk", flat=True)
    )

    unfiltered_count = base_query.count()

    base_query = base_query.filter(
        Q(page_count__lte=page_limit) | Q(page_count__isnull=True)
    )

    pdf_docs = base_query.filter(filepath_local__endswith=".pdf")
    non_pdf_docs = base_query.exclude(filepath_local__endswith=".pdf")

    pdf_count = pdf_docs.count()
    non_pdf_count = non_pdf_docs.count()
    total_count = pdf_count + non_pdf_count
    logger.info(
        "Found %d %s needing extraction (%d PDF, %d other).",
        total_count,
        model.__name__,
        pdf_count,
        non_pdf_count,
    )

    processed_count = 0
    throttle = CeleryThrottle(
        min_items=throttle_min_items, queue_name=extraction_queue
    )
    for docs, strip_html in [(non_pdf_docs, True), (pdf_docs, False)]:
        for chunk in batched(paginate_docs_queryset(docs), batch_size):
            throttle.maybe_wait()
            processed_count += len(chunk)
            extract_formatted_text_document.si(
                pks=list(chunk),
                check_if_needed=False,
                model_name=model._meta.label,
                strip_html_tags=strip_html,
            ).set(queue=extraction_queue).apply_async()
            logger.info(
                "Scheduled %d/%d (%s)",
                processed_count,
                total_count,
                f"{processed_count / total_count:.0%}",
            )
            time.sleep(delay)
    logger.info(
        "Done. Scheduled %d, skipped %d (over %d pages).",
        processed_count,
        unfiltered_count - total_count,
        page_limit,
    )


def download_state_documents(
    model: type[AbstractStateDocument],
    throttle_min_items: int,
    download_queue: str,
    extraction_queue: str,
    delay: float,
    download_order: Literal["asc", "desc"],
    skip_extraction: bool,
    auto_resume: bool,
) -> None:
    """Download documents for state document instances missing a local file.

    Queries state document instances that have no filepath_local, then
    schedules a download task for each.

    :param model: The state document model to download.
    :param throttle_min_items: CeleryThrottle min_items parameter.
    :param download_queue: The celery queue for download tasks.
    :param extraction_queue: The celery queue for extraction tasks.
    :param delay: Seconds to sleep between scheduling tasks.
    :param download_order: Sort order for the queryset by pk ("asc" or "desc").
    :param skip_extraction: Skip the extraction step.
    :param auto_resume: Resume from last pk stored in Redis.
    :return: None
    """
    desc = download_order == "desc"
    docs = model.objects.filter(
        filepath_local="", processing_error__isnull=True
    ).values_list("pk", flat=True)

    if auto_resume:
        last_pk = get_last_parent_document_id_processed(
            compose_redis_key(model)
        )
        if last_pk:
            logger.info("Auto-resuming from pk %s.", last_pk)
            if desc:
                docs = docs.filter(pk__lt=last_pk)
            else:
                docs = docs.filter(pk__gt=last_pk)

    count = docs.count()
    logger.info("Found %s %s needing download.", count, model.__name__)
    processed_count = 0
    throttle = CeleryThrottle(
        min_items=throttle_min_items, queue_name=download_queue
    )
    for pk in paginate_docs_queryset(docs, desc=desc):
        throttle.maybe_wait()
        download_state_document.si(
            model._meta.label, pk, skip_extraction, extraction_queue
        ).set(queue=download_queue).apply_async()
        processed_count += 1
        if processed_count % 100 == 0:
            logger.info(
                "Scheduled %s/%s (%s)",
                processed_count,
                count,
                f"{processed_count / count:.0%}",
            )
            log_last_document_indexed(pk, compose_redis_key(model))
        time.sleep(delay)
    logger.info(
        "Scheduled %s/%s",
        processed_count,
        count,
    )


class Command(VerboseCommand):
    """Command to download state docket entry attachments."""

    help = "Download state docket entry attachments."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--model",
            type=str,
            help="The model to download (app_label.ModelName).",
            required=True,
        )
        parser.add_argument(
            "--download-queue",
            type=str,
            help="The celery queue to use for downloads.",
            default="celery",
        )
        parser.add_argument(
            "--extraction-queue",
            type=str,
            help="The celery queue to use for OCR extraction.",
            default="celery",
        )
        parser.add_argument(
            "--throttle-min-items",
            type=int,
            default=5,
            help="CeleryThrottle min_items parameter.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Seconds to sleep between scheduling tasks.",
        )
        parser.add_argument(
            "--skip-extraction",
            action="store_true",
            default=False,
            help="Skip the extraction step.",
        )
        parser.add_argument(
            "--skip-download",
            action="store_true",
            default=False,
            help="Skip the download step.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=10,
            help="The batch size for PDF extraction tasks "
            "(only used when skipping downloads).",
        )
        parser.add_argument(
            "--page-limit",
            type=int,
            default=50,
            help="Skip documents with more pages than this value "
            "(only used when skipping downloads).",
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

    def handle(
        self,
        *args,
        model: str,
        download_queue: str,
        extraction_queue: str,
        throttle_min_items: int,
        delay: float,
        skip_extraction: bool,
        skip_download: bool,
        batch_size: int,
        page_limit: int,
        download_order: Literal["asc", "desc"],
        auto_resume: bool,
        **options,
    ) -> None:
        """Download state docket entry attachments.

        :param model: The model to download (app_label.ModelName).
        :param download_queue: The celery queue to use for downloads.
        :param extraction_queue: The celery queue to use for OCR extraction.
        :param throttle_min_items: CeleryThrottle min_items parameter.
        :param delay: Seconds to sleep between scheduling tasks.
        :param skip_extraction: Skip the text extraction step.
        :param skip_download: Skip the download step.
        :param batch_size: The batch size for PDF extraction tasks.
        :param page_limit: Skip documents with more pages than this value.
        :param download_order: Sort order for downloading documents by pk.
        :param auto_resume: Resume from last pk stored in Redis."""
        super().handle(*args, **options)
        if skip_extraction and skip_download:
            logger.info("Nothing to do.")
            return
        model_cls = apps.get_model(model)
        if not issubclass(model_cls, AbstractStateDocument):
            raise CommandError(
                f"Model {model} must be an AbstractStateDocument subclass."
            )
        if skip_download:
            extract_state_documents(
                model_cls,
                throttle_min_items,
                extraction_queue,
                batch_size,
                delay,
                page_limit,
            )
        else:
            download_state_documents(
                model_cls,
                throttle_min_items,
                download_queue,
                extraction_queue,
                delay,
                download_order,
                skip_extraction,
                auto_resume,
            )
