import logging
from pathlib import Path, PurePosixPath
from typing import IO, Self

from asgiref.sync import async_to_sync
from django.core.files import File
from django.db import models
from django.utils.text import slugify

from cl.lib.decorators import document_model
from cl.lib.models import AbstractPDF
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

    url = models.URLField(max_length=250)
    processing_error = models.SmallIntegerField(
        choices=ProcessingError.CHOICES,
        null=True,
        blank=True,
    )

    @classmethod
    def state_pdf_path(
        cls,
        state_code: str,
        court_id: str,
        filename: str,
        thumbs: bool = False,
    ) -> str:
        """Build the S3 path for a state court document.

        Every state scraper stores its documents under the same layout, so
        subclasses' `get_pdf_path` implementations delegate here rather than
        each repeating it:

            us/state/<state_code>/<court_id>/gov.<state_code>.<court_id>.<slug><ext>

        Thumbnails go in a `<court_id>-thumbnails` sibling directory so they
        cannot collide with the document they were generated from.

        Callers pass `court_id` rather than reading it off the document because
        each model reaches its court by a different relation.

        :param state_code: The two-letter USPS code for the state, lowercased.
        :param court_id: The ID of the court the document was filed in.
        :param filename: The filename Django hands to the `upload_to` callback.
        :param thumbs: Whether to return the thumbnail path instead.
        :return: The path to store the document at, relative to the bucket
            root.
        """
        slug = slugify(Path(filename).stem)
        # Court-PASS serves oral argument playlists alongside PDFs, and TAMES
        # serves .html and .wpd, so the original extension has to survive.
        ext = Path(filename).suffix or ".pdf"
        directory = f"{court_id}-thumbnails" if thumbs else court_id
        return str(
            Path("us/state")
            / state_code
            / directory
            / f"gov.{state_code}.{court_id}.{slug}{ext}"
        )

    def make_filename(self) -> str:
        """Create the filename to store this document's content under (no extension)."""
        return str(hash(self.url))

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

    def extract(self, queue: str = "celery") -> None:
        """Run the OCR extraction task for this document.

        :param queue: The queue to use for the extraction task."""
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
            return

        if not self.filepath_local.name:
            logger.info(
                "No document to extract for %s %s (empty filepath_local.name)",
                self._meta.label,
                self.pk,
            )
            return

        extension = PurePosixPath(self.filepath_local.name).suffix

        if extension not in self.extractable_extensions():
            logger.info(
                "%s %s cannot be extracted (%s)",
                self._meta.label,
                self.pk,
                self.filepath_local.name,
            )
            return

        strip_html = extension != ".pdf"

        extract_formatted_text_document.si(
            pks=self.pk,
            check_if_needed=False,
            model_name=self._meta.label,
            strip_html_tags=strip_html,
        ).set(queue=queue).apply_async()

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
            elif extension not in cls.extractable_extensions():
                document.ocr_status = cls.OCR_UNNECESSARY

            document.save()

            if extract:
                document.extract(queue)

            return document

    class Meta:
        abstract = True
