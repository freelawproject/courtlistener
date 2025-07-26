from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from elasticsearch_dsl.response import Hit, Response
from elasticsearch_dsl.utils import AttrList

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
)

ESModelType = (
    Citation
    | Docket
    | Opinion
    | OpinionCluster
    | Parenthetical
    | ParentheticalGroup
    | Audio
    | Person
    | Position
    | Education
    | RECAPDocument
)

ESModelClassType = (
    type[Citation]
    | type[Docket]
    | type[DocketEntry]
    | type[Opinion]
    | type[OpinionCluster]
    | type[Parenthetical]
    | type[ParentheticalGroup]
    | type[Audio]
    | type[Person]
    | type[Position]
    | type[Education]
    | type[RECAPDocument]
    | type[ESRECAPBaseDocument]
)

ESDocumentInstanceType = (
    AudioDocument
    | ParentheticalGroupDocument
    | AudioPercolator
    | PersonDocument
    | PositionDocument
    | ESRECAPDocument
    | OpinionDocument
    | OpinionClusterDocument
)

ESDocumentClassType = (
    type[AudioDocument]
    | type[ParentheticalGroupDocument]
    | type[AudioPercolator]
    | type[PersonDocument]
    | type[PositionDocument]
    | type[DocketDocument]
    | type[OpinionDocument]
    | type[OpinionClusterDocument]
    | type[ESRECAPDocument]
)

ESDocumentNameType = Literal[
    "AudioDocument",
    "ParentheticalGroupDocument",
    "AudioPercolator",
    "PersonDocument",
    "PositionDocument",
    "DocketDocument",
    "OpinionDocument",
    "OpinionClusterDocument",
    "ESRECAPDocument",
]

ESDictDocument = dict[str, Any]


@dataclass
class SendAlertsResponse:
    main_alerts_triggered: list[Hit]
    rd_alerts_triggered: list[Hit]
    d_alerts_triggered: list[Hit]
    document_content: ESDictDocument
    app_label_model: str


@dataclass
class PercolatorResponses:
    main_response: Response
    rd_response: Response | None
    d_response: Response | None


@dataclass
class SaveESDocumentReturn:
    document_id: str
    document_content: ESDictDocument
    app_label: str


SearchAlertHitType = tuple[Alert, str, list[ESDictDocument], int]


class EventTable(StrEnum):
    DOCKET = "search.Docket"
    DOCKET_ENTRY = "search.DocketEntry"
    RECAP_DOCUMENT = "search.RECAPDocument"
    UNDEFINED = ""


@dataclass(frozen=True)
class ESCursor:
    search_after: AttrList | None
    reverse: bool
    search_type: str
    request_date: date | None
