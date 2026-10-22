"""Per-source configuration for the shared Elasticsearch signal-processing
machinery in cl.lib.es_signal_processor and the ES indexing tasks in
cl.search.tasks.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.db import models

from cl.search.models import (
    BankruptcyInformation,
    Docket,
    RECAPDocument,
    ScotusDocketMetadata,
    SCOTUSDocument,
)


@dataclass(frozen=True)
class ESDocketSource:
    """Describes how one docket source's RECAP-style content (docket
    entries, documents, and an optional docket-level metadata model) plugs
    into the shared Elasticsearch signal-processing code.

    ``docket_entries_related_name`` is the attribute on Docket that
    reaches this source's entries (e.g. ``docket_entries`` for RECAP).

    ``document_model`` is the Django model indexed into ESRECAPDocument
    for this source (e.g. RECAPDocument).

    ``child_id_property`` is the name of the ``ES_CHILD_ID`` property
    (in cl.search.documents) that generates this source's document ES
    _id. Each source needs its own prefix -- two sources sharing one
    could generate the same _id for different pks and silently overwrite
    each other's document.

    ``docket_belongs`` decides whether a given Docket is this source's.

    ``ready_to_index`` decides whether there's enough data to index the
    Docket's own fields right now. Defaults to always-ready.

    ``metadata_model`` is the optional docket-level metadata model whose
    changes should cascade to the Docket (and its documents) in ES (e.g.
    BankruptcyInformation for RECAP, ScotusDocketMetadata for SCOTUS).
    """

    docket_entries_related_name: str
    document_model: type[models.Model]
    child_id_property: str
    docket_belongs: Callable[[Docket], bool]
    metadata_model: type[models.Model] | None = None
    ready_to_index: Callable[[Docket], bool] = lambda docket: True


def _scotus_docket_belongs(docket: Docket) -> bool:
    """True for a court_id="scotus" Docket that is real SCOTUS content,
    not one created only to hold a scraped Opinion. merge_scotus_docket
    uses the same source=SCRAPER value cl_scrape_opinions sets for every
    scraped Opinion, so source alone can't tell the two apart.

    True if the Docket was explicitly marked at save time
    (merge_scotus_docket sets `docket._index_in_es` before its first
    save), or if it already has a ScotusDocketMetadata row.
    ScotusDocketMetadata is what keeps the Docket belonging on every
    save after the first.
    """
    if docket.court_id != "scotus":
        return False
    return (
        getattr(docket, "_index_in_es", False)
        or getattr(docket, "scotus_metadata", None) is not None
    )


def _scotus_ready_to_index(docket: Docket) -> bool:
    """True once the Docket has a ScotusDocketMetadata row. capital_case
    lives there, so waiting for it means the Docket's first ES write
    already has every field, instead of an incomplete first write
    followed by a second one once the metadata arrives.
    """
    return getattr(docket, "scotus_metadata", None) is not None


RECAP_ES_SOURCE = ESDocketSource(
    docket_entries_related_name="docket_entries",
    document_model=RECAPDocument,
    child_id_property="RECAP",
    docket_belongs=lambda docket: docket.source in Docket.RECAP_SOURCES(),
    metadata_model=BankruptcyInformation,
)
SCOTUS_ES_SOURCE = ESDocketSource(
    docket_entries_related_name="scotusdocketentry_set",
    document_model=SCOTUSDocument,
    child_id_property="SCOTUS",
    docket_belongs=_scotus_docket_belongs,
    metadata_model=ScotusDocketMetadata,
    ready_to_index=_scotus_ready_to_index,
)

# Every known source, used wherever the shared code needs to loop over all
# of them uniformly.
ALL_ES_SOURCES: tuple[ESDocketSource, ...] = (
    RECAP_ES_SOURCE,
    SCOTUS_ES_SOURCE,
)

# Every model (document or metadata) belonging to a source, mapped back to
# that source -- so a caller with only a model TYPE on hand (e.g. a
# signal's `instance`) can recover the rest of that source's configuration.
SOURCE_BY_MODEL: dict[type[models.Model], ESDocketSource] = {
    **{source.document_model: source for source in ALL_ES_SOURCES},
    **{
        source.metadata_model: source
        for source in ALL_ES_SOURCES
        if source.metadata_model is not None
    },
}
