"""Per-source configuration for the shared Elasticsearch signal-processing
machinery in cl.lib.es_signal_processor and the ES indexing tasks in
cl.search.tasks.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.db import models
from django.db.models import Exists, OuterRef, Q

from cl.search.models import (
    BankruptcyInformation,
    Docket,
    RECAPDocument,
    ScotusDocketMetadata,
    SCOTUSDocument,
)

# The document models an ESDocketSource can index.
type SourceDocument = RECAPDocument | SCOTUSDocument


@dataclass(frozen=True)
class ESDocketSource:
    """Describes how one docket source's RECAP-style content (docket
    entries, documents, and an optional docket-level metadata model) plugs
    into the shared Elasticsearch signal-processing code.

    ``name`` identifies the source where a plain string is needed, e.g.
    the ``--source`` option of cl_index_parent_and_child_docs.

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

    ``docket_filter`` returns a Q selecting the saved Dockets bulk indexing
    should pick for this source, matching what the signal processor
    indexes. It's a callable because this module is imported while models
    are still loading.

    ``ready_to_index`` decides whether there's enough data to index the
    Docket's own fields right now. Defaults to always-ready.

    ``metadata_model`` is the optional docket-level metadata model whose
    changes should cascade to the Docket (and its documents) in ES (e.g.
    BankruptcyInformation for RECAP, ScotusDocketMetadata for SCOTUS).

    ``uid_namespace`` prefixes the searchable ``uid`` and
    ``docket_entry_uid`` fields of this source's documents (e.g. "scotus"
    gives "scotus_123"). None for RECAP, whose documents keep the integer
    ``id`` and ``docket_entry_id`` fields instead.

    ``court_ids`` limits the source to Dockets from these courts, so
    has_entries can rule out other courts without a query. Empty means
    any court (RECAP).
    """

    name: str
    docket_entries_related_name: str
    document_model: type[models.Model]
    child_id_property: str
    docket_belongs: Callable[[Docket], bool]
    docket_filter: Callable[[], Q]
    metadata_model: type[models.Model] | None = None
    ready_to_index: Callable[[Docket], bool] = lambda docket: True
    uid_namespace: str | None = None
    court_ids: frozenset[str] = frozenset()

    def has_entries(self, docket: Docket) -> bool:
        """Whether the Docket has any docket entries from this source.

        Dockets from a court outside ``court_ids`` return False without a
        query, so callers can check every source on each Docket save
        without an extra EXISTS query per source.
        """
        if self.court_ids and docket.court_id not in self.court_ids:
            return False
        return getattr(docket, self.docket_entries_related_name).exists()


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


def _scotus_docket_filter() -> Q:
    """Select court_id="scotus" Dockets with a ScotusDocketMetadata row or
    at least one SCOTUSDocument. _index_in_es only exists in memory, so it
    can't be matched in SQL; Dockets with a document are included because
    es_save_document indexes a document's Docket along with it when the
    Docket isn't indexed yet.
    """
    # The court filter wraps both branches so the query can use the court
    # index instead of checking every Docket.
    return Q(court_id="scotus") & (
        Q(scotus_metadata__isnull=False)
        | Q(
            Exists(
                SCOTUSDocument.objects.filter(
                    docket_entry__docket=OuterRef("pk")
                )
            )
        )
    )


def _scotus_ready_to_index(docket: Docket) -> bool:
    """True once the Docket has a ScotusDocketMetadata row. capital_case
    lives there, so waiting for it means the Docket's first ES write
    already has every field, instead of an incomplete first write
    followed by a second one once the metadata arrives.
    """
    return getattr(docket, "scotus_metadata", None) is not None


RECAP_ES_SOURCE = ESDocketSource(
    name="recap",
    docket_entries_related_name="docket_entries",
    document_model=RECAPDocument,
    child_id_property="RECAP",
    docket_belongs=lambda docket: docket.source in Docket.RECAP_SOURCES(),
    docket_filter=lambda: Q(source__in=Docket.RECAP_SOURCES()),
    metadata_model=BankruptcyInformation,
)
SCOTUS_ES_SOURCE = ESDocketSource(
    name="scotus",
    docket_entries_related_name="scotus_docket_entries",
    document_model=SCOTUSDocument,
    child_id_property="SCOTUS",
    docket_belongs=_scotus_docket_belongs,
    docket_filter=_scotus_docket_filter,
    metadata_model=ScotusDocketMetadata,
    ready_to_index=_scotus_ready_to_index,
    uid_namespace="scotus",
    court_ids=frozenset({"scotus"}),
)

# Every known source, used wherever the shared code needs to loop over all
# of them uniformly.
ALL_ES_SOURCES: tuple[ESDocketSource, ...] = (
    RECAP_ES_SOURCE,
    SCOTUS_ES_SOURCE,
)

# Each source by name, for callers that only have a string (CLI options,
# Celery task arguments).
ES_SOURCE_BY_NAME: dict[str, ESDocketSource] = {
    source.name: source for source in ALL_ES_SOURCES
}

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


def skips_percolation(instance: models.Model) -> bool:
    """True for a SCOTUS Docket, so callers must skip its percolator
    request. Temporary: remove once search alerts support SCOTUS.
    """
    return isinstance(instance, Docket) and SCOTUS_ES_SOURCE.docket_belongs(
        instance
    )
