from collections.abc import Callable
from typing import Any

from oauth2_provider.oauth2_validators import OAuth2Validator


class CourtListenerOAuth2Validator(OAuth2Validator):
    """Adds the standard OIDC ``email`` and ``profile`` claims and limits
    dynamically registered applications to the ``api`` and ``openid`` scopes.
    """

    DCR_SCOPES = frozenset({"api", "openid"})

    def validate_scopes(
        self,
        client_id: str,
        scopes: list[str],
        client: Any,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Refuse identity and wiki scopes to apps registered through DCR."""
        if (
            client.registration_source == client.RegistrationSource.DCR
            and not set(scopes) <= self.DCR_SCOPES
        ):
            return False
        return super().validate_scopes(
            client_id, scopes, client, request, *args, **kwargs
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
