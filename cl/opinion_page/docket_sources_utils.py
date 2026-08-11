from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from django.db.models import Prefetch, QuerySet
from django.utils.formats import date_format

from cl.custom_filters.templatetags.extras import http_url
from cl.search.models import (
    Docket,
    DocketEntry,
    RECAPDocument,
    SCOTUSDocketEntry,
    ScotusDocketMetadata,
    SCOTUSDocument,
)


class MetadataItem(TypedDict):
    """Shape of a single item in a metadata description list (see the
    c-metadata-section cotton component)."""

    label: str
    value: str
    url: NotRequired[str]
    nofollow: NotRequired[bool]
    is_external: NotRequired[bool]
    aria_label: NotRequired[str]
    suffix_text: NotRequired[str]
    suffix_url: NotRequired[str]
    suffix_nofollow: NotRequired[bool]
    suffix_is_external: NotRequired[bool]
    suffix_aria_label: NotRequired[str]


def build_scotus_metadata(
    scotus_metadata: ScotusDocketMetadata | None,
) -> list[MetadataItem]:
    """Build metadata items for the SCOTUS docket metadata section."""
    if not scotus_metadata:
        return []

    items: list[MetadataItem] = []

    if scotus_metadata.capital_case:
        items.append({"label": "Capital Case", "value": "Yes"})

    if scotus_metadata.date_discretionary_court_decision:
        items.append(
            {
                "label": "Date of Discretionary Court Decision",
                "value": date_format(
                    scotus_metadata.date_discretionary_court_decision,
                    "N j, Y",
                ),
            }
        )

    if scotus_metadata.linked_with:
        items.append(
            {"label": "Linked With", "value": scotus_metadata.linked_with}
        )

    if scotus_metadata.questions_presented_file:
        items.append(
            {
                "label": "Questions Presented",
                "value": "View",
                "url": scotus_metadata.questions_presented_file.url,
            }
        )
    elif http_url(scotus_metadata.questions_presented_url):
        items.append(
            {
                "label": "Questions Presented",
                "value": "View",
                "url": scotus_metadata.questions_presented_url,
                "is_external": True,
            }
        )

    return items


@dataclass(frozen=True)
class DocketEntrySource:
    """Describes how to fetch, sort, and display docket entries for one
    'flavor' of docket. RECAP/PACER is the default; SCOTUS is the first
    override. A future state-specific model plugs in by adding one more
    instance and a court_id mapping below -- view_docket itself doesn't
    need to change.
    """

    entries_queryset: Callable[[Docket], QuerySet]
    documents_for_entry: Callable[[Any], Iterable]
    order_by_asc: tuple[str, ...]
    order_by_desc: tuple[str, ...]
    has_pay_and_pray: bool = True


def _recap_entries(docket: Docket) -> QuerySet:
    return docket.docket_entries.all().prefetch_related(
        Prefetch(
            "recap_documents",
            queryset=RECAPDocument.objects.defer("plain_text"),
        )
    )


def _scotus_entries(docket: Docket) -> QuerySet:
    return docket.scotusdocketentry_set.all().prefetch_related(
        Prefetch(
            "scotusdocument_set",
            queryset=SCOTUSDocument.objects.defer("plain_text"),
        )
    )


def _recap_documents_for_entry(de: DocketEntry) -> QuerySet:
    return de.recap_documents.all()


def _scotus_documents_for_entry(de: SCOTUSDocketEntry) -> QuerySet:
    return de.scotusdocument_set.all()


RECAP_SOURCE = DocketEntrySource(
    entries_queryset=_recap_entries,
    documents_for_entry=_recap_documents_for_entry,
    order_by_asc=("recap_sequence_number", "entry_number"),
    order_by_desc=("-recap_sequence_number", "-entry_number"),
)

SCOTUS_SOURCE = DocketEntrySource(
    entries_queryset=_scotus_entries,
    documents_for_entry=_scotus_documents_for_entry,
    order_by_asc=("sequence_number",),
    order_by_desc=("-sequence_number",),
    has_pay_and_pray=False,
)

_SOURCES_BY_COURT_ID: dict[str, DocketEntrySource] = {"scotus": SCOTUS_SOURCE}
