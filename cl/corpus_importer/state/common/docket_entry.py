"""Base mergers for scraped docket entries and their documents.

Each state stores entries and documents in its own model, so these bases
leave ``model`` (and ``key``) to their concrete subclasses, which also
declare any state-specific fields and the attachment relation (its name and
target model are per-state).
"""

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, cast

from django.db.models import Model
from juriscraper.state.docket import DocketEntry as ScrapeDocketEntry
from juriscraper.state.docket import Document as ScrapeDocument

from cl.corpus_importer.state.merger import (
    Attribute,
    ManyStrategy,
    Merger,
    OneToManyRelation,
    RelatedParams,
    overwrite,
)
from cl.search.state.shared import DocketEntryType


def _entry_type(entry: ScrapeDocketEntry[Any], params: Any) -> int:
    """Map Juriscraper's `DocketEntryType` enum to CL's integer mirror."""
    return cast(int, getattr(DocketEntryType, entry.entry_type.name))


def _entry_date_filed(entry: ScrapeDocketEntry[Any], params: Any) -> date:
    return entry.date_filed


def _entry_attachments[DocType: ScrapeDocument](
    entry: ScrapeDocketEntry[DocType], params: Any
) -> Sequence[DocType]:
    return entry.attachments


def _document_url(document: ScrapeDocument, params: Any) -> str:
    return document.url


class DocumentMerger[DocType: ScrapeDocument, ParamType, M: Model](
    Merger[DocType, RelatedParams[ParamType], M], abstract=True
):
    url: str = Attribute(_document_url, strategy=overwrite)


def AttachmentRelation(
    merger: type[Merger[Any, Any, Any]] = DocumentMerger,
    *,
    transform: Callable[[Any, Any], Any] = _entry_attachments,
    strategy: ManyStrategy = ManyStrategy.APPEND,
) -> list[Any]:
    return OneToManyRelation(
        merger,
        transform,
        strategy=strategy,
    )


class DocketEntryMerger[
    EntryType: ScrapeDocketEntry[Any],
    ParamType,
    M: Model,
](Merger[EntryType, RelatedParams[ParamType], M], abstract=True):
    date_filed: date = Attribute(_entry_date_filed, strategy=overwrite)
    entry_type: int = Attribute(_entry_type, strategy=overwrite)
    documents: list[Any] = AttachmentRelation()
