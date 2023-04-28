import json
import logging
from collections import OrderedDict
from datetime import timedelta
from email.utils import parseaddr
from json import JSONDecodeError

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, F
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    QueryDict,
)
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import urlencode
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import (
    sensitive_post_parameters,
    sensitive_variables,
)
from django.views.decorators.http import require_http_methods
from rest_framework.renderers import JSONRenderer

from cl.alerts.models import DocketAlert
from cl.api.models import WEBHOOK_EVENT_STATUS, WebhookEvent, WebhookEventType
from cl.custom_filters.decorators import check_honeypot
from cl.favorites.forms import NoteForm
from cl.lib.crypto import sha1_activation_key
from cl.lib.ratelimiter import ratelimiter_unsafe_10_per_m
from cl.lib.types import AuthenticatedHttpRequest, EmailType
from cl.lib.url_utils import get_redirect_or_login_url
from cl.search.models import SEARCH_TYPES
from cl.stats.utils import tally_stat
from cl.users.forms import (
    AccountDeleteForm,
    CustomPasswordChangeForm,
    EmailConfirmationForm,
    OptInConsentForm,
    ProfileForm,
    UserCreationFormExtended,
    UserForm,
)
from cl.users.models import UserProfile
from cl.users.tasks import update_moosend_subscription
from cl.users.utils import (
    convert_to_stub_account,
    delete_user_assets,
    emails,
    message_dict,
)
from cl.visualizations.models import SCOTUSMap

logger = logging.getLogger(__name__)


@login_required
@never_cache
def view_search_alerts(request: HttpRequest) -> HttpResponse:
    search_alerts = request.user.alerts.all()
    for a in search_alerts:
        # default to 'o' because if there's no 'type' param in the search UI,
        # that's an opinion search.
        a.type = QueryDict(a.query).get("type", SEARCH_TYPES.OPINION)
    return TemplateResponse(
        request,
        "profile/alerts.html",
        {
            "search_alerts": search_alerts,
            "page": "search_alerts",
            "private": True,
            "page_title": "Search Alerts",
        },
    )


@login_required
@never_cache
def view_docket_alerts(request: HttpRequest) -> HttpResponse:
    order_by = request.GET.get("order_by", "date_created")
    if order_by.startswith("-"):
        direction = "-"
        order_by = order_by.lstrip("-")
    else:
        direction = ""
    name_map = {
        "name": "docket__case_name",
        "court": "docket__court__short_name",
        "hit": "date_last_hit",
    }
    order_by = name_map.get(order_by, "date_created")
    docket_alerts = request.user.docket_alerts.filter(
        alert_type=DocketAlert.SUBSCRIPTION
    )
    if order_by == "date_last_hit":
        if direction:
            docket_alerts = docket_alerts.order_by(
                F(order_by).desc(nulls_last=True)
            )
        else:
            docket_alerts = docket_alerts.order_by(
                F(order_by).asc(nulls_first=True)
            )
    else:
        docket_alerts = docket_alerts.order_by(f"{direction}{order_by}")

    return TemplateResponse(
        request,
        "profile/alerts.html",
        {
            "docket_alerts": docket_alerts,
            "page": "docket_alerts",
            "private": True,
            "page_title": "Docket Alerts",
        },
    )


@login_required
@never_cache
def view_notes(request: AuthenticatedHttpRequest) -> HttpResponse:
    notes = request.user.notes.all().order_by("pk")
    note_forms = OrderedDict()
    note_forms["Dockets"] = []
    note_forms["RECAP Documents"] = []
    note_forms["Opinions"] = []
    note_forms["Oral Arguments"] = []
    for note in notes:
        if note.cluster_id:
            key = "Opinions"
        elif note.audio_id:
            key = "Oral Arguments"
        elif note.recap_doc_id:
            key = "RECAP Documents"
        elif note.docket_id:
            key = "Dockets"
        note_forms[key].append(NoteForm(instance=note))
    docket_search_url = (
        "/?type=r&q=xxx AND docket_id:("
        + " OR ".join(
            [str(a.instance.docket_id.pk) for a in note_forms["Dockets"]]
        )
        + ")"
    )
    oral_search_url = (
        "/?type=oa&q=xxx AND id:("
        + " OR ".join(
            [str(a.instance.audio_id.pk) for a in note_forms["Oral Arguments"]]
        )
        + ")"
    )
    recap_search_url = (
        "/?type=r&q=xxx AND docket_entry_id:("
        + " OR ".join(
            [
                str(a.instance.recap_doc_id.pk)
                for a in note_forms["RECAP Documents"]
            ]
        )
        + ")"
    )
    opinion_search_url = (
        "/?q=xxx AND cluster_id:("
        + " OR ".join(
            [str(a.instance.cluster_id.pk) for a in note_forms["Opinions"]]
        )
        + ")&stat_Precedential=on&stat_Non-Precedential=on&stat_Errata=on&stat_Separate%20Opinion=on&stat_In-chambers=on&stat_Relating-to%20orders=on&stat_Unknown%20Status=on"
    )
    return TemplateResponse(
        request,
        "profile/notes.html",
        {
            "private": True,
            "note_forms": note_forms,
            "blank_note_form": NoteForm(),
            "docket_search_url": docket_search_url,
            "oral_search_url": oral_search_url,
            "recap_search_url": recap_search_url,
            "opinion_search_url": opinion_search_url,
        },
    )


