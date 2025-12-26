from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def honeypot_equals(val: str) -> bool:
    """
    Default verifier used if HONEYPOT_VERIFIER is not specified.
    Ensures val == HONEYPOT_VALUE or HONEYPOT_VALUE() if it's a callable.
    """
    expected = getattr(settings, "HONEYPOT_VALUE", "")
    if callable(expected):
        expected = expected()
    return val == expected


HONEYPOT_FIELD_NAME = "skip_me_if_alive"


def verify_honeypot_value(request: HttpRequest) -> HttpResponse | None:
    """
    Verify that request.POST[HONEYPOT_FIELD_NAME] is a valid honeypot.

    Ensures that the field exists and passes verification according to
    HONEYPOT_VERIFIER.
    """
    verifier = getattr(settings, "HONEYPOT_VERIFIER", honeypot_equals)
    if request.method == "POST":
        if HONEYPOT_FIELD_NAME not in request.POST or not verifier(
            request.POST[HONEYPOT_FIELD_NAME]
        ):
            return render(
                request,
                "honeypot_error.html",
                {"fieldname": HONEYPOT_FIELD_NAME},
                status=400,
            )
    return None


def check_honeypot(
    func: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """Decorator to check request.POST for valid honeypot field."""

    @wraps(func)
    def wrapper(
        request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponse:
        if response := verify_honeypot_value(request):
            return response
        return func(request, *args, **kwargs)

    return wrapper
