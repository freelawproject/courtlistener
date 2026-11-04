from collections.abc import Callable
from functools import wraps
from typing import overload

from django.conf import settings
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from cl.lib.types import DjangoViewType


def honeypot_equals(val):
    """
    Default verifier used if HONEYPOT_VERIFIER is not specified.
    Ensures val == HONEYPOT_VALUE or HONEYPOT_VALUE() if it's a callable.
    """
    expected = getattr(settings, "HONEYPOT_VALUE", "")
    if callable(expected):
        expected = expected()
    return val == expected


def verify_honeypot_value(request, field_name):
    """
    Verify that request.POST[field_name] is a valid honeypot.

    Ensures that the field exists and passes verification according to
    HONEYPOT_VERIFIER.
    """
    verifier = getattr(settings, "HONEYPOT_VERIFIER", honeypot_equals)
    if request.method == "POST":
        field = field_name or settings.HONEYPOT_FIELD_NAME
        if field not in request.POST or not verifier(request.POST[field]):
            return render(
                request,
                "honeypot_error.html",
                {"fieldname": field},
                status=400,
            )


@overload
def check_honeypot[
    **P,
    Request: HttpRequest,
    Response: HttpResponse,
](
    func: DjangoViewType[P, Request, Response], /, field_name: str | None = ...
) -> DjangoViewType[P, Request, HttpResponse]: ...
@overload
def check_honeypot[
    **P,
    Request: HttpRequest,
    Response: HttpResponse,
](
    func: None = ..., /, field_name: str | None = ...
) -> Callable[
    [DjangoViewType[P, Request, Response]],
    DjangoViewType[P, Request, HttpResponse],
]: ...
def check_honeypot[
    **P,
    Request: HttpRequest,
    Response: HttpResponse,
](
    func: DjangoViewType[P, Request, Response] | None = None,
    /,
    field_name: str | None = None,
) -> (
    DjangoViewType[P, Request, HttpResponse]
    | Callable[
        [DjangoViewType[P, Request, Response]],
        DjangoViewType[P, Request, HttpResponse],
    ]
):
    """
    Check request.POST for valid honeypot field.

    Takes an optional field_name that defaults to HONEYPOT_FIELD_NAME if
    not specified.
    """

    def decorated(
        func: DjangoViewType[P, Request, Response],
    ) -> DjangoViewType[P, Request, HttpResponse]:
        @wraps(func)
        def inner(
            request: Request, *args: P.args, **kwargs: P.kwargs
        ) -> HttpResponse:
            response = verify_honeypot_value(request, field_name)
            if response:
                return response
            else:
                return func(request, *args, **kwargs)

        return inner

    if func is None:

        def decorator(
            func: DjangoViewType[P, Request, Response],
        ) -> DjangoViewType[P, Request, HttpResponse]:
            return decorated(func)

        return decorator
    return decorated(func)
