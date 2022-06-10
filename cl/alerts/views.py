from celery.canvas import chain
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import HttpResponseRedirect, get_object_or_404, render
from django.urls import reverse
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from cl.alerts.models import Alert, DocketAlert
from cl.alerts.tasks import send_unsubscription_confirmation
from cl.lib.http import is_ajax
from cl.lib.ratelimiter import ratelimit_deny_list
from cl.lib.types import AuthenticatedHttpRequest
from cl.opinion_page.views import make_docket_title, user_has_alert
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


@ratelimit_deny_list
def disable_alert(request, secret_key):
    """Disable an alert based on a secret key."""
    alert = get_object_or_404(Alert, secret_key=secret_key)
    prev_rate = alert.rate
    alert.rate = Alert.OFF
    alert.save()
    return render(
        request,
        "disable_alert.html",
        {"alert": alert, "prev_rate": prev_rate, "private": True},
    )


@ratelimit_deny_list
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
                existing_alert.update(alert_type=DocketAlert.UNSUBSCRIPTION)
                msg = "Alert disabled successfully"
            else:
                existing_alert.update(alert_type=DocketAlert.SUBSCRIPTION)
                msg = "Alerts are now enabled for this docket"
        else:
            DocketAlert.objects.create(docket_id=docket_pk, user=request.user)
            msg = "Alerts are now enabled for this docket"

        return HttpResponse(msg)
    else:
        return HttpResponseNotAllowed(
            permitted_methods={"POST"}, content="Not an ajax POST request."
        )


@login_required
def new_docket_alert(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Allow users to create docket alerts based on case and court ID"""
    pacer_case_id = request.GET.get("pacer_case_id")
    court_id = request.GET.get("court_id")
    if not pacer_case_id or not court_id:
        return render(
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
        docket = Docket.objects.get(
            pacer_case_id=pacer_case_id, court_id=court_id
        )
    except Docket.DoesNotExist:
        return render(
            request,
            "docket_alert_new.html",
            {
                "docket": None,
                "title": "New Docket Alert for Unknown Case",
                "private": True,
            },
            status=HTTP_404_NOT_FOUND,
        )
    except Docket.MultipleObjectsReturned as exc:
        docket = Docket.objects.filter(
            pacer_case_id=pacer_case_id, court_id=court_id
        ).earliest("date_created")

    title = f"New Docket Alert for {make_docket_title(docket)}"
    has_alert = user_has_alert(request.user, docket)
    return render(
        request,
        "docket_alert_new.html",
        {
            "title": title,
            "has_alert": has_alert,
            "docket": docket,
            "private": True,
        },
    )


@ratelimit_deny_list
def subscribe_docket_alert(request, secret_key):
    docket_alert = get_object_or_404(DocketAlert, secret_key=secret_key)
    docket_alert.alert_type = DocketAlert.SUBSCRIPTION
    docket_alert.save()
    return render(
        request,
        "enable_docket_alert.html",
        {"docket_alert": docket_alert, "private": True},
    )


@ratelimit_deny_list
def unsubscribe_docket_alert(request, secret_key):
    docket_alert = get_object_or_404(DocketAlert, secret_key=secret_key)
    docket_alert.alert_type = DocketAlert.UNSUBSCRIPTION
    docket_alert.save()
    # Send Unsubscription confirmation email to the user
    send_unsubscription_confirmation.delay(docket_alert.pk)
    return render(
        request,
        "disable_docket_alert.html",
        {"docket_alert": docket_alert, "private": True},
    )
