from typing import List, TypedDict

from django.http import HttpRequest

from cl.users.models import User


class AuthenticatedHttpRequest(HttpRequest):
    user: User


class EmailType(TypedDict, total=False):
    subject: str
    body: str
    from_email: str
    to: List[str]
