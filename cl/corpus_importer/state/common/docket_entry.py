"""Base mergers for scraped docket entries and their documents.

Each state stores entries and documents in its own model, so these bases
leave ``model`` (and ``key``) to their concrete subclasses, which also
declare any state-specific fields and the attachment relation (its name and
target model are per-state).
"""

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, cast, override

from django.db.models import Model
from juriscraper.state.docket import DocketEntry as ScrapeDocketEntry
from juriscraper.state.docket import Document as ScrapeDocument

from cl.corpus_importer.state.merger import (
    Fn,
    ManyStrategy,
    Merger,
    MergerState,
    OneToManyRelation,
    Params,
    RelatedParams,
    Scrape,
    WithStrategy,
    overwrite,
)
from cl.search.state.shared import (
    AbstractStateDocument,
    DocketEntryType,
    ProcessingError,
)


def _entry_attachments[DocType: ScrapeDocument](
    entry: ScrapeDocketEntry[DocType], params: Any
) -> Sequence[DocType]:
    return entry.attachments


class DocumentMerger[
    DocType: ScrapeDocument,
    ParamType,
    M: AbstractStateDocument,
](Merger[DocType, RelatedParams[ParamType], M], abstract=True):
    url: str = WithStrategy(Scrape(ScrapeDocument).url, overwrite)

    @override
    def needs_update(self) -> bool:
        """Force the update path for a document with no stored file and no recorded processing error -- its download failed transiently, and reporting an update gets the download re-dispatched on re-ingest."""
        if not isinstance(state := self.state, MergerState.Update):
            return False
        document = cast(AbstractStateDocument, state.instance)
        return (
            not document.filepath_local and document.processing_error is None
        )

    @override
    def pre_update(self, updated_fields: list[str]) -> list[str]:
        updated = super().pre_update(updated_fields)
        # This hook only runs on the update path; the guard narrows the type.
        if not isinstance(self.state, MergerState.Update):
            return updated
        if "url" not in updated_fields:
            return updated
        existing = cast(AbstractStateDocument, self.state.instance)
        if existing.processing_error == ProcessingError.BAD_URL:
            existing.processing_error = None
            updated.append("processing_error")
        if existing.filepath_local:
            existing.filepath_local.delete(save=False)
            updated.append("filepath_local")
        existing.filepath_local = ""
        existing.ocr_status = None
        updated.append("ocr_status")
        return updated


def AttachmentRelation(
    merger: type[Merger[Any, Any, Any]] = DocumentMerger,
    *,
    transform: Callable[[Any, Any], Any] = _entry_attachments,
    strategy: ManyStrategy = ManyStrategy.APPEND,
) -> list[Any]:
    return OneToManyRelation(
        merger,
        Fn(transform)(Scrape(Any), Params(Any)),
        strategy=strategy,
    )


class DocketEntryMerger[
    EntryType: ScrapeDocketEntry[Any],
    ParamType,
    M: Model,
](Merger[EntryType, RelatedParams[ParamType], M], abstract=True):
    date_filed: date = WithStrategy(
        Scrape(ScrapeDocketEntry).date_filed, overwrite
    )
    entry_type: int = WithStrategy(
        Fn(getattr)(
            DocketEntryType, Scrape(ScrapeDocketEntry).entry_type.name
        ),
        overwrite,
    )
    documents: list[Any] = AttachmentRelation()
