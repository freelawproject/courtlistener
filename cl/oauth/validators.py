"""OAuth2 request validator for CourtListener."""

from collections.abc import Callable
from typing import Any

from django.conf import settings
from oauth2_provider.oauth2_validators import OAuth2Validator


def supported_scopes() -> list[str]:
    """Every scope the server can grant, leaving out the OIDC scopes when OIDC is off."""
    oidc_enabled = settings.OAUTH2_PROVIDER.get("OIDC_ENABLED")
    return [
        scope
        for scope in settings.OAUTH2_PROVIDER["SCOPES"]
        if oidc_enabled or scope not in settings.OIDC_SCOPES
    ]


def _is_legacy_dcr(client: Any) -> bool:
    """Whether ``client`` was created through the retired DCR endpoint."""
    return client.registration_source == client.RegistrationSource.DCR


class CourtListenerOAuth2Validator(OAuth2Validator):
    """Adds the standard OIDC ``email`` and ``profile`` claims and grants legacy DCR applications every scope.

    Applications registered through the retired DCR endpoint keep asking for
    the scopes they first connected with, and their users can't change that.
    They are granted every supported scope instead, both when a user
    authorizes them and on every refresh, so existing connections pick up
    new scopes without reconnecting.
    """

    def validate_scopes(
        self,
        client_id: str,
        scopes: list[str],
        client: Any,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Widen a legacy DCR application's authorization to every supported scope.

        Setting ``request.scopes`` carries through the rest of the
        authorization: the consent screen lists every scope and the grant
        covers them.
        """
        if _is_legacy_dcr(client):
            scopes = request.scopes = supported_scopes()
        return super().validate_scopes(
            client_id, scopes, client, request, *args, **kwargs
        )

    def validate_refresh_token(
        self,
        refresh_token: str,
        client: Any,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Make a legacy DCR application's refresh fall back to its original scopes.

        Dropping any requested ``scope`` sends oauthlib to
        ``get_original_scopes``, which reports every supported scope for these
        applications, so a refresh can't narrow the grant.
        """
        if not super().validate_refresh_token(
            refresh_token, client, request, *args, **kwargs
        ):
            return False
        if _is_legacy_dcr(client):
            request.scope = None
        return True

    def get_original_scopes(
        self, refresh_token: str, request: Any, *args: Any, **kwargs: Any
    ) -> Any:
        """Report every supported scope for a legacy DCR application's refresh token.

        oauthlib issues the refreshed token with these scopes, which is how
        existing connections pick up scopes added since they authorized.
        """
        if _is_legacy_dcr(request.client):
            return supported_scopes()
        return super().get_original_scopes(
            refresh_token, request, *args, **kwargs
        )

    # Request-free signature is how DOT opts claims into discovery.
    def get_additional_claims(  # pyrefly: ignore[bad-override]
        self,
    ) -> dict[str, Callable[[Any], Any]]:
        """Claims released alongside ``sub``, gated by scope in DOT."""
        return {
            "name": lambda r: r.user.get_full_name(),
            "given_name": lambda r: r.user.first_name,
            "family_name": lambda r: r.user.last_name,
            "email": lambda r: r.user.email,
            "email_verified": lambda r: r.user.profile.email_confirmed,
        }

    def get_oidc_claims(
        self, token: Any, token_handler: Any, request: Any
    ) -> dict[str, Any]:
        """Scope-filtered claims with empty values omitted.

        ``email_verified`` is only released alongside ``email``.
        """
        claims = super().get_oidc_claims(token, token_handler, request)
        claims = {k: v for k, v in claims.items() if v not in (None, "")}
        if "email" not in claims:
            claims.pop("email_verified", None)
        return claims