@login_required
@never_cache
def view_donations(request: AuthenticatedHttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "profile/donations.html",
        {"page": "profile_donations", "private": True},
    )


@login_required
@never_cache
def view_visualizations(request: AuthenticatedHttpRequest) -> HttpResponse:
    visualizations = (
        SCOTUSMap.objects.filter(user=request.user, deleted=False)
        .annotate(Count("clusters"))
        .order_by("-date_created")
    )
    paginator = Paginator(visualizations, 20, orphans=2)
    page = request.GET.get("page", 1)
    try:
        paged_vizes = paginator.page(page)
    except PageNotAnInteger:
        paged_vizes = paginator.page(1)
    except EmptyPage:
        paged_vizes = paginator.page(paginator.num_pages)
    return TemplateResponse(
        request,
        "profile/visualizations.html",
        {
            "results": paged_vizes,
            "page": "visualizations_active",
            "private": True,
        },
    )


@login_required
@never_cache
def view_deleted_visualizations(
    request: AuthenticatedHttpRequest,
) -> HttpResponse:
    thirty_days_ago = now() - timedelta(days=30)
    visualizations = (
        SCOTUSMap.objects.filter(
            user=request.user, deleted=True, date_deleted__gte=thirty_days_ago
        )
        .annotate(Count("clusters"))
        .order_by("-date_created")
    )
    paginator = Paginator(visualizations, 20, orphans=2)
    page = request.GET.get("page", 1)
    try:
        paged_vizes = paginator.page(page)
    except PageNotAnInteger:
        paged_vizes = paginator.page(1)
    except EmptyPage:
        paged_vizes = paginator.page(paginator.num_pages)

    return TemplateResponse(
        request,
        "profile/visualizations_deleted.html",
        {
            "results": paged_vizes,
            "page": "visualizations_trash",
            "private": True,
        },
    )


@login_required
@never_cache
def view_api(request: AuthenticatedHttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "profile/api.html",
        {
            "private": True,
            "page": "api_info",
            "page_title": "API Documentation",
        },
    )


@login_required
@never_cache
def view_api_token(request: AuthenticatedHttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "profile/api.html",
        {"private": True, "page": "api_token", "page_title": "API Token"},
    )


@login_required
@never_cache
def view_api_usage(request: AuthenticatedHttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "profile/api.html",
        {"private": True, "page": "api_usage", "page_title": "API Usage"},
    )


@sensitive_variables(
    # Contains password info
    "user_cd",
    # Contains activation key
    "email",
)
@login_required
@never_cache
def view_settings(request: AuthenticatedHttpRequest) -> HttpResponse:
    old_email = request.user.email  # this line has to be at the top to work.
    old_wants_newsletter = request.user.profile.wants_newsletter
    user = request.user
    up = user.profile
    user_form = UserForm(request.POST or None, instance=user)
    profile_form = ProfileForm(request.POST or None, instance=up)
    if profile_form.is_valid() and user_form.is_valid():
        user_cd = user_form.cleaned_data
        profile_cd = profile_form.cleaned_data
        new_email = user_cd["email"]
        changed_email = old_email != new_email
        if changed_email:
            # Email was changed.
            up.activation_key = sha1_activation_key(user.username)
            up.key_expires = now() + timedelta(5)
            up.email_confirmed = False

            # Unsubscribe the old address in moosend (we'll
            # resubscribe it when they confirm it later).
            update_moosend_subscription.delay(old_email, "unsubscribe")

            # Send an email to the new and old addresses. New for verification;
            # old for notification of the change.
            email: EmailType = emails["email_changed_successfully"]
            send_mail(
                email["subject"],
                email["body"] % (user.username, up.activation_key),
                email["from_email"],
                [new_email],
            )
            email: EmailType = emails["notify_old_address"]
            send_mail(
                email["subject"],
                email["body"] % (user.username, old_email, new_email),
                email["from_email"],
                [old_email],
            )
            msg = message_dict["email_changed_successfully"]
            messages.add_message(request, msg["level"], msg["message"])
            logout(request)
        else:
            # if the email wasn't changed, simply inform of success.
            msg = message_dict["settings_changed_successfully"]
            messages.add_message(request, msg["level"], msg["message"])

        new_wants_newsletter = profile_cd["wants_newsletter"]
        if old_wants_newsletter != new_wants_newsletter:
            if new_wants_newsletter is True and not changed_email:
                # They just subscribed. If they didn't *also* update their
                # email address, subscribe them.
                update_moosend_subscription.delay(new_email, "subscribe")
            elif new_wants_newsletter is False:
                # They just unsubscribed
                update_moosend_subscription.delay(new_email, "unsubscribe")

        # New email address and changes above are saved here.
        profile_form.save()
        user_form.save()

        return HttpResponseRedirect(reverse("view_settings"))

    return TemplateResponse(
        request,
        "profile/settings.html",
        {
            "profile_form": profile_form,
            "user_form": user_form,
            "page": "profile_settings",
            "private": True,
        },
    )


