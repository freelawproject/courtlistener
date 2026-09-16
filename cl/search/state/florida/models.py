import base64
import hashlib
import logging
import struct
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import httpx
import pghistory
from django.db import models
from juriscraper.state.florida.scraper import FLORIDA_API_BASE
from pydantic import BaseModel, Field

from cl.lib.decorators import document_model
from cl.lib.model_helpers import CSVExportMixin
from cl.lib.models import AbstractDateTimeModel
from cl.lib.types import NonEmptyTuple
from cl.search.state.shared import (
    AbstractStateDocument,
    DocketEntryType,
)

logger = logging.getLogger(__name__)

__all__ = ["FloridaDocketEntry", "FloridaDocument"]


class AltchaData(BaseModel):
    resource: str

    def fetch(self) -> "AltchaChallenge | None":
        response = httpx.get(
            urljoin(FLORIDA_API_BASE, "/altcha/challenge"),
            params={"resource": self.resource},
            headers={"User-Agent": "Courtlistener (Free Law Project)"},
        )

        response.raise_for_status()

        if response.status_code == 204:
            return None

        return AltchaChallenge.model_validate_json(response.text)


class AltchaChallengeSolution(BaseModel):
    counter: int
    derived_key: str = Field(alias="derivedKey")
    time: float


class AltchaChallengeParameters(BaseModel):
    algorithm: str
    cost: int
    key_length: int = Field(alias="keyLength")
    key_prefix: str = Field(alias="keyPrefix")
    nonce: str
    salt: str
    expiry: int = Field(alias="expiresAt")
    data: AltchaData
    key_signature: str = Field(alias="keySignature")


MAX_ATTEMPT_TIME: float = 30.0


class AltchaChallenge(BaseModel):
    parameters: AltchaChallengeParameters
    signature: str

    def solve(self) -> AltchaChallengeSolution | None:
        if self.parameters.algorithm != "PBKDF2/SHA-256":
            raise NotImplementedError
        nonce_bytes = bytes.fromhex(self.parameters.nonce)
        salt_bytes = bytes.fromhex(self.parameters.salt)
        prefix_bytes = bytes.fromhex(self.parameters.key_prefix)
        start = time.monotonic()
        solution = None
        i = 0
        while time.monotonic() - start < MAX_ATTEMPT_TIME:
            candidate = hashlib.pbkdf2_hmac(
                "sha256",
                nonce_bytes + struct.pack(">I", i),
                salt_bytes,
                self.parameters.cost,
                self.parameters.key_length,
            )
            if candidate.startswith(prefix_bytes):
                solution = candidate
                break
            i += 1

        if solution is None:
            return None

        return AltchaChallengeSolution(
            counter=i,
            derivedKey=solution.hex(),
            time=(time.monotonic() - start) * 1_000,
        )


class AltchaChallengeResponse(BaseModel):
    challenge: AltchaChallenge
    solution: AltchaChallengeSolution

    def encode(self) -> str:
        return base64.b64encode(
            self.model_dump_json(by_alias=True).encode()
        ).decode()


