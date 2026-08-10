import logging
from typing import IO, Self

from asgiref.sync import async_to_sync
from django.core.files import File
from django.db import models

from cl.lib.decorators import document_model
from cl.lib.models import AbstractPDF

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

    url = models.URLField(max_length=250)
    processing_error = models.SmallIntegerField(
        choices=ProcessingError.CHOICES,
        null=True,
        blank=True,
    )

    def make_filename(self) -> str:
        """Create the filename to store this document's content under (no extension)."""
        return str(hash(self.url))

    @classmethod
    def tmp_prefix(cls) -> str:
        """Prefix for the temporary file name to save downloads with."""
        return "tmp_"

    @classmethod
    def expected_extensions(cls) -> set[str]:
        """Return the set of expected file extensions for this document."""
        return set()

    def can_extract(self, extension: str) -> bool:
        """Whether this document is eligible for OCR extraction.

        :param extension: The file extension of the document."""
        return False

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

    @classmethod
    def download(cls, pk: int) -> Self | None:
        """Download the document from the URL, save it to a local file. Returns the document if download was
        successful and `None` otherwise."""
        # Imported here to avoid a circular import: this module is loaded with
        # cl.search.models, which the task modules import.
        from cl.corpus_importer.tasks import download_document_in_stream
        from cl.scrapers.tasks import extract_formatted_text_document
        from cl.scrapers.utils import get_extension

        try:
            document = cls.objects.get(pk=pk)
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

        url = document.url

        logger.info(
            "Document download: Fetching document for %s %s from %s",
            cls.__name__,
            pk,
            url,
        )

        with download_document_in_stream(
            url, pk, cls.tmp_prefix(), require_pdf=False
        ) as result:
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

            filename = f"{document.make_filename()}{extension}"
            downloaded_file = File(tmp)
            document.filepath_local.save(filename, downloaded_file, save=False)
            document.file_size = downloaded_file.size
            document.sha1 = sha1_hash

            if extension == ".pdf":
                if pages := async_to_sync(document.fetch_page_count)():
                    document.page_count = pages
            elif not document.can_extract(extension):
                document.ocr_status = cls.OCR_UNNECESSARY

            document.save()

            if document.can_extract(extension):
                extract_formatted_text_document.si(
                    pks=document.pk,
                    check_if_needed=False,
                    model_name=cls._meta.label,
                    strip_html_tags=True,
                ).apply_async()

            return document

    class Meta:
        abstract = True
