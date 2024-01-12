from typing import Union

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
