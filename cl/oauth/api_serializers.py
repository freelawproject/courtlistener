"""Serializers for OAuth endpoints.

Houses the RFC 7591 Dynamic Client Registration serializer used by
:class:`cl.oauth.views.DynamicClientRegistrationView`. The shared
allow-lists also live here so that both the DCR validator and the
RFC 8414 metadata view (which advertises them) import them from the
same place.
"""

import ipaddress
from typing import Any
from urllib.parse import urlparse

from rest_framework import serializers

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


def check_redirect_uri(uri: str) -> str | None:
    """Return an error message if ``uri`` is not an acceptable redirect
    target, else ``None``.

    Acceptable: any ``https://`` URI with a host, or an ``http://`` URI
    whose host is a loopback address (RFC 8252 §7.3). The DCR serializer
    and the ``Application`` pre_save signal both call this so admin-created
    apps can't bypass the loopback restriction.
    """
    parsed = urlparse(uri)
    if parsed.scheme == "https":
        if not parsed.netloc:
            return f"redirect_uri missing host: {uri}"
        return None
    if parsed.scheme == "http":
        if not parsed.hostname or not _is_loopback_host(parsed.hostname):
            return (
                "http:// redirect_uris are only permitted for "
                f"loopback addresses (got {uri})"
            )
        return None
    return f"unsupported redirect_uri scheme: {uri}"


class DynamicClientRegistrationSerializer(serializers.Serializer):
    """Validates RFC 7591 DCR POST bodies against the MCP-allowed subset.

    ``grant_types`` and ``response_types`` treat an omitted field and
    an explicit empty list the same way — both fall back to the RFC
    default inside the field-level validator.
    """

    redirect_uris = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        allow_empty=False,
    )
    grant_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    response_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    token_endpoint_auth_method = serializers.ChoiceField(
        choices=sorted(ALLOWED_TOKEN_AUTH_METHODS),
        required=False,
        default="client_secret_basic",
    )
    client_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )

    def validate_redirect_uris(self, value: list[str]) -> list[str]:
        for raw in value:
            error = check_redirect_uri(raw)
            if error:
                raise serializers.ValidationError(error)
        return value

    def validate_grant_types(self, value: list[str]) -> list[str]:
        if not value:
            value = ["authorization_code"]
        if not set(value).issubset(ALLOWED_GRANT_TYPES):
            raise serializers.ValidationError(
                "grant_types must be a subset of "
                f"{sorted(ALLOWED_GRANT_TYPES)}"
            )
        if "authorization_code" not in value:
            raise serializers.ValidationError(
                "authorization_code grant type is required"
            )
        return value

    def validate_response_types(self, value: list[str]) -> list[str]:
        if not value:
            value = ["code"]
        if not set(value).issubset(ALLOWED_RESPONSE_TYPES):
            raise serializers.ValidationError(
                "only the 'code' response_type is supported"
            )
        return value


def first_error_description(errors: Any) -> str:
    """Return the first human-readable message in DRF serializer errors.

    DCR wraps failures as RFC 7591 ``{error, error_description}``
    pairs, so we flatten DRF's nested errors structure (dicts of lists,
    possibly nested for list-of-dict fields) down to a single string.
    """
    if isinstance(errors, dict):
        for messages in errors.values():
            msg = first_error_description(messages)
            if msg:
                return msg
    elif isinstance(errors, list):
        for item in errors:
            msg = first_error_description(item)
            if msg:
                return msg
    elif errors:
        return str(errors)
    return "invalid client metadata"
