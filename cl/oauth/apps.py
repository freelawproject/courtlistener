from django.apps import AppConfig


class OAuthConfig(AppConfig):
    name = "cl.oauth"
    verbose_name = "OAuth"

    def ready(self) -> None:
        from cl.oauth import signals  # noqa: F401

        self._restrict_pkce_to_s256()

    @staticmethod
    def _restrict_pkce_to_s256() -> None:
        """Narrow oauthlib's PKCE method set to S256 only.

        django-oauth-toolkit 3.2 exposes no setting to restrict which
        PKCE transformation method is accepted; its ``PKCE_REQUIRED``
        only checks for the presence of a ``code_challenge``. oauthlib
        defaults a missing ``code_challenge_method`` to ``"plain"``
        (see ``oauthlib/oauth2/rfc6749/grant_types/authorization_code.py``),
        which would let a client bypass the S256-only promise we make
        in the RFC 8414 metadata by omitting the method or explicitly
        sending ``plain``. Removing ``plain`` from oauthlib's method
        dict makes its own ``UnsupportedCodeChallengeMethodError`` fire
        for any non-S256 authorization request.

        The assertion surfaces oauthlib internal renames at boot rather
        than as a silent security regression.
        """
        from oauthlib.oauth2.rfc6749.grant_types.authorization_code import (
            AuthorizationCodeGrant,
        )

        methods = AuthorizationCodeGrant._code_challenge_methods
        if set(methods) == {"S256"}:
            return
        assert "S256" in methods, (
            "oauthlib API changed; revisit PKCE S256-only enforcement"
        )
        AuthorizationCodeGrant._code_challenge_methods = {
            "S256": methods["S256"]
        }
