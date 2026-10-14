"""OAuth 2.1 / MCP compatibility endpoints.

These sit alongside the endpoints that ``django-oauth-toolkit`` (DOT)
provides under ``/o/`` (authorize, token, revoke, introspect, OIDC
discovery, JWKS). They add:

* RFC 7591 Dynamic Client Registration at ``/o/register/`` so MCP
  clients can self-register without a human filling out a form.
* RFC 8414 Authorization Server Metadata at
  ``/.well-known/oauth-authorization-server`` so MCP clients can
  discover our endpoints.
* Authorize and token views that hand clients registered through DCR
  over to the MCP server, which is their authorization server now,
  behind the ``oauth_dcr_clients_via_mcp`` flag.
"""

import base64
import binascii
import hashlib
import json
import uuid
from typing import Any, cast
from urllib.parse import parse_qs, unquote

import requests
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser, User
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    JsonResponse,
)
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from oauth2_provider import views as oauth2_views
from oauth2_provider.models import (
    AbstractAccessToken,
    get_access_token_model,
    get_application_model,
    revoke_access_token,
)
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from waffle import get_waffle_flag_model

from cl.lib.ratelimiter import get_ip_for_ratelimiter
from cl.oauth.api_serializers import (
    ALLOWED_GRANT_TYPES,
    ALLOWED_RESPONSE_TYPES,
    ALLOWED_TOKEN_AUTH_METHODS,
    DynamicClientRegistrationSerializer,
    first_error_description,
)
from cl.oauth.validators import CourtListenerOAuth2Validator

AccessToken = get_access_token_model()
Application = get_application_model()

DCR_CLIENTS_VIA_MCP_FLAG = "oauth_dcr_clients_via_mcp"
MCP_RELAY_TIMEOUT_SECONDS = 35


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
    throttle_classes: list[Any] = []

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
            registration_source=Application.RegistrationSource.DCR,
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


class AuthorizationView(oauth2_views.AuthorizationView):
    """DOT's authorize view, sending clients registered through DCR on to
    the MCP server when the flag is on for the user."""

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        if (url := mcp_authorize_url(request)) and migrating(request.user):
            return handoff(url)
        return super().dispatch(request, *args, **kwargs)


def mcp_authorize_url(request: HttpRequest) -> str | None:
    """The MCP server's authorize URL for a request from a client registered
    through DCR that asks for a redirect it registered, filling in its only
    registered redirect when the request names none, as DOT would."""
    app = Application.objects.filter(
        client_id=request.GET.get("client_id", ""),
        registration_source=Application.RegistrationSource.DCR,
    ).first()
    if app is None:
        return None
    query = request.GET.copy()
    if (
        "redirect_uri" not in query
        and len(uris := app.redirect_uris.split()) == 1
    ):
        query["redirect_uri"] = uris[0]
    if not app.redirect_uri_allowed(query.get("redirect_uri", "")):
        return None
    return f"{settings.OAUTH2_MCP_URL}/authorize?{query.urlencode()}"


def migrating(user: AbstractBaseUser | AnonymousUser) -> bool:
    """Whether the flag hands *user*'s DCR clients to the MCP server, going by
    its everyone, user, group, staff and superuser settings alone."""
    flag = get_waffle_flag_model().get(DCR_CLIENTS_VIA_MCP_FLAG)
    if not flag.pk:
        return False
    if isinstance(user, AnonymousUser):
        return bool(flag.everyone)
    return bool(flag.is_active_for_user(user))


def handoff(url: str) -> HttpResponse:
    """A page that sends the browser on to *url*, ending any redirect chain
    from a sign-in form that Chrome would hold to that form's form-action."""
    return HttpResponse(
        format_html('<meta http-equiv="refresh" content="0;url={}">', url),
        headers={"Cache-Control": "no-store"},
    )