@sensitive_post_parameters("password")
@login_required
@ratelimiter_unsafe_10_per_m
def delete_account(request: AuthenticatedHttpRequest) -> HttpResponse:
    non_deleted_map_count = request.user.scotus_maps.filter(
        deleted=False
    ).count()
    if request.method == "POST":
        delete_form = AccountDeleteForm(request, request.POST)
        if delete_form.is_valid():
            email: EmailType = emails["account_deleted"]
            send_mail(
                email["subject"],
                email["body"] % request.user,
                email["from_email"],
                email["to"],
            )
            delete_user_assets(request.user)
            user = convert_to_stub_account(request.user)
            update_moosend_subscription.delay(
                request.user.email, "unsubscribe"
            )
            update_session_auth_hash(request, user)
            logout(request)
            return HttpResponseRedirect(reverse("delete_profile_done"))

    else:
        delete_form = AccountDeleteForm(request=request)
    return TemplateResponse(
        request,
        "profile/delete.html",
        {
            "non_deleted_map_count": non_deleted_map_count,
            "delete_form": delete_form,
            "page": "profile_settings",
            "private": True,
        },
    )


def delete_profile_done(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "profile/deleted.html", {"private": True})


@login_required
def take_out(request: AuthenticatedHttpRequest) -> HttpResponse:
    if request.method == "POST":
        email: EmailType = emails["take_out_requested"]
        send_mail(
            email["subject"],
            email["body"] % (request.user, request.user.email),
            email["from_email"],
            email["to"],
        )

        return HttpResponseRedirect(reverse("take_out_done"))

    return TemplateResponse(
        request,
        "profile/take_out.html",
        {"private": True},
    )


def take_out_done(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "profile/take_out_done.html",
        {"private": True},
    )


@sensitive_post_parameters("password1", "password2")
@sensitive_variables(
    # Contains password info
    "cd",
    # Contains activation key
    "email",
)
@check_honeypot(field_name="skip_me_if_alive")
@never_cache
def register(request: HttpRequest) -> HttpResponse:
    """allow only an anonymous user to register"""
    redirect_to = get_redirect_or_login_url(request, "next")
    if request.user.is_anonymous:
        if request.method == "POST":
            try:
                stub_account = User.objects.filter(
                    profile__stub_account=True,
                ).get(email__iexact=request.POST.get("email"))
            except User.DoesNotExist:
                stub_account = False

            if stub_account:
                form = UserCreationFormExtended(
                    request.POST, instance=stub_account
                )
            else:
                form = UserCreationFormExtended(request.POST)

            consent_form = OptInConsentForm(request.POST)
            if form.is_valid() and consent_form.is_valid():
                cd = form.cleaned_data
                if not stub_account:
                    # make a new user that is active, but has not confirmed
                    # their email address
                    user = User.objects.create_user(
                        cd["username"], cd["email"], cd["password1"]
                    )
                    up = UserProfile(user=user)
                else:
                    # Upgrade the stub account to make it a regular account.
                    user = stub_account
                    user.set_password(cd["password1"])
                    user.username = cd["username"]
                    user.is_active = True
                    up = stub_account.profile
                    up.stub_account = False

                if cd["first_name"]:
                    user.first_name = cd["first_name"]
                if cd["last_name"]:
                    user.last_name = cd["last_name"]
                user.save()

                # Build and assign the activation key
                up.activation_key = sha1_activation_key(user.username)
                up.key_expires = now() + timedelta(days=5)
                up.save()

                email: EmailType = emails["confirm_your_new_account"]
                send_mail(
                    email["subject"],
                    email["body"] % (user.username, up.activation_key),
                    email["from_email"],
                    [user.email],
                )
                email: EmailType = emails["new_account_created"]
                send_mail(
                    email["subject"] % up.user.username,
                    email["body"]
                    % (
                        up.user.get_full_name() or "Not provided",
                        up.user.email,
                    ),
                    email["from_email"],
                    email["to"],
                )
                tally_stat("user.created")
                get_str = "?next=%s&email=%s" % (
                    urlencode(redirect_to),
                    urlencode(user.email),
                )
                return HttpResponseRedirect(
                    reverse("register_success") + get_str
                )
        else:
            form = UserCreationFormExtended()
            consent_form = OptInConsentForm()
        return TemplateResponse(
            request,
            "register/register.html",
            {"form": form, "consent_form": consent_form, "private": False},
        )
    else:
        # The user is already logged in. Direct them to their settings page as
        # a logical fallback
        return HttpResponseRedirect(reverse("view_settings"))


