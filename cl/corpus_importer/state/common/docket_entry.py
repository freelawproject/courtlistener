"""Shared transforms for merging scraped docket entries and their documents.

A reusable base ``DocketEntryMerger``/``DocumentMerger`` can't be defined yet:
each state stores entries and documents in its own model, and ``Merger``
subclasses must name a concrete ``model`` at class-definition time (specs are
validated against it as the class is created). Until the merger abstraction
supports model-less/abstract bases, states share the transforms below instead.
"""

from collections.abc import Sequence
from typing import Any, cast

from juriscraper.state.docket import DocketEntry as ScrapeDocketEntry
from juriscraper.state.docket import Document as ScrapeDocument

from cl.search.state.shared import DocketEntryType


def _entry_type(entry: ScrapeDocketEntry[Any], params: Any) -> int:
    """Map Juriscraper's `DocketEntryType` enum to CL's integer mirror."""
    return cast(int, getattr(DocketEntryType, entry.entry_type.name))


def _entry_attachments[DocType: ScrapeDocument](
    entry: ScrapeDocketEntry[DocType], params: Any
) -> Sequence[DocType]:
    return entry.attachments


def _document_url(document: ScrapeDocument, params: Any) -> str:
    return document.url
