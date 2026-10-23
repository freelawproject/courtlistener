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

    ``metadata_model`` is the optional docket-level metadata model whose
    changes should cascade to the Docket (and its documents) in ES (e.g.
    BankruptcyInformation for RECAP, ScotusDocketMetadata for SCOTUS).
    """

    docket_entries_related_name: str
    document_model: type[models.Model]
    child_id_property: str
    docket_belongs: Callable[[Docket], bool]
    metadata_model: type[models.Model] | None = None


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
    docket_belongs=lambda docket: docket.court_id == "scotus",
    metadata_model=ScotusDocketMetadata,
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
