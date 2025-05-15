from datetime import date
from typing import TypedDict


class RoleType(TypedDict, total=False):
    role: int | None
    date_action: date | None
    role_raw: str
