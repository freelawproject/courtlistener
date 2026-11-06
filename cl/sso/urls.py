from allauth.socialaccount import views as socialaccount_views
from allauth.urls import build_provider_urlpatterns
from django.urls import URLPattern, URLResolver, include, path
from django.views.generic import RedirectView

from cl.lib.ratelimiter import ratelimiter_all_10_per_m
from cl.sso import views


def without_saml_logout(
    patterns: list[URLPattern | URLResolver],
) -> list[URLPattern | URLResolver]:
    """Swap allauth's SAML logout view for one that refuses every request.

    :param patterns: URL patterns, nested includes too. Changed in place.
    :return: The same patterns.
    """
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            without_saml_logout(pattern.url_patterns)
        elif pattern.name == "saml_sls":
            pattern.callback = views.saml_logout_not_supported
    return patterns


def rate_limited(
    patterns: list[URLPattern | URLResolver],
) -> list[URLPattern | URLResolver]:
    """Put a per-IP limit on every view in a list of URL patterns.

    For allauth's provider URLs, which are unauthenticated and, for SAML's
    ACS, CSRF-exempt, and which store state in the session before anything
    is validated. The limit counts every method, since the login callbacks
    are GETs.

    :param patterns: URL patterns, nested includes too. Changed in place.
    :return: The same patterns.
    """
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            rate_limited(pattern.url_patterns)
        else:
            pattern.callback = ratelimiter_all_10_per_m(pattern.callback)
    return patterns


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
                *rate_limited(
                    without_saml_logout(build_provider_urlpatterns())
                ),
            ]
        ),
    ),
]
