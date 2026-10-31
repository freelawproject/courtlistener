from allauth.socialaccount import views as socialaccount_views
from allauth.urls import build_provider_urlpatterns
from django.urls import include, path
from django.views.generic import RedirectView

from cl.sso import views

# Only the SSO parts of allauth are routed. allauth.urls is deliberately not
# included: it would also mount allauth's own login, signup and password
# reset pages, none of which have CourtListener's rate limits, confirmed-email
# check or anti-enumeration behavior.
urlpatterns = [
    path("sso/", views.sso_start, name="sso_start"),
    path(
        "sso/",
        include(
            [
                # allauth's SSO flow sends people to these URL names (e.g.
                # after an inactive account signs in, or a cancelled login),
                # so they point at CourtListener's own sign-in page.
                path(
                    "sign-in/",
                    RedirectView.as_view(
                        pattern_name="sign-in", query_string=True
                    ),
                    name="account_login",
                ),
                path(
                    "inactive/",
                    RedirectView.as_view(pattern_name="sign-in"),
                    name="account_inactive",
                ),
                path(
                    "login/cancelled/",
                    socialaccount_views.login_cancelled,
                    name="socialaccount_login_cancelled",
                ),
                path(
                    "login/error/",
                    socialaccount_views.login_error,
                    name="socialaccount_login_error",
                ),
                # One login and callback URL per installed provider, e.g.
                # /sso/oidc/<provider_id>/login/ for OpenID Connect.
                path(
                    "oidc/<str:provider_id>/initiate/",
                    views.oidc_initiate_login,
                    name="sso_oidc_initiate",
                ),
                *build_provider_urlpatterns(),
            ]
        ),
    ),
]
