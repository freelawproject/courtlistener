from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal, Type, Union

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

ESModelType = Union[
    Citation,
    Docket,
    Opinion,
    OpinionCluster,
    Parenthetical,
    ParentheticalGroup,
    Audio,
    Person,
    Position,
    Education,
    RECAPDocument,
]

ESModelClassType = Union[
    Type[Citation],
    Type[Docket],
    Type[DocketEntry],
    Type[Opinion],
    Type[OpinionCluster],
    Type[Parenthetical],
    Type[ParentheticalGroup],
    Type[Audio],
    Type[Person],
    Type[Position],
    Type[Education],
    Type[RECAPDocument],
    Type[ESRECAPBaseDocument],
]

ESDocumentInstanceType = Union[
    AudioDocument,
    ParentheticalGroupDocument,
    AudioPercolator,
    PersonDocument,
    PositionDocument,
    ESRECAPDocument,
    OpinionDocument,
    OpinionClusterDocument,
]

ESDocumentClassType = Union[
    Type[AudioDocument],
    Type[ParentheticalGroupDocument],
    Type[AudioPercolator],
    Type[PersonDocument],
    Type[PositionDocument],
    Type[DocketDocument],
    Type[OpinionDocument],
    Type[OpinionClusterDocument],
    Type[ESRECAPDocument],
]

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

# TODO: Remove after scheduled OA alerts have been processed.
PercolatorResponseType = tuple[list[Hit], ESDictDocument]


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


# TODO: Remove after scheduled OA alerts have been processed.
SaveDocumentResponseType = tuple[str, ESDictDocument]


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
