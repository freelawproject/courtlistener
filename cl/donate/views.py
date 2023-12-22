import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def payment_complete(
    request: HttpRequest,
    template_name: str,
) -> HttpResponse:
    error = None
    if len(request.GET) > 0:
        # We've gotten some information from the payment provider
        if request.GET.get("error") == "failure":
            error_msg = request.GET.get("error_description", "").lower()
            if error_msg == "user cancelled":
                error = "user_cancelled"
            elif "insufficient funds" in error_msg:
                error = "insufficient_funds"
            return render(
                request,
                "donate_complete.html",
                {"error": error, "private": True},
            )

    return render(
        request,
        template_name,
        {"error": error, "private": True},
    )
