from typing import Any, Union

from elasticsearch_dsl.response import Hit

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.search.documents import (
    AudioDocument,
    AudioPercolator,
    ParentheticalGroupDocument,
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
]
ESDocumentType = Union[
    AudioDocument, ParentheticalGroupDocument, AudioPercolator
]

ESDictDocument = dict[str, Any]

PercolatorResponseType = tuple[list[Hit], ESDictDocument]

SaveDocumentResponseType = tuple[str, ESDictDocument]

SearchAlertHitType = tuple[Alert, str, list[ESDictDocument], int]
