from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django_ses.views import SESEventWebhookView
from rest_framework.routers import DefaultRouter

from cl.lib.AuthenticationBackend import ConfirmedEmailAuthenticationForm
from cl.lib.ratelimiter import ratelimiter_unsafe_10_per_m
from cl.users import api_views as user_views
from cl.users import views
from cl.users.forms import CustomPasswordResetForm, CustomSetPasswordForm

router = DefaultRouter()

# Webhooks
router.register(r"webhooks", user_views.WebhooksViewSet, basename="webhooks")
router.register(
    r"webhook-events",
    user_views.WebhookEventViewSet,
    basename="webhook_events",
)

urlpatterns = [
    # Sign in/out and password pages
    path(
        "sign-in/",
        ratelimiter_unsafe_10_per_m(
            auth_views.LoginView.as_view(
                **{
                    "template_name": "register/login.html",
                    "authentication_form": ConfirmedEmailAuthenticationForm,
                    "extra_context": {"private": False},
                }
            )
        ),
        name="sign-in",
    ),
    path(
        "sign-out/",
        auth_views.LogoutView.as_view(
            **{
                "template_name": "register/logged_out.html",
                "extra_context": {"private": False},
            },
        ),
    ),
    path(
        "reset-password/",
        ratelimiter_unsafe_10_per_m(
            auth_views.PasswordResetView.as_view(
                **{
                    "template_name": "register/password_reset_form.html",
                    "email_template_name": "register/password_reset_email.html",
                    "extra_context": {"private": False},
                    "form_class": CustomPasswordResetForm,
                }
            )
        ),
        name="password_reset",
    ),
    path(
        "reset-password/instructions-sent/",
        auth_views.PasswordResetDoneView.as_view(
            **{
                "template_name": "register/password_reset_done.html",
                "extra_context": {"private": True},
            },
        ),
        name="password_reset_done",
    ),
    re_path(
        r"^confirm-password/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>.+)/$",
        auth_views.PasswordResetConfirmView.as_view(
            **{
                "template_name": "register/password_reset_confirm.html",
                "form_class": CustomSetPasswordForm,
                "extra_context": {"private": True},
            },
        ),
        name="confirm_password",
    ),
    path(
        "reset-password/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            **{
                "template_name": "register/password_reset_complete.html",
                "extra_context": {"private": True},
            },
        ),
        name="password_reset_complete",
    ),
    # Profile pages
    path("profile/settings/", views.view_settings, name="view_settings"),
    path("profile/", RedirectView.as_view(pattern_name="view_settings")),
    path("profile/notes/", views.view_notes, name="profile_notes"),
    path("profile/alerts/", views.view_search_alerts, name="profile_alerts"),
    path(
        "profile/docket-alerts/",
        views.view_docket_alerts,
        name="profile_docket_alerts",
    ),
    path(
        "profile/visualizations/",
        views.view_visualizations,
        name="view_visualizations",
    ),
    path(
        "profile/visualizations/deleted/",
        views.view_deleted_visualizations,
        name="view_deleted_visualizations",
    ),
    path("profile/api/", views.view_api, name="view_api"),
    path("profile/api-token/", views.view_api_token, name="view_api_token"),
    path("profile/api-usage/", views.view_api_usage, name="view_api_usage"),
    path("profile/webhooks/", views.view_webhooks, name="view_webhooks"),
    re_path(
        "profile/webhooks/(logs|test-logs)/",
        views.view_webhook_logs,
        name="view_webhook_logs",
    ),
    path(
        "profile/webhooks/event/<int:pk>/",
        views.view_webhook_logs_detail,
        name="view_webhook_logs_detail",
    ),
    path(
        "profile/auto_subscribe/toggle/",
        views.toggle_recap_email_auto_subscription,
        name="toggle_recap_email_auto_subscription",
    ),
    path(
        "profile/password/change/",
        views.password_change,
        name="password_change",
    ),
    path(
        "profile/recap-dot-email/",
        views.view_recap_email,
        name="view_recap_email",
    ),
    path("profile/delete/", views.delete_account, name="delete_account"),
    path(
        "profile/delete/done/",
        views.delete_profile_done,
        name="delete_profile_done",
    ),
    path("profile/take-out/", views.take_out, name="take_out"),
    path("profile/take-out/done/", views.take_out_done, name="take_out_done"),
    path(
        "register/",
        ratelimiter_unsafe_10_per_m(views.register),
        name="register",
    ),
    path(
        "register/success/",
        views.register_success,
        name="register_success",
    ),
    # Registration pages
    re_path(
        r"^email/confirm/([0-9a-f]{40})/$",
        views.confirm_email,
        name="email_confirm",
    ),
    path(
        "email-confirmation/request/",
        ratelimiter_unsafe_10_per_m(views.request_email_confirmation),
        name="email_confirmation_request",
    ),
    path(
        "email-confirmation/success/",
        views.email_confirm_success,
        name="email_confirm_success",
    ),
    # Webhooks
    path(
        f"webhook/moosend/",
        views.moosend_webhook,
    ),
    path(
        "webhook/ses/",
        SESEventWebhookView.as_view(),
        name="handle_ses_webhook",
    ),
    re_path(r"^api/htmx/", include(router.urls)),
]