class TokenView(oauth2_views.TokenView):
    """DOT's token view, which for clients registered through DCR relays what
    DOT can't serve to the MCP server and refuses refreshes for flagged users."""

    def post(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponse:
        body = request.body
        response = super().post(request, *args, **kwargs)
        client_id = client_id_of(request, body)
        if not handed_to_mcp(client_id):
            return response
        error = error_of(response)
        if error == "invalid_grant" or (
            error == "invalid_client"
            and not Application.objects.filter(client_id=client_id).exists()
        ):
            return relay_to_mcp(body, cast(str, client_id))
        if (token := minted_token(response)) is None or token.user is None:
            return response
        if not migrating(token.user):
            return response
        revoke_access_token(token)
        return invalid_grant()


def handed_to_mcp(client_id: str | None) -> bool:
    """Whether a token request is the MCP server's to serve: from a client
    registered through DCR, or whose registration was pruned."""
    if not client_id:
        return False
    return (
        not Application.objects.filter(client_id=client_id)
        .exclude(registration_source=Application.RegistrationSource.DCR)
        .exists()
    )


def client_id_of(request: HttpRequest, body: bytes) -> str | None:
    """The client id of a token request, from its body or HTTP Basic auth."""
    if client_id := parse_qs(body.decode(errors="replace")).get("client_id"):
        return client_id[0]
    scheme, _, credentials = request.META.get(
        "HTTP_AUTHORIZATION", ""
    ).partition(" ")
    if scheme.lower() != "basic":
        return None
    try:
        decoded = base64.b64decode(credentials, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None
    return unquote(decoded.partition(":")[0]) or None


def error_of(response: HttpResponse) -> str | None:
    """The OAuth error code of a failed token response."""
    if response.status_code == status.HTTP_200_OK:
        return None
    return json.loads(response.content).get("error")


def minted_token(response: HttpResponse) -> AbstractAccessToken | None:
    """The access token a successful token response just issued."""
    if response.status_code != status.HTTP_200_OK:
        return None
    raw = json.loads(response.content)["access_token"]
    checksum = hashlib.sha256(raw.encode()).hexdigest()
    return AccessToken.objects.select_related("user").get(
        token_checksum=checksum
    )


def invalid_grant() -> JsonResponse:
    """The refusal that makes a client drop its tokens and authorize again."""
    return JsonResponse(
        {"error": "invalid_grant"},
        status=status.HTTP_400_BAD_REQUEST,
        headers={"Cache-Control": "no-store"},
    )


def relay_to_mcp(body: bytes, client_id: str) -> HttpResponse:
    """Replay a token request at the MCP server."""
    form = parse_qs(body.decode(errors="replace"))
    form.setdefault("client_id", [client_id])
    form.pop("client_secret", None)
    try:
        upstream = requests.post(
            f"{settings.OAUTH2_MCP_URL}/token",
            data=form,
            timeout=MCP_RELAY_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return JsonResponse(
            {"error": "temporarily_unavailable"},
            status=status.HTTP_502_BAD_GATEWAY,
            headers={"Cache-Control": "no-store"},
        )
    return HttpResponse(
        upstream.content,
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type", "application/json"),
        headers={"Cache-Control": "no-store"},
    )


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
    use it to discover the authorize, token, registration, and JWKS
    endpoints.

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
        # Discovery serves dynamically registered clients, so advertise
        # only the scopes they are allowed to request.
        scopes_supported = [
            scope
            for scope in settings.OAUTH2_PROVIDER["SCOPES"]
            if scope in CourtListenerOAuth2Validator.DCR_SCOPES
            and (oidc_enabled or scope not in settings.OIDC_SCOPES)
        ]
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
                "authorization_response_iss_parameter_supported": bool(
                    settings.OAUTH2_PROVIDER.get(
                        "COMPLIANT_BCP_RFC9700_AUTHZ_RESPONSE_ISS"
                    )
                ),
                "scopes_supported": scopes_supported,
                "service_documentation": f"{settings.WIKI_API_BASE_URL}/rest/v4/overview",
            }
        )
