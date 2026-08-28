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
    """Shape of a single item in a metadata description list. Rendered by
    both the c-metadata-section cotton component and
    includes/metadata_section.html.

    is_copyable/has_tooltip/tooltip_message are flags + plain content,
    -- each stack decides its own concrete styling/mechanism.
    tooltip_message may contain HTML; the caller must mark_safe it.
    """

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
    is_copyable: NotRequired[bool]
    has_tooltip: NotRequired[bool]
    tooltip_message: NotRequired[str]


class MetadataSection(TypedDict):
    """Shape of one rendered metadata section. Rendered by both the
    c-metadata-section cotton component and includes/metadata_section.html.
    A section with no items renders nothing, so callers MAY return empty
    sections rather than filtering them out."""

    items: list[MetadataItem]
    title: NotRequired[str]


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


def _always_has_actions(document: Any) -> bool:
    """Return True: by default every document gets its action buttons."""
    return True


def _no_metadata_items(docket: Docket) -> list[MetadataItem]:
    """Return no items: by default a source adds nothing to the core
    docket metadata block."""
    return []


def _no_metadata_sections(docket: Docket) -> list[MetadataSection]:
    """Return no sections: by default a source adds no metadata sections
    of its own."""
    return []


@dataclass(frozen=True)
class DocketEntrySource:
    """Describes how to fetch, sort, and display docket entries for one
    'flavor' of docket. RECAP/PACER is the default; SCOTUS is the first
    override. A future state-specific model plugs in by adding one more
    instance and a court_id mapping below -- view_docket itself doesn't
    need to change.

    ``component`` picks which file renders this source's copy. Both
    template stacks hold one file per component: under cotton/, the
    docket_source_button/, docket_source_attribution/ and
    document_source_link/ folders; under includes/, those three plus
    docket_empty_message/, docket_empty_cta/ and docket_source_li/. A
    source named "xyz" needs xyz.html in every
    folder of both stacks. A missing one fails at render time with an
    error that doesn't name it, so DocketSourceComponentTest checks that
    every component resolves. Sources that render the same copy MAY share
    a component instead of copying files.

    ``document_detail_url`` returns a CourtListener path that we build
    ourselves, or None. docket_entry_rows.html renders it unfiltered into
    an ``href``, so a source MUST NOT return an externally sourced URL
    from it.

    ``document_external_url`` points outside CourtListener, so its scheme
    MUST be guaranteed by us: either build the URL from a hardcoded
    prefix, as ``RECAPDocument.pacer_url`` does, or filter it through
    ``http_url``, as ``_scotus_document_external_url`` does. A source MUST
    NOT return a raw third-party string.

    ``metadata_items`` returns items appended to the core docket metadata
    block, so they render as part of that block with no heading or visual
    division (e.g. the SCOTUS docket metadata). ``metadata_sections``
    returns standalone titled sections rendered after the common ones
    (e.g. RECAP's Bankruptcy Information).

    ``docket_url`` returns the docket's page on the source's own site, or
    None when the source has no page for it. core_docket_data() resolves
    it once into the ``docket_source_url`` context variable, which gates
    the docket toolbar in docket_tabs.html -- gating on
    ``docket.pacer_docket_url`` there would hide the toolbar for every
    non-PACER source.

    Every callable below touches the ORM, so callers in async views MUST
    wrap them in ``sync_to_async``.
    """

    entries_queryset: Callable[[Docket], QuerySet]
    documents_for_entry: Callable[[Any], Iterable]
    order_by_asc: tuple[str, ...]
    order_by_desc: tuple[str, ...]
    document_is_attachment: Callable[[Any], bool]
    document_label: Callable[[Any], str]
    document_detail_url: Callable[[Any], str | None]
    document_external_url: Callable[[Any], str | None]
    docket_url: Callable[[Docket], str | None]
    component: str
    has_pay_and_pray: bool = True
    document_has_actions: Callable[[Any], bool] = _always_has_actions
    metadata_items: Callable[[Docket], list[MetadataItem]] = _no_metadata_items
    metadata_sections: Callable[[Docket], list[MetadataSection]] = (
        _no_metadata_sections
    )


def attach_display_fields(source: DocketEntrySource, document: Any) -> None:
    """Resolve one document's display fields from its source, in place."""
    document.is_attachment = source.document_is_attachment(document)
    document.label = source.document_label(document)
    document.detail_url = source.document_detail_url(document)
    document.external_url = source.document_external_url(document)
    document.has_actions = source.document_has_actions(document)


# RECAP


def _recap_entries(docket: Docket) -> QuerySet:
    return docket.docket_entries.all().prefetch_related(
        Prefetch(
            "recap_documents",
            queryset=RECAPDocument.objects.defer("plain_text"),
        )
    )


def _recap_documents_for_entry(de: DocketEntry) -> QuerySet:
    return de.recap_documents.all()


def _recap_docket_url(docket: Docket) -> str | None:
    """Return the docket's PACER docket report URL, or None."""
    return docket.pacer_docket_url


def _recap_document_is_attachment(document: RECAPDocument) -> bool:
    """Return whether one RECAP document is an attachment (vs. the main
    document) within its entry."""
    return document.document_type == document.ATTACHMENT


