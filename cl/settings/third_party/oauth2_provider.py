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
    },
    "DEFAULT_SCOPES": ["api"],
    "PKCE_REQUIRED": True,
    "ACCESS_TOKEN_EXPIRE_SECONDS": 60 * 60,  # 1 hour
    "REFRESH_TOKEN_EXPIRE_SECONDS": 60 * 60 * 24 * 30,  # 30 days
    "OIDC_ENABLED": bool(OIDC_RSA_PRIVATE_KEY),
    "OIDC_RSA_PRIVATE_KEY": OIDC_RSA_PRIVATE_KEY,
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
    "CLIENT_SECRET_GENERATOR_LENGTH": 128,
    "ERROR_RESPONSE_WITH_SCOPES": False,
}
