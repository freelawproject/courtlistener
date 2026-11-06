"""OAuth 2.1 / MCP compatibility endpoints.

These sit alongside the endpoints that ``django-oauth-toolkit`` (DOT)
provides under ``/o/`` (authorize, token, revoke, introspect, OIDC
discovery, JWKS). They add RFC 8414 Authorization Server Metadata at
``/.well-known/oauth-authorization-server`` so MCP clients can discover
our endpoints, and extend introspection with ``sub``.

Clients are registered by hand, or by the MCP server, which is its own
authorization server. RFC 7591 Dynamic Client Registration is gone;
applications it created live on with ``registration_source="dcr"``.
"""

import json
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.urls import reverse
from oauth2_provider import views as oauth2_views
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

# What the metadata advertises. Client-credentials, password, and
# device-code grants are intentionally left out: MCP clients are
# confidential or public user-agent apps using authorization-code + PKCE.
GRANT_TYPES_SUPPORTED = ["authorization_code", "refresh_token"]
RESPONSE_TYPES_SUPPORTED = ["code"]
TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED = [
    "client_secret_basic",
    "client_secret_post",
    "none",
]


class IntrospectTokenView(oauth2_views.IntrospectTokenView):
    """RFC 7662 introspection with the optional ``sub`` field.

    Resource servers that link accounts by OIDC ``sub`` need it here too,
    and the toolkit only returns ``username``.
    """

    @staticmethod
    def get_token_response(token_value: str | None = None) -> JsonResponse:
        response = oauth2_views.IntrospectTokenView.get_token_response(
            token_value
        )
        data = json.loads(response.content)
        if not data.get("active") or "username" not in data:
            return response
        pk = User.objects.values_list("pk", flat=True).get(
            username=data["username"]
        )
        data["sub"] = str(pk)
        return JsonResponse(data)


class OAuthMetadataView(APIView):
    """RFC 8414 OAuth 2.0 Authorization Server Metadata.

    MCP clients fetch this from
    ``https://<issuer>/.well-known/oauth-authorization-server`` and
    use it to discover the authorize, token, and JWKS endpoints.

    The issuer is derived from the incoming request so the same code
    serves the right URLs for ``courtlistener.com``, staging, and any
    other host in ``ALLOWED_HOSTS``.
    """

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []
    throttle_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        base = request.build_absolute_uri("/").rstrip("/")
        oidc_enabled = settings.OAUTH2_PROVIDER.get("OIDC_ENABLED")
        scopes_supported = [
            scope
            for scope in settings.OAUTH2_PROVIDER["SCOPES"]
            if oidc_enabled or scope not in settings.OIDC_SCOPES
        ]
        return Response(
            {
                "issuer": base,
                "authorization_endpoint": base
                + reverse("oauth2_provider:authorize"),
                "token_endpoint": base + reverse("oauth2_provider:token"),
                "revocation_endpoint": base
                + reverse("oauth2_provider:revoke-token"),
                "introspection_endpoint": base
                + reverse("oauth2_provider:introspect"),
                "userinfo_endpoint": base
                + reverse("oauth2_provider:user-info"),
                "jwks_uri": base + reverse("oauth2_provider:jwks-info"),
                "response_types_supported": RESPONSE_TYPES_SUPPORTED,
                "grant_types_supported": GRANT_TYPES_SUPPORTED,
                "token_endpoint_auth_methods_supported": (
                    TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED
                ),
                "code_challenge_methods_supported": ["S256"],
                "authorization_response_iss_parameter_supported": bool(
                    settings.OAUTH2_PROVIDER.get(
                        "COMPLIANT_BCP_RFC9700_AUTHZ_RESPONSE_ISS"
                    )
                ),
                "scopes_supported": scopes_supported,
                "service_documentation": f"{settings.WIKI_API_BASE_URL}/rest/v4/overview",
            }
        )
