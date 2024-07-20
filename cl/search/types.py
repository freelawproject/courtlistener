from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal, Type, Union

from elasticsearch_dsl.response import Hit
from elasticsearch_dsl.utils import AttrList

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.people_db.models import Education, Person, Position
from cl.search.documents import (
    AudioDocument,
    AudioPercolator,
    DocketDocument,
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

PercolatorResponseType = tuple[
    list[Hit], list[Hit], list[Hit], ESDictDocument, str
]

SaveDocumentResponseType = tuple[str, ESDictDocument, str]

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
