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

import ipaddress
import uuid
from typing import Any
from urllib.parse import urlparse

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

Application = get_application_model()

# Only these grant types may be requested via DCR. Client-credentials,
# password, and device-code grants are intentionally excluded — MCP
# clients are confidential or public user-agent apps using the
# authorization-code + PKCE flow.
ALLOWED_GRANT_TYPES = {"authorization_code", "refresh_token"}
ALLOWED_RESPONSE_TYPES = {"code"}
ALLOWED_TOKEN_AUTH_METHODS = {
    "client_secret_basic",
    "client_secret_post",
    "none",
}

# Hosts that are allowed as ``http://`` redirect targets. Everything
# else must use ``https://``. See RFC 8252 section 7.3 ("Loopback
# Interface Redirection").
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _is_loopback_host(host: str) -> bool:
    """Return True if ``host`` is a loopback interface per RFC 8252."""
    host = host.strip("[]").lower()
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_redirect_uris(uris: list[str]) -> str | None:
    """Return an error description, or None if all URIs are acceptable.

    ``https://`` is always allowed. ``http://`` is only allowed when
    the host is a loopback interface. Anything else (``ftp://``,
    ``javascript:``, ``http://evil.example.com``, bare strings) is
    rejected.
    """
    if not uris:
        return "redirect_uris is required and must be a non-empty list"
    if not isinstance(uris, list):
        return "redirect_uris must be a list of strings"
    for raw in uris:
        if not isinstance(raw, str) or not raw:
            return "redirect_uris entries must be non-empty strings"
        parsed = urlparse(raw)
        if parsed.scheme == "https":
            if not parsed.netloc:
                return f"redirect_uri missing host: {raw}"
            continue
        if parsed.scheme == "http":
            if not parsed.hostname or not _is_loopback_host(parsed.hostname):
                return (
                    "http:// redirect_uris are only permitted for "
                    f"loopback addresses (got {raw})"
                )
            continue
        return f"unsupported redirect_uri scheme: {raw}"
    return None


def _invalid_metadata(description: str) -> Response:
    return Response(
        {
            "error": "invalid_client_metadata",
            "error_description": description,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


@method_decorator(
    ratelimit(key="ip", rate="10/h", block=True, method="POST"),
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

    def handle_exception(self, exc):
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
        data = request.data if isinstance(request.data, dict) else {}

        redirect_uris = data.get("redirect_uris")
        if (err := _validate_redirect_uris(redirect_uris)) is not None:
            return _invalid_metadata(err)

        grant_types = data.get("grant_types") or ["authorization_code"]
        if not isinstance(grant_types, list) or not set(grant_types).issubset(
            ALLOWED_GRANT_TYPES
        ):
            return _invalid_metadata(
                "grant_types must be a subset of "
                f"{sorted(ALLOWED_GRANT_TYPES)}"
            )
        if "authorization_code" not in grant_types:
            return _invalid_metadata(
                "authorization_code grant type is required"
            )

        response_types = data.get("response_types") or ["code"]
        if not isinstance(response_types, list) or not set(
            response_types
        ).issubset(ALLOWED_RESPONSE_TYPES):
            return _invalid_metadata(
                "only the 'code' response_type is supported"
            )

        token_endpoint_auth_method = data.get(
            "token_endpoint_auth_method", "client_secret_basic"
        )
        if token_endpoint_auth_method not in ALLOWED_TOKEN_AUTH_METHODS:
            return _invalid_metadata(
                "token_endpoint_auth_method must be one of "
                f"{sorted(ALLOWED_TOKEN_AUTH_METHODS)}"
            )

        client_name = data.get("client_name") or (
            f"MCP Client {uuid.uuid4().hex[:8]}"
        )
        if not isinstance(client_name, str) or len(client_name) > 255:
            return _invalid_metadata(
                "client_name must be a string of at most 255 characters"
            )

        if token_endpoint_auth_method == "none":
            client_type = Application.CLIENT_PUBLIC
        else:
            client_type = Application.CLIENT_CONFIDENTIAL

        app = Application.objects.create(
            name=client_name,
            client_type=client_type,
            authorization_grant_type=(Application.GRANT_AUTHORIZATION_CODE),
            redirect_uris=" ".join(redirect_uris),
            algorithm=Application.RS256_ALGORITHM,
            skip_authorization=False,
        )

        response_data: dict[str, Any] = {
            "client_id": app.client_id,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "response_types": response_types,
            "token_endpoint_auth_method": token_endpoint_auth_method,
            "client_id_issued_at": int(timezone.now().timestamp()),
        }
        if client_type == Application.CLIENT_CONFIDENTIAL:
            # DOT hashes the secret on save and returns the plaintext
            # on the instance only for the duration of this request.
            response_data["client_secret"] = app.client_secret
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
                "jwks_uri": base + reverse("oauth2_provider:jwks-info"),
                "response_types_supported": ["code"],
                "grant_types_supported": [
                    "authorization_code",
                    "refresh_token",
                ],
                "token_endpoint_auth_methods_supported": [
                    "client_secret_basic",
                    "client_secret_post",
                    "none",
                ],
                "code_challenge_methods_supported": ["S256"],
                "scopes_supported": ["api"],
                "service_documentation": (base + "/help/api/rest/"),
            }
        )
