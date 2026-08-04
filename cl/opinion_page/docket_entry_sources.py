from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from django.db.models import Prefetch, QuerySet

from cl.search.models import (
    Docket,
    DocketEntry,
    RECAPDocument,
    SCOTUSDocketEntry,
    SCOTUSDocument,
)


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
    has_docket_alerts: bool = True


def _recap_entries(docket: Docket) -> QuerySet:
    return docket.docket_entries.all().prefetch_related(
        Prefetch(
            "recap_documents",
            queryset=RECAPDocument.objects.defer("plain_text"),
        )
    )


def _scotus_entries(docket: Docket) -> QuerySet:
    return docket.scotusdocketentry_set.all().prefetch_related(
        Prefetch("scotusdocument_set", queryset=SCOTUSDocument.objects.all())
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
    has_docket_alerts=False,
)

_SOURCES_BY_COURT_ID: dict[str, DocketEntrySource] = {"scotus": SCOTUS_SOURCE}


def get_docket_entry_source(docket: Docket) -> DocketEntrySource:
    return _SOURCES_BY_COURT_ID.get(docket.court_id, RECAP_SOURCE)