@never_cache
def register_success(request: HttpRequest) -> HttpResponse:
    """Tell the user they have been registered and allow them to continue where
    they left off."""
    redirect_to = get_redirect_or_login_url(request, "next")
    email = request.GET.get("email", "")
    default_from = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    return TemplateResponse(
        request,
        "register/registration_complete.html",
        {
            "redirect_to": redirect_to,
            "email": email,
            "default_from": default_from,
            "private": True,
        },
    )


@sensitive_variables("activation_key")
@never_cache
def confirm_email(request, activation_key):
    """Confirms email addresses for a user and sends an email to the admins.

    Checks if a hash in a confirmation link is valid, and if so sets the user's
    email address as valid. If they are subscribed to the newsletter, ensures
    that moosend is updated.
    """
    ups = UserProfile.objects.filter(activation_key=activation_key)
    if not len(ups):
        return TemplateResponse(
            request,
            "register/confirm.html",
            {"invalid": True, "private": True},
        )

    confirmed_accounts_count = 0
    expired_key_count = 0
    for up in ups:
        if up.email_confirmed:
            confirmed_accounts_count += 1
        if up.key_expires < now():
            expired_key_count += 1

    if confirmed_accounts_count == len(ups):
        # All the accounts were already confirmed.
        return TemplateResponse(
            request,
            "register/confirm.html",
            {"already_confirmed": True, "private": True},
        )

    if expired_key_count > 0:
        return TemplateResponse(
            request,
            "register/confirm.html",
            {"expired": True, "private": True},
        )

    # Tests pass; Save the profile
    for up in ups:
        if up.wants_newsletter:
            update_moosend_subscription.delay(up.user.email, "subscribe")
        up.email_confirmed = True
        up.save()

    return TemplateResponse(
        request, "register/confirm.html", {"success": True, "private": True}
    )


@sensitive_variables(
    "activation_key",
    # Contains activation key
    "email",
)
@check_honeypot(field_name="skip_me_if_alive")
def request_email_confirmation(request: HttpRequest) -> HttpResponse:
    """Send an email confirmation email"""
    if request.method == "POST":
        form = EmailConfirmationForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            users = User.objects.filter(email__iexact=cd["email"])
            if not len(users):
                # Normally, we'd throw an error here, but instead we pretend it
                # was a success. Meanwhile, we send an email saying that a
                # request was made, but we don't have an account with that
                # email address.
                email: EmailType = emails["no_account_found"]
                message = email["body"] % (
                    "email confirmation",
                    reverse("register"),
                )
                send_mail(
                    email["subject"],
                    message,
                    email["from_email"],
                    [cd["email"]],
                )
                return HttpResponseRedirect(reverse("email_confirm_success"))

            activation_key = sha1_activation_key(cd["email"])
            key_expires = now() + timedelta(days=5)

            for user in users:
                # associate it with the user's accounts.
                up = user.profile
                up.activation_key = activation_key
                up.key_expires = key_expires
                up.save()

            email: EmailType = emails["confirm_existing_account"]
            send_mail(
                email["subject"],
                email["body"] % activation_key,
                email["from_email"],
                [user.email],
            )
            return HttpResponseRedirect(reverse("email_confirm_success"))
    else:
        form = EmailConfirmationForm()
    return TemplateResponse(
        request,
        "register/request_email_confirmation.html",
        {"private": True, "form": form},
    )


