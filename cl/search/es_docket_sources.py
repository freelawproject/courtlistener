from dataclasses import dataclass

from django.db import models

from cl.search.models import RECAPDocument, SCOTUSDocument

# The document models an ESDocketSource can index.
type SourceDocument = RECAPDocument | SCOTUSDocument


@dataclass(frozen=True)
class ESDocketSource:
    """Describes how one docket source's documents are identified in the
    RECAP Elasticsearch index.

    ``document_model`` is the Django model indexed into ESRECAPDocument
    for this source (e.g. RECAPDocument).

    ``child_id_property`` is the name of the ``ES_CHILD_ID`` property
    (in cl.search.documents) that generates this source's document ES
    _id. Each source needs its own prefix -- two sources sharing one
    could generate the same _id for different pks and silently overwrite
    each other's document.

    ``uid_namespace`` prefixes the searchable ``uid`` and
    ``docket_entry_uid`` fields of this source's documents (e.g. "scotus"
    gives "scotus_123"). None for RECAP, whose documents keep the integer
    ``id`` and ``docket_entry_id`` fields instead.
    """

    document_model: type[models.Model]
    child_id_property: str
    uid_namespace: str | None = None


RECAP_ES_SOURCE = ESDocketSource(
    document_model=RECAPDocument,
    child_id_property="RECAP",
)
SCOTUS_ES_SOURCE = ESDocketSource(
    document_model=SCOTUSDocument,
    child_id_property="SCOTUS",
    uid_namespace="scotus",
)

# Every known source, used wherever the shared code needs to loop over all
# of them uniformly.
ALL_ES_SOURCES: tuple[ESDocketSource, ...] = (
    RECAP_ES_SOURCE,
    SCOTUS_ES_SOURCE,
)

# Every document model mapped back to its source, so a caller with only a
# model TYPE on hand can recover the rest of that source's configuration.
SOURCE_BY_MODEL: dict[type[models.Model], ESDocketSource] = {
    source.document_model: source for source in ALL_ES_SOURCES
}
