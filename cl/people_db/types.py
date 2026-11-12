"""Types for attorney role data."""

from datetime import date
from typing import TypedDict


class RoleType(TypedDict, total=False):
    """An attorney's role, with the date of the role's action and its raw text."""

    role: int | None
    date_action: date | None
    role_raw: str
