from typing import NotRequired, TypedDict

from cl.people_db.types import RoleType


class RECAPCriminalComplaint(TypedDict):
    name: str
    disposition: str


class RECAPCriminalCount(TypedDict):
    name: str
    disposition: str
    status: str


class RECAPAttorneyDict(TypedDict):
    contact: str
    name: str
    roles: list[str] | list[RoleType]


class RECAPCriminalDataDict(TypedDict):
    highest_offense_level_opening: str
    highest_offense_level_terminated: str
    counts: list[RECAPCriminalCount]
    complaints: list[RECAPCriminalComplaint]


class RECAPPartyDict(TypedDict):
    name: str
    type: str
    date_terminated: NotRequired[str]
    extra_info: NotRequired[str]
    criminal_data: NotRequired[RECAPCriminalDataDict]
    attorneys: NotRequired[list[RECAPAttorneyDict]]
