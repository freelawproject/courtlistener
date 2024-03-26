from typing import NotRequired, TypedDict, Union

from django.db.models import QuerySet
from eyecite.models import (
    FullCaseCitation,
    IdCitation,
    Resource,
    ShortCaseCitation,
    SupraCitation,
)

from cl.search.models import Opinion, OpinionCluster

SupportedCitationType = Union[
    FullCaseCitation, ShortCaseCitation, SupraCitation, IdCitation
]
MatchedResourceType = Union[Opinion, Resource]
ResolvedFullCite = tuple[FullCaseCitation, MatchedResourceType]
ResolvedFullCites = list[ResolvedFullCite]


class CitationAPIResponse(TypedDict):
    status: int
    error_message: NotRequired[str]
    clusters: NotRequired[QuerySet[OpinionCluster]]
