from datetime import date
from typing import Optional, TypedDict


class RoleType(TypedDict, total=False):
    role: Optional[int]
    date_action: Optional[date]
    role_raw: str
