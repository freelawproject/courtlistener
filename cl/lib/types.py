from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, NotRequired, TypedDict, Union

from django.http import HttpRequest

from cl.users.models import User

CleanData = Dict[str, Any]
TaskData = Dict[str, Any]


class AuthenticatedHttpRequest(HttpRequest):
    user: User


class EmailType(TypedDict, total=False):
    subject: str
    body: str
    from_email: str
    to: List[str]


class ESRangeQueryParams(TypedDict):
    gte: str | int | float
    lte: str | int | float
    relation: NotRequired[str]


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


"""
The following classes provide a homogeneous collection of variables
as a reusable group. The goal of these classes is to work as
containers of the data thats coming from a Position queryset.

- The BasePositionMapping class contains the smallest set of common
fields that we use in the UI and we need in the API response.

- the ApiPositionMapping class inherits the attributes from the base
class and define new API-specific attributes.

when adding a new attribute to one of those classes, we need to make
sure the type of the new field is defaultdict[int, list[str]].

These classes contain an internal variable called __db_to_dataclass_map,
this mapping is used to define which fields should be included in each
container of the dataclass. This variable must be a nested dict where
the the first-level keys should point to fields in the Position model that
needs to be checked before adding data to the class, each of these keys
should have another dictionary as its value. The inner dictionary should
use name of fields or query relationships of the Position Model as keys
and the name of the dataclass attribute as its value. Here are some
examples:

if we have the following if-statement:

    if position.how_selected:
        map.selection_method_dict[person_pk].append(
            position.get_how_selected_display()
            )

We can represent it in the __db_to_dataclass_map variable like this:

    "how_selected": {
        "get_how_selected_display": "selection_method_dict",
    },

where the first-level key is 'how_selected' because the the if-statement was
checking that field before appending the value of the 'get_how_selected_display'
method to the 'selection_method_dict' attribute.

We can even use lookups that span relationships, for example:

    if position.appointer:
        map.appointer_dict[person_pk].append(
            position.appointer.person.name_full_reverse
        )

can be represented as:

    "appointer": {
        "appointer__person__name_full_reverse": "appointer_dict"
    },

"""


@dataclass
class BasePositionMapping:
    court_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    court_exact_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    appointer_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    selection_method_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    selection_method_id_dict: defaultdict[int, list[int]] = field(
        default_factory=lambda: defaultdict(list)
    )
    supervisor_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    predecessor_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    __db_to_dataclass_map = {
        "court": {
            "court__short_name": "court_dict",
            "court__pk": "court_exact_dict",
        },
        "appointer": {
            "appointer__person__name_full_reverse": "appointer_dict"
        },
        "how_selected": {
            "get_how_selected_display": "selection_method_dict",
            "how_selected": "selection_method_id_dict",
        },
        "supervisor": {"supervisor__name_full_reverse": "supervisor_dict"},
        "predecessor": {"predecessor__name_full_reverse": "predecessor_dict"},
    }

    def get_db_to_dataclass_map(self):
        return self.__db_to_dataclass_map


@dataclass
class ApiPositionMapping(BasePositionMapping):
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
    termination_reason_dict: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    __db_to_dataclass_map = {
        "position_type": {
            "get_position_type_display": "position_type_dict",
        },
        "date_nominated": {"date_nominated": "date_nominated_dict"},
        "date_elected": {"date_elected": "date_elected_dict"},
        "date_recess_appointment": {
            "date_recess_appointment": "date_recess_appointment_dict"
        },
        "date_referred_to_judicial_committee": {
            "date_referred_to_judicial_committee": "date_referred_to_judicial_committee_dict"
        },
        "date_judicial_committee_action": {
            "date_judicial_committee_action": "date_judicial_committee_action_dict"
        },
        "date_hearing": {"date_hearing": "date_hearing_dict"},
        "date_confirmation": {"date_confirmation": "date_confirmation_dict"},
        "date_start": {"date_start": "date_start_dict"},
        "date_granularity_start": {
            "date_granularity_start": "date_granularity_start_dict"
        },
        "date_retirement": {"date_retirement": "date_retirement_dict"},
        "date_termination": {"date_termination": "date_termination_dict"},
        "date_granularity_termination": {
            "date_granularity_termination": "date_granularity_termination_dict"
        },
        "judicial_committee_action": {
            "get_judicial_committee_action_display": "judicial_committee_action_dict"
        },
        "nomination_process": {
            "get_nomination_process_display": "nomination_process_dict"
        },
        "termination_reason": {
            "get_termination_reason_display": "termination_reason_dict"
        },
    }

    def get_db_to_dataclass_map(self):
        parent_map = super().get_db_to_dataclass_map()
        return parent_map | self.__db_to_dataclass_map