def _recap_document_label(document: RECAPDocument) -> str:
    """Return the label identifying one RECAP document within its entry."""
    if document.document_type == RECAPDocument.ATTACHMENT:
        return f"Attachment {document.attachment_number}"
    return "Main Document"


def _recap_document_detail_url(document: RECAPDocument) -> str | None:
    """Return the URL of the CourtListener page for one RECAP document, or
    None if we don't have the file yet."""
    if not document.filepath_local:
        return None
    # Numberless minute entries have no URL of their own; get_absolute_url
    # returns an empty string for them.
    return document.get_absolute_url() or None


def _recap_document_external_url(document: RECAPDocument) -> str | None:
    """Return the PACER URL for one RECAP document, or None if it has
    none."""
    return document.pacer_url or None


def _recap_document_has_actions(document: RECAPDocument) -> bool:
    """Return whether one RECAP document gets action buttons.

    Numberless minute entries are not individually addressable on PACER, so
    there is nothing to download, buy or pray for. Legacy hides the whole
    action area for them; see the `{# Hide this if an unnumbered minute
    entry #}` guard in includes/de_list.html.
    """
    return bool(document.document_number)


def _recap_metadata_sections(docket: Docket) -> list[MetadataSection]:
    """Build the metadata sections specific to a RECAP/PACER docket."""
    # Imported here rather than at module scope because cl.opinion_page.utils
    # imports from this module.
    from cl.opinion_page.utils import build_bankruptcy_metadata

    bankr_info = getattr(docket, "bankruptcy_information", None)
    return [
        {
            "items": build_bankruptcy_metadata(bankr_info),
            "title": "Bankruptcy Information",
        },
    ]


RECAP_SOURCE = DocketEntrySource(
    entries_queryset=_recap_entries,
    documents_for_entry=_recap_documents_for_entry,
    order_by_asc=("recap_sequence_number", "entry_number"),
    order_by_desc=("-recap_sequence_number", "-entry_number"),
    document_is_attachment=_recap_document_is_attachment,
    document_label=_recap_document_label,
    document_detail_url=_recap_document_detail_url,
    document_external_url=_recap_document_external_url,
    document_has_actions=_recap_document_has_actions,
    docket_url=_recap_docket_url,
    metadata_sections=_recap_metadata_sections,
    component="recap",
)


# SCOTUS
def _scotus_entries(docket: Docket) -> QuerySet:
    return docket.scotusdocketentry_set.all().prefetch_related(
        Prefetch(
            "scotusdocument_set",
            queryset=SCOTUSDocument.objects.defer("plain_text"),
        )
    )


def _scotus_documents_for_entry(de: SCOTUSDocketEntry) -> QuerySet:
    return de.scotusdocument_set.all()


def _scotus_document_is_attachment(document: SCOTUSDocument) -> bool:
    """Return True always: SCOTUSDocument has no "main document" concept,
    every SCOTUS document is an attachment."""
    return True


def _scotus_document_label(document: SCOTUSDocument) -> str:
    """Return the label identifying one SCOTUS document within its entry.

    SCOTUSDocument has no "main document" concept: every SCOTUS document is
    an attachment. The scrapers always set attachment_number, but guard
    against a null one so a stray row can't render as "Attachment None".
    """
    if document.attachment_number is None:
        return "Attachment"
    return f"Attachment {document.attachment_number}"


def _scotus_document_detail_url(document: SCOTUSDocument) -> str | None:
    """Return None: SCOTUS documents have no CourtListener page in either
    design yet.

    When that page exists, returning its URL here is all it takes for the
    docket entry templates to start linking SCOTUS document labels.
    """
    return None


def _scotus_document_external_url(document: SCOTUSDocument) -> str | None:
    """Return the supremecourt.gov URL for one SCOTUS document, or None.

    The URL comes from the court rather than from us, so it is filtered
    through http_url before being handed to a template.
    """
    return http_url(document.url) or None


def _scotus_metadata_items(docket: Docket) -> list[MetadataItem]:
    """Build the SCOTUS-specific items appended to the core docket
    metadata, so they render inside that block rather than as a section
    of their own."""
    return build_scotus_metadata(getattr(docket, "scotus_metadata", None))


def _scotus_docket_url(docket: Docket) -> str | None:
    """Return the docket's page on supremecourt.gov, or None when the
    docket has no docket_number to build it from."""
    return docket.scotus_docket_url or None


SCOTUS_SOURCE = DocketEntrySource(
    entries_queryset=_scotus_entries,
    documents_for_entry=_scotus_documents_for_entry,
    order_by_asc=("sequence_number",),
    order_by_desc=("-sequence_number",),
    document_is_attachment=_scotus_document_is_attachment,
    document_label=_scotus_document_label,
    document_detail_url=_scotus_document_detail_url,
    document_external_url=_scotus_document_external_url,
    docket_url=_scotus_docket_url,
    metadata_items=_scotus_metadata_items,
    has_pay_and_pray=False,
    component="scotus",
)

_SOURCES_BY_COURT_ID: dict[str, DocketEntrySource] = {"scotus": SCOTUS_SOURCE}