@pghistory.track()
@document_model
class FloridaDocketEntry(AbstractDateTimeModel, CSVExportMixin):
    """
    Represents a docket entry in a Florida docket.

    :ivar docket: The Docket this entry is associated with.
    :ivar date_filed: The filing date indicated by Florida ACIS
    :ivar date_submitted: Pulled directly from Florida results
    :ivar entry_type: Mirror of Juriscraper `DocketEntryType` enum.
    :ivar entry_type_raw: Value of `entry_type_raw` in Juriscraper results. Pulled from Florida API with no modification.
    :ivar entry_name: Pulled directly from Florida results
    :ivar description: Pulled directly from Florida results
    :ivar submitted_by: FK to the case party that submitted this document may be null if the party cannot be found.
    :ivar submitted_by_name: The name of the party that submitted this entry.
    :ivar status: Mapped from Florida's `entry_status` field. Can be "stricken",
    "vacated", or "docketed", or "unknown".
    :ivar docket_entry_uuid: Pulled directly from Florida results
    """

    STATUS_STRICKEN = 0
    STATUS_VACATED = 1
    STATUS_DOCKETED = 2
    STATUS_UNKNOWN = 3
    STATUS_CHOICES = (
        (STATUS_STRICKEN, "Stricken"),
        (STATUS_VACATED, "Vacated"),
        (STATUS_DOCKETED, "Docketed"),
        (STATUS_UNKNOWN, "Unknown"),
    )

    docket = models.ForeignKey(
        "search.Docket",
        on_delete=models.CASCADE,
        related_name="florida_docket_entries",
    )
    date_filed = models.DateTimeField(
        null=True,
        blank=True,
    )
    date_submitted = models.DateTimeField(
        null=True,
        blank=True,
    )
    entry_type = models.SmallIntegerField(
        choices=DocketEntryType.CHOICES, default=DocketEntryType.UNKNOWN
    )
    entry_type_raw = models.TextField(blank=True)
    entry_name = models.TextField(blank=True)
    description = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        "people_db.Party",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    submitted_by_name = models.TextField(blank=True)
    status = models.SmallIntegerField(
        choices=STATUS_CHOICES, default=STATUS_UNKNOWN
    )
    docket_entry_uuid = models.UUIDField()

    class Meta:
        app_label = "search"
        ordering = ["-date_filed"]
        verbose_name_plural = "Florida Docket Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["docket_entry_uuid", "docket"],
                name="unique_docket_entry_uuid_per_docket",
            )
        ]


@pghistory.track()
@document_model
class FloridaDocument(AbstractDateTimeModel, AbstractStateDocument):
    """
    Represents an attachment to a Florida docket entry.

    :ivar docket_entry: The Docket entry this document is associated with.
    :ivar content_type: The MIME type indicated by Florida ACIS
    :ivar document_name: The name of the document in Florida ACIS
    :ivar document_type: The type of the document in Florida ACIS
    :ivar link_uuid: The attachment link UUID retrieved from Florida ACIS. Used to generate document download URL.
    :ivar url: Download URL for attachment. Derived from uuid and link_uuid. Stored for safety.
    """

    docket_entry = models.ForeignKey(
        FloridaDocketEntry,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    content_type = models.CharField(max_length=255, blank=True)
    document_name = models.TextField(blank=True)
    document_type = models.TextField(blank=True)
    link_uuid = models.UUIDField()

    def build_url(self) -> str | None:
        """Requests parameters for and computes the altcha proof-of-work token for Florida documents, returning the URL
        with the token appended."""

        scheme, netloc, path, params, query, fragment = urlparse(self.url)

        challenge = AltchaData(resource=path).fetch()
        if challenge is None:
            return self.url
        solution = challenge.solve()
        if solution is None:
            logger.error(
                "Failed to solve Florida challenge within time limit for %s",
                self.url,
            )
            return None
        token = AltchaChallengeResponse(
            challenge=challenge, solution=solution
        ).encode()

        query_dict = parse_qs(query)
        query_dict["altcha"] = [token]

        return urlunparse(
            (
                scheme,
                netloc,
                path,
                params,
                urlencode(query_dict, doseq=True),
                fragment,
            )
        )

    def make_filename(self) -> str:
        """Build the stored filename from the document name and link UUID."""
        return f"{self.document_name}-{self.link_uuid}"

    @classmethod
    def tmp_prefix(cls) -> str:
        """Prefix for temporary download files."""
        return "fl_"

    @classmethod
    def expected_extensions(cls) -> NonEmptyTuple[str]:
        """File extensions Florida ACIS is known to serve."""
        return ".pdf", ".tiff"

    @classmethod
    def extractable_extensions(cls) -> NonEmptyTuple[str]:
        """Extensions that can be sent to text extraction"""
        return (
            ".pdf",
            ".html",
            ".wpd",
            ".txt",
            ".tiff",
        )

    async def fetch_page_count(self) -> int | None:
        """Florida ACIS gives us the page count directly, so skip sending to the microservice."""
        return self.page_count

    class Meta:
        app_label = "search"
        ordering = ["link_uuid"]
        indexes = [
            models.Index(fields=["filepath_local"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["link_uuid", "docket_entry"],
                name="unique_link_uuid_per_docket_entry",
            )
        ]

    def get_pdf_path(self, filename: str, thumbs: bool = False) -> str:
        """Store Florida ACIS documents under the shared state layout."""
        return self.state_pdf_path(
            "fl", self.docket_entry.docket.court_id, filename, thumbs
        )
