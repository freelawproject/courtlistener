from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import HttpResponseRedirect, get_object_or_404, render
from django.urls import reverse
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from cl.alerts.models import Alert, DocketAlert
from cl.lib.ratelimiter import ratelimit_if_not_whitelisted
from cl.opinion_page.views import make_docket_title, user_has_alert
from cl.search.models import Docket


@login_required
def edit_alert_redirect(request, alert_id):
    """Note that this method is still very useful because it gives people an
    opportunity to login if they come to the site via one of our email alerts.
    """
    try:
        alert_id = int(alert_id)
    except ValueError:
        return HttpResponseRedirect("/")

    # check if the user can edit this, or if they are url hacking
    alert = get_object_or_404(Alert, pk=alert_id, user=request.user)
    return HttpResponseRedirect("/?%s&edit_alert=%s" % (alert.query, alert.pk))


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
        "Your alert <strong>%s</strong> was deleted successfully."
        % alert.name,
    )
    return HttpResponseRedirect(reverse("profile_alerts"))


@login_required
def delete_alert_confirm(request, alert_id):
    try:
        alert_id = int(alert_id)
    except ValueError:
        return HttpResponseRedirect("/")
    return render(
        request,
        "delete_confirm.html",
        {"alert_id": alert_id, "private": False},
    )


@ratelimit_if_not_whitelisted
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


@ratelimit_if_not_whitelisted
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


def toggle_docket_alert(request: HttpRequest) -> HttpResponse:
    """Use Ajax to create or delete an alert for a user."""
    if request.is_ajax() and request.method == "POST":
        docket_pk = request.POST.get("id")
        existing_alert = DocketAlert.objects.filter(
            user=request.user, docket_id=docket_pk
        )
        if existing_alert.exists():
            existing_alert.delete()
            msg = "Alert disabled successfully"
        else:
            DocketAlert.objects.create(docket_id=docket_pk, user=request.user)
            msg = "Alerts are now enabled for this docket"
        return HttpResponse(msg)
    else:
        return HttpResponseNotAllowed(
            permitted_methods={"POST"}, content="Not an ajax POST request."
        )


def new_docket_alert(request: HttpRequest) -> HttpResponse:
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

    title = "New Docket Alert for %s" % make_docket_title(docket)
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
