from typing import Any, Type, Union

from elasticsearch_dsl.response import Hit

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
]


ESDictDocument = dict[str, Any]

PercolatorResponseType = tuple[list[Hit], ESDictDocument]

SaveDocumentResponseType = tuple[str, ESDictDocument]

SearchAlertHitType = tuple[Alert, str, list[ESDictDocument], int]
