from typing import Any, NotRequired, TypedDict, Union

from eyecite.models import (
    FullCaseCitation,
    IdCitation,
    Resource,
    ShortCaseCitation,
    SupraCitation,
)

from cl.search.models import Opinion

SupportedCitationType = Union[
    FullCaseCitation, ShortCaseCitation, SupraCitation, IdCitation
]
MatchedResourceType = Union[Opinion, Resource]
ResolvedFullCite = tuple[FullCaseCitation, MatchedResourceType]
ResolvedFullCites = list[ResolvedFullCite]


class CitationAPIResponse(TypedDict):
    status: int
    error_message: NotRequired[str]
    clusters: NotRequired[list[dict[str, Any]]]
