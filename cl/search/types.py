from typing import Any, Type, Union

from elasticsearch_dsl.response import Hit

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.people_db.models import Education, Person, Position
from cl.search.documents import (
    AudioDocument,
    AudioPercolator,
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
]

ESDocumentInstanceType = Union[
    AudioDocument,
    ParentheticalGroupDocument,
    AudioPercolator,
    PersonDocument,
    PositionDocument,
]

ESDocumentClassType = Union[
    Type[AudioDocument],
    Type[ParentheticalGroupDocument],
    Type[AudioPercolator],
]


ESDictDocument = dict[str, Any]

PercolatorResponseType = tuple[list[Hit], ESDictDocument]

SaveDocumentResponseType = tuple[str, ESDictDocument]

SearchAlertHitType = tuple[Alert, str, list[ESDictDocument], int]
