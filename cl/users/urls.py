from cl.lib.AuthenticationBackend import ConfirmedEmailAuthenticationForm
from cl.users.forms import (
    CustomPasswordResetForm, CustomSetPasswordForm,
)
from cl.users import views
from django.conf.urls import url
from django.contrib.auth import views as auth_views


urlpatterns = [
    # Sign in/out and password pages
    url(
        r'^sign-in/$',
        auth_views.login,
        {
            'template_name': 'register/login.html',
            'authentication_form': ConfirmedEmailAuthenticationForm,
            'extra_context': {'private': False}
        },
        name="sign-in"),
    url(
        r'^sign-out/$',
        auth_views.logout,
        {
            'template_name': 'register/logged_out.html',
            'extra_context': {'private': False}
        },
    ),
    url(
        r'^reset-password/$',
        auth_views.password_reset,
        {
            'template_name': 'register/password_reset_form.html',
            'email_template_name': 'register/password_reset_email.html',
            'extra_context': {'private': False},
            'password_reset_form': CustomPasswordResetForm
        }
    ),
    url(
        r'^reset-password/instructions-sent/$',
        auth_views.password_reset_done,
        {
            'template_name': 'register/password_reset_done.html',
            'extra_context': {'private': False}
        },
        name='password_reset_done',
    ),
    url(
        r'^confirm-password/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>.+)/$',
        auth_views.password_reset_confirm,
        {
            'template_name': 'register/password_reset_confirm.html',
            'set_password_form': CustomSetPasswordForm,
            'extra_context': {'private': False}
        }
    ),
    url(
        r'^reset-password/complete/$',
        auth_views.password_reset_complete,
        {
            'template_name': 'register/password_reset_complete.html',
            'extra_context': {'private': False}
        },
        name='password_reset_complete',
    ),

    # Profile pages
    url(r'^profile/settings/$', views.view_settings, name='view_settings'),
    url(r'^profile/favorites/$', views.view_favorites),
    url(r'^profile/alerts/$', views.view_alerts),
    url(
        r'^profile/visualizations/$',
        views.view_visualizations,
        name='view_visualizations'
    ),
    url(
        r'^profile/visualizations/deleted/$',
        views.view_deleted_visualizations,
        name='view_deleted_visualizations',
    ),
    url(r'^profile/api/$', views.view_api, name='view_api'),
    url(r'^profile/password/change/$', views.password_change),
    url(r'^profile/delete/$', views.delete_account),
    url(r'^profile/delete/done/$', views.delete_profile_done),
    url(
        r'^register/$',
        views.register,
        name="register"
    ),
    url(r'^register/success/$', views.register_success),

    # Registration pages
    url(
        r'^email/confirm/([0-9a-f]{40})/$',
        views.confirm_email
    ),
    url(
        r'^email-confirmation/request/$',
        views.request_email_confirmation,
        name='email_confirmation_request'
    ),
    url(
        r'^email-confirmation/success/$',
        views.email_confirm_success
    ),
]
