from django.urls import path
from oauth2_provider import views as oauth2_views

from cl.oauth import views

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
    # django-oauth-toolkit endpoints.
    path(
        "o/authorize/",
        oauth2_views.AuthorizationView.as_view(),
        name="oauth2_authorize",
    ),
    path(
        "o/token/",
        oauth2_views.TokenView.as_view(),
        name="oauth2_token",
    ),
    path(
        "o/revoke_token/",
        oauth2_views.RevokeTokenView.as_view(),
        name="oauth2_revoke_token",
    ),
    path(
        "o/introspect/",
        oauth2_views.IntrospectTokenView.as_view(),
        name="oauth2_introspect",
    ),
    path(
        "o/.well-known/jwks.json",
        oauth2_views.JwksInfoView.as_view(),
        name="oauth2_jwks",
    ),
]
