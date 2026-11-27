"""Base mergers for scraped docket entries and their documents.

Each state stores entries and documents in its own model, so these bases
leave ``model`` (and ``match``) to their concrete subclasses, which also
declare any state-specific fields and the attachment relation (its name and
target model are per-state).
"""

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, ClassVar, override

from django.db.models import Model
from juriscraper.state.docket import DocketEntry as ScrapeDocketEntry
from juriscraper.state.docket import Document as ScrapeDocument

from cl.corpus_importer.state.merger import (
    Fn,
    ManyStrategy,
    Merger,
    MergerConfig,
    MergerState,
    OneToManyRelation,
    Params,
    RelatedParams,
    Scrape,
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
    Params,
    M: AbstractStateDocument,
](Merger[DocType, RelatedParams[Params], M], abstract=True):
    """Base merger for a scraped state document.

    When a document's URL changes, its stored file and OCR status are reset
    so it is downloaded again.
    """

    config: ClassVar[MergerConfig[AbstractStateDocument]] = MergerConfig(
        model=AbstractStateDocument,
        reads=("filepath_local", "processing_error"),
    )

    url: str = Scrape(ScrapeDocument).url

    @override
    def update(
        self, state: MergerState.Update[DocType, RelatedParams[Params], M]
    ) -> MergerState.UpdateOutput[DocType, RelatedParams[Params], M]:
        if not isinstance(
            save_state := super().update(state), MergerState.Save
        ):
            return save_state

        document = state.instance
        if not save_state.operation.fields and (
            document.filepath_local or document.processing_error is not None
        ):
            return save_state

        existing = save_state.operation.instance
        updated_fields = list(save_state.operation.fields)

        if "url" not in updated_fields:
            return state.save(
                existing, updated_fields, save_state.result, force=True
            )

        if existing.processing_error == ProcessingError.BAD_URL:
            existing.processing_error = None
            updated_fields.append("processing_error")

        if existing.filepath_local:
            existing.filepath_local.delete(save=False)
            updated_fields.append("filepath_local")

        existing.filepath_local = ""
        existing.ocr_status = None
        updated_fields.append("ocr_status")

        return state.save(existing, updated_fields, save_state.result)


def AttachmentRelation(
    merger: type[Merger[Any, Any, Any]] = DocumentMerger,
    *,
    transform: Callable[[Any, Any], Any] = _entry_attachments,
    strategy: ManyStrategy = ManyStrategy.APPEND,
) -> list[Any]:
    """Declare a docket entry's attachments as a one-to-many relation.

    Defaults to merging the scraped entry's attachments and appending them
    to the entry's existing documents.
    """
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
    """Base merger for a scraped state docket entry and its attachments."""

    date_filed: date = Scrape(ScrapeDocketEntry).date_filed
    entry_type: int = Fn(getattr)(
        DocketEntryType, Scrape(ScrapeDocketEntry).entry_type.name
    )
    documents: list[Any] = AttachmentRelation()
