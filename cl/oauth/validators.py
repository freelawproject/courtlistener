from collections.abc import Callable
from typing import Any

from django.contrib.auth.models import User
from oauth2_provider.oauth2_validators import OAuth2Validator


def _email_verified(user: User) -> bool:
    """Whether the user has confirmed their email; no profile counts as no."""
    profile = getattr(user, "profile", None)
    return bool(profile and profile.email_confirmed)


class CourtListenerOAuth2Validator(OAuth2Validator):
    """Adds the standard OIDC ``email`` and ``profile`` claims."""

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
            "email_verified": lambda r: _email_verified(r.user),
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
