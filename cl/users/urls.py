from cl.users.forms import (
    CustomPasswordResetForm, CustomSetPasswordForm,
)
from cl.users.views import (
    confirm_email, delete_account, delete_profile_done, email_confirm_success,
    password_change, register, register_success, request_email_confirmation,
    view_favorites, view_alerts, view_settings, view_visualizations,
)
from django.conf.urls import url
from django.contrib.auth.views import (
    login, logout, password_reset, password_reset_done, password_reset_confirm,
)



urlpatterns = [
    # Sign in/out and password pages
    url(r'^sign-in/$', login, {
        'extra_context': {'private': False}},
        name="sign-in"),
    url(r'^sign-out/$', logout, {'extra_context': {'private': False}}),
    url(r'^reset-password/$', password_reset,
        {'extra_context': {'private': False},
         'password_reset_form': CustomPasswordResetForm}),
    url(r'^reset-password/instructions-sent/$', password_reset_done,
        {'extra_context': {'private': False}}),
    url(r'^confirm-password/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>.+)/$',
        password_reset_confirm,
        {'post_reset_redirect': '/reset-password/complete/',
         'set_password_form': CustomSetPasswordForm,
         'extra_context': {'private': False}}),
    url(r'^reset-password/complete/$', login, {
        'template_name': 'registration/password_reset_complete.html',
        'extra_context': {'private': False}}),

    # Settings pages
    url(r'^profile/settings/$', view_settings, name='view_settings'),
    url(r'^profile/favorites/$', view_favorites),
    url(r'^profile/alerts/$', view_alerts),
    url(r'^profile/visualizations/$', view_visualizations,
        name='view_visualizations'),
    url(r'^profile/password/change/$', password_change),
    url(r'^profile/delete/$', delete_account),
    url(r'^profile/delete/done/$', delete_profile_done),
    url(r'^register/$', register, name="register"),
    url(r'^register/success/$', register_success),

    # Registration pages
    url(r'^email/confirm/([0-9a-f]{40})/$', confirm_email),
    url(r'^email-confirmation/request/$', request_email_confirmation),
    url(r'^email-confirmation/success/$', email_confirm_success),
]
