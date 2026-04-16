from django.urls import path

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
]
