import environ
from django.core.exceptions import ImproperlyConfigured

from ..project.testing import TESTING

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)

OIDC_RSA_PRIVATE_KEY = env("OIDC_RSA_PRIVATE_KEY", default="").replace(
    "\\n", "\n"
)

OAUTH2_DCR_RATELIMIT = env("OAUTH2_DCR_RATELIMIT", default="20000/h")

if not OIDC_RSA_PRIVATE_KEY and not DEVELOPMENT and not TESTING:
    raise ImproperlyConfigured(
        "OIDC_RSA_PRIVATE_KEY must be set in production. Generate one "
        "with 'openssl genrsa 4096' and store the PEM in the env var."
    )

OAUTH2_PROVIDER = {
    "SCOPES": {
        "api": "Access the CourtListener API on your behalf",
        "openid": "OpenID Connect identity",
        # Consumed by the Free Law wiki, not by CourtListener itself:
        # the wiki's JSON API introspects CL-issued tokens and requires
        # this scope before serving anything beyond public pages, so a
        # token authorized only for the CL API can't be replayed there
        # (and the authorize screen names the wiki access explicitly).
        "wiki:read": "Read Free Law wiki pages you have access to",
    },
    "DEFAULT_SCOPES": ["api"],
    "PKCE_REQUIRED": True,
    "ACCESS_TOKEN_EXPIRE_SECONDS": 60 * 60,  # 1 hour
    "REFRESH_TOKEN_EXPIRE_SECONDS": 60 * 60 * 24 * 30,  # 30 days
    # Adds email/email_verified claims to userinfo for downstream
    # resource servers (the Free Law wiki). See cl/oauth/validators.py.
    "OAUTH2_VALIDATOR_CLASS": "cl.oauth.validators.ResourceServerClaimsValidator",
    "OIDC_ENABLED": bool(OIDC_RSA_PRIVATE_KEY),
    "OIDC_RSA_PRIVATE_KEY": OIDC_RSA_PRIVATE_KEY,
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
    "CLIENT_SECRET_GENERATOR_LENGTH": 128,
    "ERROR_RESPONSE_WITH_SCOPES": False,
}
