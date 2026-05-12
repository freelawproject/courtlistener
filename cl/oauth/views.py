"""OAuth 2.1 / MCP compatibility endpoints.

These sit alongside the endpoints that ``django-oauth-toolkit`` (DOT)
provides under ``/o/`` (authorize, token, revoke, introspect, OIDC
discovery, JWKS). They add:

* RFC 7591 Dynamic Client Registration at ``/o/register/`` so MCP
  clients can self-register without a human filling out a form.
* RFC 8414 Authorization Server Metadata at
  ``/.well-known/oauth-authorization-server`` so MCP clients can
  discover our endpoints.
"""

import uuid
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from oauth2_provider.models import get_application_model
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from cl.lib.ratelimiter import get_ip_for_ratelimiter
from cl.oauth.api_serializers import (
    ALLOWED_GRANT_TYPES,
    ALLOWED_RESPONSE_TYPES,
    ALLOWED_TOKEN_AUTH_METHODS,
    DynamicClientRegistrationSerializer,
    first_error_description,
)

Application = get_application_model()


def _invalid_metadata(description: str) -> Response:
    return Response(
        {
            "error": "invalid_client_metadata",
            "error_description": description,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def get_dcr_rate(group: str, request: Request) -> str:
    return settings.OAUTH2_DCR_RATELIMIT


@method_decorator(
    ratelimit(
        key=get_ip_for_ratelimiter,
        rate=get_dcr_rate,
        block=True,
        method="POST",
    ),
    name="post",
)
class DynamicClientRegistrationView(APIView):
    """RFC 7591 Dynamic Client Registration endpoint.

    Open registration: anyone on the internet may POST to this
    endpoint to create an OAuth client. This is required by the MCP
    authorization spec so that clients the server has never seen
    before can self-register. The resulting client is useless until a
    real user completes the authorization-code flow and grants
    consent, so the abuse surface is DB pollution, which we bound
    with a per-IP rate limit.
    """

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, Ratelimited):
            return Response(
                {
                    "error": "rate_limited",
                    "error_description": (
                        "Too many client registrations from this IP; "
                        "try again later."
                    ),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return super().handle_exception(exc)

    def post(self, request: Request) -> Response:
        serializer = DynamicClientRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return _invalid_metadata(
                first_error_description(serializer.errors)
            )

        data = serializer.validated_data
        token_endpoint_auth_method = data["token_endpoint_auth_method"]
        client_name = (
            data.get("client_name") or f"MCP Client {uuid.uuid4().hex[:8]}"
        )
        client_type = (
            Application.CLIENT_PUBLIC
            if token_endpoint_auth_method == "none"
            else Application.CLIENT_CONFIDENTIAL
        )

        app = Application(
            name=client_name,
            client_type=client_type,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=" ".join(data["redirect_uris"]),
            algorithm=Application.RS256_ALGORITHM,
            skip_authorization=False,
        )
        # Capture the plaintext BEFORE save() hashes it in place.
        client_secret_plaintext = app.client_secret
        app.save()

        response_data: dict[str, Any] = {
            "client_id": app.client_id,
            "client_name": client_name,
            "redirect_uris": data["redirect_uris"],
            "grant_types": data["grant_types"],
            "response_types": data["response_types"],
            "token_endpoint_auth_method": token_endpoint_auth_method,
            "client_id_issued_at": int(timezone.now().timestamp()),
        }
        if client_type == Application.CLIENT_CONFIDENTIAL:
            response_data["client_secret"] = client_secret_plaintext
            response_data["client_secret_expires_at"] = 0
        return Response(response_data, status=status.HTTP_201_CREATED)


class OAuthMetadataView(APIView):
    """RFC 8414 OAuth 2.0 Authorization Server Metadata.

    MCP clients fetch this from
    ``https://<issuer>/.well-known/oauth-authorization-server`` and
    use it to discover the authorize, token, registration, and JWKS
    endpoints.

    The issuer is derived from the incoming request so the same code
    serves the right URLs for ``courtlistener.com``, staging, and any
    other host in ``ALLOWED_HOSTS``.
    """

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        base = request.build_absolute_uri("/").rstrip("/")
        scopes_supported = ["api"]
        if settings.OAUTH2_PROVIDER.get("OIDC_ENABLED"):
            scopes_supported.append("openid")
        return Response(
            {
                "issuer": base,
                "authorization_endpoint": base
                + reverse("oauth2_provider:authorize"),
                "token_endpoint": base + reverse("oauth2_provider:token"),
                "registration_endpoint": base + reverse("oauth2_dcr"),
                "revocation_endpoint": base
                + reverse("oauth2_provider:revoke-token"),
                "introspection_endpoint": base
                + reverse("oauth2_provider:introspect"),
                "userinfo_endpoint": base
                + reverse("oauth2_provider:user-info"),
                "jwks_uri": base + reverse("oauth2_provider:jwks-info"),
                "response_types_supported": sorted(ALLOWED_RESPONSE_TYPES),
                "grant_types_supported": sorted(ALLOWED_GRANT_TYPES),
                "token_endpoint_auth_methods_supported": sorted(
                    ALLOWED_TOKEN_AUTH_METHODS
                ),
                "code_challenge_methods_supported": ["S256"],
                "scopes_supported": scopes_supported,
                "service_documentation": f"{settings.WIKI_API_BASE_URL}/rest/v4/overview",
            }
        )
