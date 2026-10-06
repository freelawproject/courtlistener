import logging
from datetime import date, datetime
from http import HTTPStatus
from pathlib import Path, PurePosixPath
from typing import IO, TYPE_CHECKING, Any, Self

import requests
from asgiref.sync import async_to_sync
from django.core.files import File
from django.db import models
from django.db.models import Q, QuerySet

from cl.lib.decorators import document_model
from cl.lib.models import AbstractPDF
from cl.lib.recap_utils import format_path_date, make_recap_style_path
from cl.lib.types import NonEmptyTuple

logger = logging.getLogger(__name__)


class DocketEntryType:
    """
    Represents the type of docket entries. Mirror of Juriscraper `DocketEntryType` enum.
    """

    UNKNOWN = 0
    """A docket entry whose type cannot be determined."""
    BRIEF = 1
    """Brief entry type"""
    DISPOSITION = 2
    """Disposition entry type"""
    EVENT = 3
    """Event entry type"""
    LETTER = 4
    """Letter entry type"""
    MOTION = 5
    """Motion entry type"""
    NOTICE = 6
    """Notice entry type"""
    ORDER = 7
    """Order entry type"""
    PETITION = 8
    """Petition entry type"""
    UNASSIGNED = 9
    """Unassigned entry type. Indicates parser needs to be updated."""

    CHOICES = (
        (UNKNOWN, "Unknown"),
        (BRIEF, "Brief"),
        (DISPOSITION, "Disposition"),
        (EVENT, "Event"),
        (LETTER, "Letter"),
        (MOTION, "Motion"),
        (NOTICE, "Notice"),
        (ORDER, "Order"),
        (PETITION, "Petition"),
        (UNASSIGNED, "Unassigned"),
    )


class ProcessingError:
    BAD_URL = 1
    EXTRACTION_FAILURE = 2
    SEALED = 3
    CHOICES = (
        (BAD_URL, "Bad URL"),
        (EXTRACTION_FAILURE, "Extraction Failure"),
        (SEALED, "Sealed"),
    )


