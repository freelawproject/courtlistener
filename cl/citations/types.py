"""Types for matching citations and the citation lookup API."""

from enum import Enum, auto
from typing import Literal, NotRequired, TypedDict

from django.db.models import QuerySet
from eyecite.models import (
    FullCaseCitation,
    IdCitation,
    ShortCaseCitation,
    SupraCitation,
)

from cl.search.models import Opinion, OpinionCluster

SupportedCitationType = (
    FullCaseCitation | ShortCaseCitation | SupraCitation | IdCitation
)


class UnmatchedResource(Enum):
    """Placeholder resources for citations that did not resolve to exactly one opinion."""

    NO_MATCH = auto()
    MULTIPLE_MATCHES = auto()


type MatchedResourceType = (
    Opinion
    | Literal[UnmatchedResource.NO_MATCH, UnmatchedResource.MULTIPLE_MATCHES]
)
ResolvedFullCite = tuple[FullCaseCitation, MatchedResourceType]
ResolvedFullCites = list[ResolvedFullCite]


class CitationAPIResponse(TypedDict):
    """The lookup result for one citation in the citation lookup API."""

    status: int
    normalized_citations: NotRequired[list[str]]
    error_message: NotRequired[str]
    clusters: NotRequired[QuerySet[OpinionCluster]]
