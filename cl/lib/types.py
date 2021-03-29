from django.http import HttpRequest

from cl.users.models import User


class AuthenticatedHttpRequest(HttpRequest):
    user: User
