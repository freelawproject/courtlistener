from django.conf import settings
from django.urls import include, path
from django.views.decorators.csp import csp_override
from oauth2_provider import views as oauth2_views
from oauth2_provider.urls import (
    app_name as oauth2_app_name,
)
from oauth2_provider.urls import (
    base_urlpatterns,
    oidc_urlpatterns,
)

from cl.oauth import views

# Chrome checks form-action against the redirect a form submission lands on,
# not just the POST itself. Authorizing a client posts here and then redirects
# to its redirect_uri, which is by definition another origin, so the site-wide
# "form-action: 'self'" blocks the whole flow. (Firefox does not enforce the
# directive across redirects, so this breaks in only some browsers. See
# https://github.com/w3c/webappsec-csp/issues/8.)
#
# Dropping the directive for this one view costs nothing: form-action is there
# to stop forms hidden in the third-party HTML we publish from posting
# elsewhere, and the authorize page renders none of that.
CSP_ALLOWING_FOREIGN_REDIRECT = {
    directive: sources
    for directive, sources in settings.SECURE_CSP.items()
    if directive != "form-action"
}

# Redeclared rather than wrapped in place: base_urlpatterns is a module-level
# list, so mutating its entries would follow every other importer.
authorize_urlpattern = path(
    "authorize/",
    csp_override(CSP_ALLOWING_FOREIGN_REDIRECT)(
        oauth2_views.AuthorizationView.as_view()
    ),
    name="authorize",
)

mcp_base_urlpatterns = [authorize_urlpattern] + [
    p
    for p in base_urlpatterns
    if not (p.name or "").startswith("device") and p.name != "authorize"
]

mcp_oidc_urlpatterns = [
    p for p in oidc_urlpatterns if p.name != "rp-initiated-logout"
]

urlpatterns = [
    # RFC 7591 Dynamic Client Registration.
    path(
        "o/register/",
        views.DynamicClientRegistrationView.as_view(),
        name="oauth2_dcr",
    ),
    # RFC 8414 Authorization Server Metadata.
    path(
        ".well-known/oauth-authorization-server",
        views.OAuthMetadataView.as_view(),
        name="oauth2_metadata",
    ),
    # django-oauth-toolkit's OAuth 2.0 and OIDC routes.
    path(
        "o/",
        include(
            (mcp_base_urlpatterns + mcp_oidc_urlpatterns, oauth2_app_name)
        ),
    ),
]
