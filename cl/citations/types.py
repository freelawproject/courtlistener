from typing import List, Tuple, Union

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
ResolvedFullCite = Tuple[FullCaseCitation, MatchedResourceType]
ResolvedFullCites = List[ResolvedFullCite]
