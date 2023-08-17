from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass
class PositionMapping:
    court_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    appointer_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    selection_method_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    supervisor_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    predecessor_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    # API
    court_exact_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    position_type_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_nominated_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_elected_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_recess_appointment_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_referred_to_judicial_committee_dict: defaultdict[
        int, list[datetime]
    ] = field(default_factory=lambda: defaultdict(list))
    date_judicial_committee_action_dict: defaultdict[
        int, list[datetime]
    ] = field(default_factory=lambda: defaultdict(list))
    date_hearing_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_confirmation_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_start_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_granularity_start_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_retirement_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_termination_dict: defaultdict[int, list[datetime]] = field(
        default_factory=lambda: defaultdict(list)
    )
    date_granularity_termination_dict: defaultdict[
        int, list[datetime]
    ] = field(default_factory=lambda: defaultdict(list))

    judicial_committee_action_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    nomination_process_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    selection_method_id_dict: defaultdict[int, list[int]] = field(
        default_factory=lambda: defaultdict(list)
    )
    termination_reason_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