@never_cache
def email_confirm_success(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "register/request_email_confirmation_success.html",
        {"private": False},
    )


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@login_required
@never_cache
@ratelimiter_unsafe_10_per_m
def password_change(request: AuthenticatedHttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            msg = message_dict["pwd_changed_successfully"]
            messages.add_message(request, msg["level"], msg["message"])
            update_session_auth_hash(request, form.user)
            return HttpResponseRedirect(reverse("password_change"))
    else:
        form = CustomPasswordChangeForm(user=request.user)
    return TemplateResponse(
        request,
        "profile/password_form.html",
        {"form": form, "page": "profile_password", "private": False},
    )


@csrf_exempt  # nosemgrep
def moosend_webhook(request: HttpRequest) -> HttpResponse:
    logger.info("Got moosend webhook with %s method.", request.method)

    if request.method == "POST":
        # The body is returned as a byte string
        body = request.body.decode("utf-8")
        json_body = json.loads(body)
        webhook_event = json_body.get("Event")
        if webhook_event:
            webhook_event_name = webhook_event.get("EventName")
            webhook_contact_context = webhook_event.get("ContactContext")
            wants_newsletter = None
            email = None
            if webhook_contact_context:
                email = webhook_contact_context.get("EmailAddress")
            if webhook_event_name == "SUBSCRIBED":
                wants_newsletter = True
            elif webhook_event_name == "UNSUBSCRIBED":
                wants_newsletter = False
            if wants_newsletter is not None and email is not None:
                profiles = UserProfile.objects.filter(user__email=email)
                logger.info(
                    "Updating %s profiles for email %s",
                    profiles.count(),
                    email,
                )
                profiles.update(wants_newsletter=wants_newsletter)

    # Moosend does a GET when you create/edit the automation workflow,
    # so we need to return a 200 even for GETs.
    return HttpResponse("<h1>200: OK</h1>")


@login_required
@never_cache
def view_webhooks(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Render the webhooks page"""
    return TemplateResponse(
        request,
        "profile/webhooks.html",
        {
            "private": True,
            "page": "api_webhooks",
            "sub_page": "webhooks",
        },
    )


@login_required
@never_cache
def view_webhook_logs(
    request: AuthenticatedHttpRequest,
    route_prefix: str,
) -> HttpResponse:
    """Render the webhooks logs page"""

    page_title = "Webhook Logs"
    sub_page = "logs"
    debug = False
    if route_prefix == "test-logs":
        page_title = "Webhook Test Logs"
        sub_page = "test_logs"
        debug = True

    return TemplateResponse(
        request,
        "profile/webhooks_logs.html",
        {
            "private": True,
            "page": "api_webhooks",
            "page_title": page_title,
            "sub_page": sub_page,
            "debug": debug,
            "event_types": WebhookEventType,
            "event_statuses": WEBHOOK_EVENT_STATUS.STATUS,
        },
    )


@login_required
@never_cache
def view_webhook_logs_detail(
    request: AuthenticatedHttpRequest, pk: int
) -> HttpResponse:
    """Render the webhook event detail page"""

    webhook_event = get_object_or_404(
        WebhookEvent, webhook__user=request.user, pk=pk
    )
    renderer = JSONRenderer()
    json_content = renderer.render(
        webhook_event.content,
        accepted_media_type="application/json; indent=2;",
    ).decode()
    sub_page = "logs"
    if webhook_event.debug:
        sub_page = "test_logs"

    return TemplateResponse(
        request,
        "includes/webhook-event-detail.html",
        {
            "private": True,
            "page": "api_webhooks",
            "sub_page": sub_page,
            "webhook_event": webhook_event,
            "json_content": json_content,
        },
    )


@login_required
@require_http_methods(["POST"])
def toggle_recap_email_auto_subscription(
    request: AuthenticatedHttpRequest,
) -> HttpResponse:
    """Toggle the user's setting to auto-subscribe to recap.email cases"""

    if request.user.is_anonymous:
        return HttpResponse("Please log in to continue.")

    user = request.user
    if request.POST["current_toggle_status"] == "True":
        UserProfile.objects.filter(user=user).update(auto_subscribe=False)
        msg = "Auto-subscribe to @recap.email cases is now disabled"
    else:
        UserProfile.objects.filter(user=user).update(auto_subscribe=True)
        msg = "Auto-subscribe to @recap.email cases is now enabled"
    return HttpResponse(msg)


@login_required
@never_cache
def view_recap_email(request: AuthenticatedHttpRequest) -> HttpResponse:
    auto_subscribe = request.user.profile.auto_subscribe
    return TemplateResponse(
        request,
        "profile/recap_email.html",
        {
            "private": True,
            "page": "profile_recap",
            "auto_subscribe": auto_subscribe,
        },
    )
