"""OIDC claim customization for downstream resource servers.

Sketch for the wiki-tools-in-MCP design (freelawproject/wiki#136): the
Free Law wiki accepts CL-issued bearer tokens on its JSON API
(freelawproject/wiki, ``wiki/lib/cl_oauth.py``). It validates a token
with ``/o/introspect/`` and then reads the account email from
``/o/userinfo/`` to map the token to its own user table. Email is the
join key between the two systems, so userinfo must expose it — which
stock django-oauth-toolkit doesn't do without a custom validator.
"""

from typing import Any

from oauth2_provider.oauth2_validators import OAuth2Validator
from oauthlib.common import Request


class ResourceServerClaimsValidator(OAuth2Validator):
    """Expose email claims through ``/o/userinfo/``.

    Only verified addresses are trustworthy: consumers MUST treat
    ``email_verified: false`` as no identity at all (the wiki does).

    ``oidc_claim_scope = None`` disables DOT's per-claim scope gating,
    serving these claims to any token that can reach userinfo at all
    (i.e. one carrying ``openid``). If the claim set ever grows beyond
    email, reinstate gating with a claim→scope map instead.
    """

    oidc_claim_scope = None

    def get_additional_claims(self, request: Request) -> dict[str, Any]:
        user = request.user
        return {
            "email": user.email,
            "email_verified": user.profile.email_confirmed,
        }
