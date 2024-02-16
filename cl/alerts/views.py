from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from cl.alerts.forms import DocketAlertConfirmForm
from cl.alerts.models import Alert, DocketAlert
from cl.alerts.tasks import send_unsubscription_confirmation
from cl.lib.http import is_ajax
from cl.lib.types import AuthenticatedHttpRequest
from cl.opinion_page.utils import make_docket_title, user_has_alert
from cl.search.models import Docket


@login_required
def edit_alert_redirect(request, pk):
    """Note that this method is still very useful because it gives people an
    opportunity to login if they come to the site via one of our email alerts.
    """
    # check if the user can edit this, or if they are url hacking
    alert = get_object_or_404(Alert, pk=pk, user=request.user)
    return HttpResponseRedirect(f"/?{alert.query}&edit_alert={alert.pk}")


@login_required
def delete_alert(request, pk):
    try:
        pk = int(pk)
    except ValueError:
        return HttpResponseRedirect("/")

    # check if the user can edit this, or if they are url hacking
    alert = get_object_or_404(Alert, pk=pk, user=request.user)

    # if they've made it this far, they have permission to edit the alert
    alert.delete()
    messages.add_message(
        request,
        messages.SUCCESS,
        f"Your alert <strong>{alert.name}</strong> was deleted successfully.",
    )
    return HttpResponseRedirect(reverse("profile_alerts"))


