from typing import Any, Callable, Dict, List, Tuple, TypedDict, Union

from django.http import HttpRequest
from eyecite.models import (
    FullCaseCitation,
    IdCitation,
    Resource,
    ShortCaseCitation,
    SupraCitation,
)

from cl.search.models import Opinion
from cl.users.models import User

CleanData = Dict[str, Any]
TaskData = Dict[str, Any]

SupportedCitationType = Union[
    FullCaseCitation, ShortCaseCitation, SupraCitation, IdCitation
]
MatchedResourceType = Union[Opinion, Resource]
ResolvedFullCite = Tuple[FullCaseCitation, MatchedResourceType]
ResolvedFullCites = List[ResolvedFullCite]


class AuthenticatedHttpRequest(HttpRequest):
    user: User


class EmailType(TypedDict, total=False):
    subject: str
    body: str
    from_email: str
    to: List[str]


# fmt: off
SearchParam = TypedDict(
    "SearchParam",
    {
        "q": str,
        "fq": List[str],
        "mm": int,

        # Pagination & ordering
        "rows": int,
        "sort": str,

        # Faceting
        "facet": str,
        "facet.field": str,
        "facet.mincount": int,
        "facet.range": str,
        "facet.range.start": str,
        "facet.range.end": str,
        "facet.range.gap": str,

        # Highlighting
        "hl": str,
        "hl.fl": str,
        "fl": str,
        "f.text.hl.snippets": str,
        "f.text.hl.maxAlternateFieldLength": str,
        "f.text.hl.alternateField": str,

        # Grouping
        "group": str,
        "group.ngroups": str,
        "group.limit": int,
        "group.field": str,
        "group.sort": str,

        # Boosting
        "boost": str,
        "qf": str,
        "pf": str,
        "ps": Union[float, str],

        # More Like This
        "mlt": str,
        "mlt.fl": str,
        "mlt.maxqt": int,
        "mlt.mintf": int,
        "mlt.minwl": int,
        "mlt.maxwl": int,
        "mlt.maxdf": int,

        "caller": str,
    },
    total=False,
)
# fmt: on


OptionsType = Dict[str, Union[str, Callable]]
