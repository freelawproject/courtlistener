import logging

from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render

from cl.donate.models import MonthlyDonation
from cl.lib.http import is_ajax

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


def toggle_monthly_donation(request: HttpRequest) -> HttpResponse:
    """Use Ajax to enable/disable monthly contributions"""
    if is_ajax(request) and request.method == "POST":
        monthly_pk = request.POST.get("id")
        m_donation = MonthlyDonation.objects.get(pk=monthly_pk)
        state = m_donation.enabled
        if state:
            m_donation.enabled = False
            msg = "Monthly contribution disabled successfully"
        else:
            m_donation.enabled = True
            msg = "Monthly contribution enabled successfully"
        m_donation.save()
        return HttpResponse(msg)
    else:
        return HttpResponseNotAllowed(
            permitted_methods={"POST"}, content="Not an Ajax POST request."
        )