@login_required
def delete_alert_confirm(request, pk):
    return render(
        request,
        "delete_confirm.html",
        {"alert_id": pk, "private": False},
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def disable_alert(request, secret_key):
    """Disable an alert based on a secret key."""
    alert = get_object_or_404(Alert, secret_key=secret_key)
    prev_rate = alert.rate
    alert.rate = Alert.OFF
    alert.save()
    if request.method == "POST":
        return HttpResponse("You have been successfully unsubscribed!")
    return render(
        request,
        "disable_alert.html",
        {"alert": alert, "prev_rate": prev_rate, "private": True},
    )


def enable_alert(request, secret_key):
    alert = get_object_or_404(Alert, secret_key=secret_key)
    rate = request.GET.get("rate")
    if not rate:
        failed = "a rate was not provided"
    else:
        if rate not in Alert.ALL_FREQUENCIES:
            failed = "an unknown rate was provided"
        else:
            alert.rate = rate
            alert.save()
            failed = ""
    return render(
        request,
        "enable_alert.html",
        {"alert": alert, "failed": failed, "private": True},
    )


@login_required
def toggle_docket_alert(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Use Ajax to create or delete an alert for a user."""

    # This could be removed and replaced using the docket-alert API.
    if request.user.is_anonymous:
        return HttpResponse("Please log in to continue.")

    if is_ajax(request) and request.method == "POST":
        docket_pk = request.POST.get("id")
        if not docket_pk:
            msg = "Unable to alter alert. Please provide ID attribute"
            return HttpResponse(msg)
        existing_alert = DocketAlert.objects.filter(
            user=request.user,
            docket_id=docket_pk,
        )
        if existing_alert.exists():
            if existing_alert[0].alert_type == DocketAlert.SUBSCRIPTION:
                # Use save() to force date_created to be updated
                da_alert = existing_alert[0]
                da_alert.alert_type = DocketAlert.UNSUBSCRIPTION
                da_alert.save()
                msg = "Alert disabled successfully"
            else:
                # Use save() to force date_created to be updated
                da_alert = existing_alert[0]
                da_alert.alert_type = DocketAlert.SUBSCRIPTION
                da_alert.save()
                msg = "Alerts are now enabled for this docket"
        else:
            DocketAlert.objects.create(docket_id=docket_pk, user=request.user)
            msg = "Alerts are now enabled for this docket"

        return HttpResponse(msg)
    else:
        return HttpResponseNotAllowed(
            permitted_methods={"POST"}, content="Not an ajax POST request."
        )


async def new_docket_alert(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Allow users to create docket alerts based on case and court ID"""
    pacer_case_id = request.GET.get("pacer_case_id")
    court_id = request.GET.get("court_id")
    if not pacer_case_id or not court_id:
        return TemplateResponse(
            request,
            "docket_alert_new.html",
            {
                "docket": None,
                "title": "400: Invalid request creating docket alert",
                "private": True,
            },
            status=HTTP_400_BAD_REQUEST,
        )
    try:
        docket = await Docket.objects.aget(
            pacer_case_id=pacer_case_id, court_id=court_id
        )
    except Docket.DoesNotExist:
        return TemplateResponse(
            request,
            "docket_alert_new.html",
            {
                "docket": None,
                "title": "New Docket Alert for Unknown Case",
                "private": True,
            },
            status=HTTP_404_NOT_FOUND,
        )
    except Docket.MultipleObjectsReturned:
        docket = await Docket.objects.filter(
            pacer_case_id=pacer_case_id, court_id=court_id
        ).aearliest("date_created")

    title = f"New Docket Alert for {make_docket_title(docket)}"
    has_alert = await user_has_alert(await request.auser(), docket)  # type: ignore[attr-defined]
    return TemplateResponse(
        request,
        "docket_alert_new.html",
        {
            "title": title,
            "has_alert": has_alert,
            "docket": docket,
            "private": True,
        },
    )


def set_docket_alert_state(
    docket_alert: DocketAlert, target_state: int
) -> None:
    """Flip the alert_type for a docket alert.

    :param docket_alert: The docket alert to flip.
    :param target_state: The new alert_type to set.
    """
    # Only flip the alert_type if it's not already the same
    if docket_alert.alert_type == target_state:
        return

    docket_alert.alert_type = target_state
    docket_alert.save()
    if target_state == DocketAlert.UNSUBSCRIPTION:
        # Send Unsubscription confirmation email to the user
        send_unsubscription_confirmation.delay(docket_alert.pk)


def toggle_docket_alert_confirmation(
    request: HttpRequest,
    route_prefix: str,
    secret_key: str,
) -> HttpResponse:
    """Show a confirmation or success page for toggling docket alerts.

    :param request: The HttpRequest from the client
    :param route_prefix: The route prefix, unsubscribe or subscribe
    :param secret_key: The secret key for the docket alert
    :return: The HttpResponse to send to the client
    """
    target_state = DocketAlert.UNSUBSCRIPTION
    if route_prefix == "subscribe":
        target_state = DocketAlert.SUBSCRIPTION
    try:
        docket_alert = DocketAlert.objects.get(secret_key=secret_key)
    except DocketAlert.DoesNotExist:
        return render(
            request,
            "docket_alert.html",
            {
                "docket_alert_not_found": True,
                "da_subscription_type": DocketAlert.SUBSCRIPTION,
                "private": True,
                "target_state": target_state,
            },
            status=HTTP_404_NOT_FOUND,
        )
    # Handle confirmation form POST requests
    if request.method == "POST":
        form = DocketAlertConfirmForm(request.POST)
        if form.is_valid():
            set_docket_alert_state(docket_alert, target_state)
            return render(
                request,
                "docket_alert.html",
                {
                    "docket_alert": docket_alert,
                    "private": True,
                    "target_state": target_state,
                },
            )
        # If the form is invalid, show the form errors.
        return render(
            request,
            "docket_alert_confirmation.html",
            {
                "docket_alert": docket_alert,
                "form": form,
                "private": True,
                "target_state": target_state,
                "h_captcha_site_key": settings.HCAPTCHA_SITEKEY,
            },
        )

    if request.user.is_authenticated:
        # If the user is logged in, flip the docket alert. No confirmation page
        # required
        set_docket_alert_state(docket_alert, target_state)
        return render(
            request,
            "docket_alert.html",
            {
                "docket_alert": docket_alert,
                "private": True,
                "target_state": target_state,
            },
        )

    # Unauthenticated users need to confirm their action, render the
    # confirmation page
    form = DocketAlertConfirmForm()
    return render(
        request,
        "docket_alert_confirmation.html",
        {
            "docket_alert": docket_alert,
            "form": form,
            "private": True,
            "target_state": target_state,
            "h_captcha_site_key": settings.HCAPTCHA_SITEKEY,
        },
    )


@csrf_exempt
@require_http_methods(["POST"])
def one_click_docket_alert_unsubscribe(
    request: HttpRequest,
    secret_key: str,
) -> HttpResponse:
    """Unsubscribes a user from docket alerts for a specific docket.

    :param request: The HttpRequest from the client
    :param secret_key: The secret key for the docket alert
    :return: The HttpResponse to send to the client
    """
    try:
        docket_alert = DocketAlert.objects.get(secret_key=secret_key)
    except DocketAlert.DoesNotExist:
        return HttpResponseNotFound(
            "Your attempt to unsubscribe was unsuccessful."
        )

    set_docket_alert_state(docket_alert, DocketAlert.UNSUBSCRIPTION)

    return HttpResponse("You have been successfully unsubscribed!")
