import environ
from django.core.exceptions import ImproperlyConfigured

from ..project.testing import TESTING

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)

# The private key used to sign OIDC ID tokens. Generate with::
#
#     openssl genrsa 4096
#
# and store the full PEM (including the BEGIN/END lines) in the env
# var. It is fine for DEVELOPMENT boots to have no key — OIDC will
# be disabled in that case. In prod we refuse to start without it.
OIDC_RSA_PRIVATE_KEY = env("OIDC_RSA_PRIVATE_KEY", default="")

if not OIDC_RSA_PRIVATE_KEY and not DEVELOPMENT and not TESTING:
    raise ImproperlyConfigured(
        "OIDC_RSA_PRIVATE_KEY must be set in production. Generate one "
        "with 'openssl genrsa 4096' and store the PEM in the env var."
    )

OAUTH2_PROVIDER = {
    # Scopes advertised to clients. Keep this narrow; CourtListener's
    # API authorizes per-viewset and per-object, not per-scope, so a
    # single "api" scope is sufficient for now.
    "SCOPES": {
        "api": "Access the CourtListener API on your behalf",
        "openid": "OpenID Connect identity",
    },
    "DEFAULT_SCOPES": ["api"],
    # MCP clients must use PKCE (RFC 7636). django-oauth-toolkit
    # enforces this for every authorization-code flow when True.
    "PKCE_REQUIRED": True,
    # Short-lived access tokens + longer refresh tokens. MCP clients
    # are expected to refresh frequently.
    "ACCESS_TOKEN_EXPIRE_SECONDS": 60 * 60,  # 1 hour
    "REFRESH_TOKEN_EXPIRE_SECONDS": 60 * 60 * 24 * 30,  # 30 days
    # OIDC gives us /o/.well-known/openid-configuration and
    # /o/.well-known/jwks.json for free when a signing key is
    # configured.
    "OIDC_ENABLED": bool(OIDC_RSA_PRIVATE_KEY),
    "OIDC_RSA_PRIVATE_KEY": OIDC_RSA_PRIVATE_KEY,
    # Redirect URI scheme allowlist. The RFC 7591 DCR view in
    # cl.oauth.views additionally enforces that any http:// URI must
    # be loopback (RFC 8252).
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
    # Hash stored client secrets. DOT returns the plaintext on the
    # create() response instance so DCR can echo it once.
    "CLIENT_SECRET_GENERATOR_LENGTH": 128,
    # Let authenticated users revoke their own tokens via the DOT
    # "authorized tokens" UI.
    "ERROR_RESPONSE_WITH_SCOPES": False,
}
