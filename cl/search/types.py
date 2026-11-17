"""Types for search models, Elasticsearch documents, and alert percolation."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from elasticsearch.dsl.response import Hit, Response
from elasticsearch.dsl.utils import AttrList

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.people_db.models import Education, Person, Position
from cl.search.documents import (
    AudioDocument,
    AudioPercolator,
    DocketDocument,
    ESRECAPBaseDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    ParentheticalGroupDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.models import (
    Citation,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    Parenthetical,
    ParentheticalGroup,
    RECAPDocument,
    SCOTUSDocument,
)

type ESModelType = (
    Citation
    | Docket
    | DocketEntry
    | Opinion
    | OpinionCluster
    | Parenthetical
    | ParentheticalGroup
    | Audio
    | Person
    | Position
    | Education
    | RECAPDocument
    | SCOTUSDocument
)

type ESDocumentType = (
    AudioDocument
    | ParentheticalGroupDocument
    | AudioPercolator
    | PersonDocument
    | PositionDocument
    | DocketDocument
    | OpinionDocument
    | OpinionClusterDocument
    | ESRECAPDocument
    | ESRECAPBaseDocument
)

type ESDocumentNameType = Literal[
    "AudioDocument",
    "ParentheticalGroupDocument",
    "AudioPercolator",
    "PersonDocument",
    "PositionDocument",
    "DocketDocument",
    "OpinionDocument",
    "OpinionClusterDocument",
    "ESRECAPDocument",
    "ESRECAPBaseDocument",
]

type ESDictDocument = dict[str, Any]


# Apart from utility, this function ensures that types and names match
def get_es_document_name_for_type(d: ESDocumentType) -> ESDocumentNameType:
    """Get the class name of an Elasticsearch document."""
    match d:
        case AudioDocument():
            return "AudioDocument"
        case ParentheticalGroupDocument():
            return "ParentheticalGroupDocument"
        case AudioPercolator():
            return "AudioPercolator"
        case PersonDocument():
            return "PersonDocument"
        case PositionDocument():
            return "PositionDocument"
        case DocketDocument():
            return "DocketDocument"
        case OpinionDocument():
            return "OpinionDocument"
        case OpinionClusterDocument():
            return "OpinionClusterDocument"
        case ESRECAPDocument():
            return "ESRECAPDocument"
        case ESRECAPBaseDocument():
            return "ESRECAPBaseDocument"


# Apart from utility, this function ensures that types and names match
def get_es_document_type_for_name(
    d: ESDocumentNameType,
) -> type[ESDocumentType]:
    """Get the Elasticsearch document class with the given name."""
    match d:
        case "AudioDocument":
            return AudioDocument
        case "ParentheticalGroupDocument":
            return ParentheticalGroupDocument
        case "AudioPercolator":
            return AudioPercolator
        case "PersonDocument":
            return PersonDocument
        case "PositionDocument":
            return PositionDocument
        case "DocketDocument":
            return DocketDocument
        case "OpinionDocument":
            return OpinionDocument
        case "OpinionClusterDocument":
            return OpinionClusterDocument
        case "ESRECAPDocument":
            return ESRECAPDocument
        case "ESRECAPBaseDocument":
            return ESRECAPBaseDocument


@dataclass
class SendAlertsResponse:
    """The alerts a document triggered, with the document's content and model."""

    main_alerts_triggered: list[Hit]
    rd_alerts_triggered: list[Hit]
    d_alerts_triggered: list[Hit]
    document_content: ESDictDocument
    app_label_model: str


@dataclass
class PercolatorResponses:
    """Percolator query responses for a document and, optionally, its RECAP document and docket alerts."""

    main_response: Response
    rd_response: Response | None
    d_response: Response | None


@dataclass
class SaveESDocumentReturn:
    """A saved document's ID, content, and app label."""

    document_id: str
    document_content: ESDictDocument
    app_label: str


type SearchAlertHitType = tuple[Alert, str, list[ESDictDocument], int]


class EventTable(StrEnum):
    """The model labels of tables whose events trigger re-indexing, plus an empty ``UNDEFINED`` value."""

    DOCKET = "search.Docket"
    DOCKET_ENTRY = "search.DocketEntry"
    RECAP_DOCUMENT = "search.RECAPDocument"
    UNDEFINED = ""


@dataclass(frozen=True)
class ESCursor:
    """The state of an Elasticsearch cursor pagination request."""

    search_after: AttrList | None
    reverse: bool
    search_type: str
    request_date: date | None
    page_int: int
