from typing import NotRequired, TypedDict

from django.db.models import QuerySet
from eyecite.models import (
    FullCaseCitation,
    IdCitation,
    Resource,
    ShortCaseCitation,
    SupraCitation,
)

from cl.search.models import Opinion, OpinionCluster

SupportedCitationType = (
    FullCaseCitation | ShortCaseCitation | SupraCitation | IdCitation
)
type MatchedResourceType = Opinion | Resource
ResolvedFullCite = tuple[FullCaseCitation, MatchedResourceType]
ResolvedFullCites = list[ResolvedFullCite]


class CitationAPIResponse(TypedDict):
    status: int
    normalized_citations: NotRequired[list[str]]
    error_message: NotRequired[str]
    clusters: NotRequired[QuerySet[OpinionCluster, OpinionCluster]]
