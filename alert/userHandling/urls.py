from alert.AuthenticationBackend import ConfirmedEmailAuthenticationForm
from alert.userHandling.forms import CustomPasswordResetForm
from alert.userHandling.views import (
    confirmEmail, deleteProfile, deleteProfileDone, emailConfirmSuccess,
    password_change, register, register_success,
    request_email_confirmation, view_favorites, view_alerts, view_settings
)
from django.conf.urls import patterns, url
from django.contrib.auth.views import (
    login, logout, password_reset, password_reset_done, password_reset_confirm
)
from django.views.generic import RedirectView


urlpatterns = patterns('',
    # Sign in/out and password pages
    url(r'^sign-in/$', login, {
        'authentication_form': ConfirmedEmailAuthenticationForm,
        'extra_context': {'private': False}},
        name="sign-in"),
    (r'^sign-out/$', logout, {'extra_context': {'private': False}}),
    (r'^reset-password/$', password_reset,
     {'extra_context': {'private': False},
      'password_reset_form': CustomPasswordResetForm}),
    (r'^reset-password/instructions-sent/$', password_reset_done,
     {'extra_context': {'private': False}}),
    (r'^confirm-password/(?P<uidb36>.*)/(?P<token>.*)/$',
     password_reset_confirm,
     {'post_reset_redirect': '/reset-password/complete/',
      'extra_context': {'private': False}}),
    (r'^reset-password/complete/$', login, {
        'template_name': 'registration/password_reset_complete.html',
        'extra_context': {'private': False}}),

    # Settings pages
    url(r'^profile/settings/$', view_settings, name='view_settings'),
    (r'^profile/$', RedirectView.as_view(
        url='/profile/settings/',
        permanent=True)
    ),
    (r'^profile/favorites/$', view_favorites),
    (r'^profile/alerts/$', view_alerts),
    (r'^profile/password/change/$', password_change),
    (r'^profile/delete/$', deleteProfile),
    (r'^profile/delete/done/$', deleteProfileDone),
    url(r'^register/$', register, name="register"),
    (r'^register/success/$', register_success),

    # Registration pages
    (r'^email/confirm/([0-9a-f]{40})/$', confirmEmail),
    (r'^email-confirmation/request/$', request_email_confirmation),
    (r'^email-confirmation/success/$', emailConfirmSuccess),
)