@document_model
class AbstractStateDocument(AbstractPDF):
    """
    :ivar processing_error: The processing error for the document, if any."""

    if TYPE_CHECKING:
        # Every state document points at its state's docket entry model, so
        # the FK is declared on each subclass; this only tells the type
        # checker it exists.
        docket_entry: Any

    url = models.URLField(max_length=250)
    processing_error = models.SmallIntegerField(
        choices=ProcessingError.CHOICES,
        null=True,
        blank=True,
    )

    def build_url(self) -> str | None:
        """Build a URL to fetch the appropriate document from the court website.

        The default implementation returns the `url` column unchanged, but it can be overridden for states like Florida that
        require a proof-of-work token to fetch documents. Returns `None`, after logging why, if we failed to construct a URL
        and therefore shouldn't attempt downloading anything. Overrides may also raise; `download` logs the error itself in
        that case and skips the document either way."""

        return self.url

    def path_date_filed(self) -> date | None:
        """The filing date used in this document's storage path.

        Defaults to the docket entry's `date_filed`. States whose entries
        store timestamps rather than dates override this to pick the court's
        local calendar day.
        """
        return self.docket_entry.date_filed

    def get_pdf_path(self, filename: str, thumbs: bool = False) -> str:
        """Build the S3 path for a state court document in the RECAP layout.

        Every state's documents are filed this way, so this satisfies
        `AbstractPDF.get_pdf_path` for all of them rather than each model
        repeating it.

        State documents have no PACER document numbers, so the document's own
        pk identifies it within the docket, and the CourtListener docket id
        stands in for the PACER case id:

            recap/gov.uscourts.<court_id>.<docket_id>/gov.uscourts.<court_id>.<docket_id>.<date_filed>.<pk><ext>

        The filing date comes from `path_date_filed`, rendered as `undated`
        when missing. Only the extension of `filename` survives, since state
        scrapers serve several formats (TAMES .html/.wpd/.mp3, ACIS .tiff).

        :param filename: The filename Django hands to the `upload_to` callback.
        :param thumbs: Whether to return the thumbnail path instead.
        :return: The path to store the document at, relative to the bucket
            root.
        :raises ValueError: If the document hasn't been saved yet; its pk is
            part of the name.
        """
        if self.pk is None:
            raise ValueError(
                f"{type(self).__name__} must be saved before a file can be "
                "stored for it; its pk is part of the storage path."
            )
        docket = self.docket_entry.docket
        return make_recap_style_path(
            docket.court_id,
            docket.pk,
            [format_path_date(self.path_date_filed()), str(self.pk)],
            Path(filename).suffix or ".pdf",
            thumbs=thumbs,
        )

    @classmethod
    def tmp_prefix(cls) -> str:
        """Prefix for the temporary file name to save downloads with."""
        return "tmp_"

    @classmethod
    def expected_extensions(cls) -> NonEmptyTuple[str]:
        """Return the set of expected file extensions for this document."""
        return (".pdf",)

    @classmethod
    def extractable_extensions(cls) -> NonEmptyTuple[str]:
        """Return the set of file extensions that can be extracted."""
        return (".pdf",)

    @classmethod
    def written_since(cls, since: datetime) -> QuerySet[Self]:
        """Documents of this model written since `since` that carry no
        extracted text.

        :param since: The moment to count from.
        :return: The documents still missing their text.
        """
        extensions = Q()
        for extension in cls.extractable_extensions():
            extensions |= Q(filepath_local__endswith=extension)
        return (
            cls._default_manager.filter(extensions, date_modified__gte=since)
            .exclude(filepath_local="")
            .exclude(ocr_status__in=(cls.OCR_COMPLETE, cls.OCR_UNNECESSARY))
        )

    @classmethod
    def unextracted(cls, since: datetime) -> QuerySet[Self]:
        """Documents that have not been OCRed but have been modified
        since provided datetime.

        :param since: The moment to count from.
        :return: The documents nothing has yet tried and failed to read.
        """
        return cls.written_since(since).exclude(ocr_status=cls.OCR_FAILED)

    def validate_file(self, content: IO[bytes], extension: str) -> int | None:
        """Validate the file content and return the processing error if any.

        :param content: The file content to validate.
        :param extension: The file extension of the content."""

        return None

    async def fetch_page_count(self) -> int | None:
        """Fetch the page count of the document."""
        from cl.lib.microservice_utils import doc_page_count_service

        response = await doc_page_count_service(self)
        if response.is_success:
            return int(response.text)
        return None

    def extract(self, queue: str = "celery") -> bool:
        """Run the OCR extraction task for this document.

        :param queue: The queue to use for the extraction task.
        :return: True if dispatch occured, else False."""
        from cl.scrapers.tasks import extract_formatted_text_document

        if (
            self.ocr_status == self.OCR_UNNECESSARY
            or self.ocr_status == self.OCR_COMPLETE
        ):
            logger.info(
                "OCR extraction unnecessary for %s %s (%s)",
                self._meta.label,
                self.pk,
                self.ocr_status,
            )
            return False

        if not self.filepath_local.name:
            logger.info(
                "No document to extract for %s %s (empty filepath_local.name)",
                self._meta.label,
                self.pk,
            )
            return False

        extension = PurePosixPath(self.filepath_local.name).suffix

        if extension not in self.extractable_extensions():
            logger.info(
                "%s %s cannot be extracted (%s)",
                self._meta.label,
                self.pk,
                self.filepath_local.name,
            )
            return False

        strip_html = extension != ".pdf"

        extract_formatted_text_document.si(
            pks=self.pk,
            check_if_needed=False,
            model_name=self._meta.label,
            strip_html_tags=strip_html,
        ).set(queue=queue).apply_async()
        return True

    @classmethod
    def download(
        cls, pk: int, extract: bool = True, queue: str = "celery"
    ) -> Self | None:
        """Download the document from the URL, save it to a local file. Returns the document if download was
        successful and `None` otherwise.

        :param pk: The primary key of the document to download.
        :param extract: Whether to extract the document after downloading.
        :param queue: The queue to use for the extraction task."""
        # Imported here to avoid a circular import: this module is loaded with
        # cl.search.models, which the task modules import.
        from cl.corpus_importer.tasks import download_document_in_stream

        try:
            # The document's storage path is built from its docket, so fetch
            # that with it rather than going back for it a query at a time.
            document = cls._default_manager.select_related(
                "docket_entry__docket"
            ).get(pk=pk)
        except cls.DoesNotExist:
            logger.warning(
                "Document download: %s %s does not exist; skipping.",
                cls.__name__,
                pk,
            )
            return None

        if document.processing_error == ProcessingError.BAD_URL:
            logger.warning(
                "Document download: %s %s has a bad URL. Skipping.",
                cls.__name__,
                pk,
            )
            return None

        # A URL that can't be built is a per-document problem, so it must
        # not take down the task that's working through a batch.
        try:
            url = document.build_url()
        except Exception:
            logger.exception("Failed to build URL for %s %s", cls.__name__, pk)
            return None
        if url is None:
            return None

        logger.info(
            "Document download: Fetching document for %s %s from %s",
            cls.__name__,
            pk,
            url,
        )

        try:
            with download_document_in_stream(
                url, pk, cls.tmp_prefix(), require_pdf=False
            ) as result:
                return cls._store_download(
                    document, url, result, extract, queue
                )
        except requests.HTTPError as exc:
            # A refusal gets its own message, without a traceback: a 5xx is
            # the court having a bad day, a 403 is the court turning us away.
            if exc.response.status_code == HTTPStatus.FORBIDDEN:
                logger.error(
                    "Court refused %s %s at %s (403)",
                    cls.__name__,
                    pk,
                    exc.request.url,
                )
            else:
                logger.exception(
                    "Failed to fetch %s %s from %s",
                    cls.__name__,
                    pk,
                    exc.request.url,
                )
            return None

    @classmethod
    def _store_download(
        cls,
        document: Self,
        url: str,
        result: tuple[IO[bytes], str] | None,
        extract: bool,
        queue: str,
    ) -> Self | None:
        """Validate a downloaded file and save it onto `document`. Returns the
        document on success and `None` if there was nothing to store or the
        file was rejected.

        :param document: The document the file belongs to.
        :param url: The URL the file was fetched from, for logging.
        :param result: The temporary file and its SHA-1 as yielded by
            `download_document_in_stream`, or `None` if the download failed.
        :param extract: Whether to dispatch text extraction after saving.
        :param queue: The queue to use for the extraction task."""
        # Imported here to avoid a circular import; see `download`.
        from cl.scrapers.utils import get_extension

        pk = document.pk
        if result is None:
            logger.error(
                "Failed to download document for %s %s from URL %s.",
                cls.__name__,
                pk,
                url,
            )
            return None

        tmp, sha1_hash = result
        content = tmp.read(8192)
        tmp.seek(0)

        extension = get_extension(content)

        if extension not in cls.expected_extensions():
            logger.warning(
                "Document download: Unexpected extension '%s' for %s %s from %s. Proceeding anyway.",
                extension,
                cls.__name__,
                pk,
                url,
            )

        if error := document.validate_file(tmp, extension):
            document.processing_error = error
            document.save()
            return None

        # `get_pdf_path` names the file from the document itself and keeps
        # only this name's extension, so the stem is never stored.
        filename = f"document{extension}"
        downloaded_file = File(tmp)
        document.filepath_local.save(filename, downloaded_file, save=False)
        document.file_size = downloaded_file.size
        document.sha1 = sha1_hash

        if extension == ".pdf":
            if pages := async_to_sync(document.fetch_page_count)():
                document.page_count = pages
        elif extension not in cls.extractable_extensions():
            document.ocr_status = cls.OCR_UNNECESSARY

        document.save()

        if extract:
            document.extract(queue)

        return document

    class Meta:
        abstract = True
