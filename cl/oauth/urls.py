from django.urls import include, path
from oauth2_provider.urls import (
    app_name as oauth2_app_name,
)
from oauth2_provider.urls import (
    base_urlpatterns,
    oidc_urlpatterns,
)

from cl.oauth import views

mcp_base_urlpatterns = [
    p for p in base_urlpatterns if not (p.name or "").startswith("device")
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
