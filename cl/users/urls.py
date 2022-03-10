from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, re_path
from django.views.generic import RedirectView

from cl.lib.AuthenticationBackend import ConfirmedEmailAuthenticationForm
from cl.lib.ratelimiter import ratelimiter_unsafe_10_per_m
from cl.users import views
from cl.users.forms import CustomPasswordResetForm, CustomSetPasswordForm

from django_ses.views import SESEventWebhookView

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
    path("profile/favorites/", views.view_favorites, name="profile_favorites"),
    path("profile/alerts/", views.view_alerts, name="profile_alerts"),
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
    path(
        "profile/password/change/",
        views.password_change,
        name="password_change",
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
        f"webhook/mailchimp/{settings.MAILCHIMP_SECRET}/",
        views.mailchimp_webhook,
    ),
    path(
        "ses/event-webhook/",
        SESEventWebhookView.as_view(),
        name="handle-event-webhook",
    ),
]
