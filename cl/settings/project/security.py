import socket

import environ
from csp.constants import NONCE, SELF

from ..django import DATABASES, INSTALLED_APPS, MIDDLEWARE, TESTING
from ..third_party.aws import AWS_S3_CUSTOM_DOMAIN

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)

SQLCOMMENTER_MAX_PATH_LENGTH = env.int("SQLCOMMENTER_MAX_PATH_LENGTH", 255)

PRIVACY_POLICY_CUTOFF_DAYS = env.int("PRIVACY_POLICY_CUTOFF_DAYS", 84)
ALLOWED_HOSTS: list[str] = env(
    "ALLOWED_HOSTS", default=["www.courtlistener.com"]
)

EGRESS_PROXY_HOSTS: list[str] = env.list(
    "EGRESS_PROXY_HOSTS", default=["http://cl-webhook-sentry:9090"]
)
WEBHOOK_EGRESS_PROXY_HOSTS: list[str] = env.list(
    "WEBHOOK_EGRESS_PROXY_HOSTS", default=["http://cl-webhook-sentry:9090"]
)


SECURE_HSTS_SECONDS = 63_072_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

RATELIMIT_VIEW = "cl.simple_pages.views.ratelimited"

if DEVELOPMENT:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_DOMAIN = None
    if not TESTING:
        # Install django-debug-toolbar
        INSTALLED_APPS.append("debug_toolbar")
        MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS = [".".join(ip.split(".")[:-1] + ["1"]) for ip in ips] + [
        "127.0.0.1"
    ]

    if TESTING:
        db = DATABASES["default"]
        db["ENCODING"] = "UTF8"
        db["TEST_ENCODING"] = "UTF8"
        db["CONN_MAX_AGE"] = 0
else:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 9,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# CORS
CORS_ALLOW_ALL_ORIGINS = True
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_METHODS = (
    "GET",
    "HEAD",
    "OPTIONS",
)
CORS_ALLOW_CREDENTIALS = True

# PERMISSIONS_POLICY
# Dictionary to disable many potentially privacy-invading and annoying features
# for all scripts:
PERMISSIONS_POLICY: dict[str, list[str]] = {
    "browsing-topics": [],
}

# CSP
# Components:
# - hCaptcha: https://docs.hcaptcha.com/#content-security-policy-settings
# - Plausible: https://github.com/plausible/docs/issues/20
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "connect-src": [
            SELF,
            f"https://{AWS_S3_CUSTOM_DOMAIN}/",  # for embedded PDFs
            "https://hcaptcha.com/",
            "https://*.hcaptcha.com/",
            "https://plausible.io/",
        ],
        "default-src": [SELF, f"https://{AWS_S3_CUSTOM_DOMAIN}/"],
        "script-src": [
            SELF,
            NONCE,
            "'report-sample'",
            f"https://{AWS_S3_CUSTOM_DOMAIN}/",
            "https://hcaptcha.com/",
            "https://*.hcaptcha.com/",
            "https://plausible.io/",
        ],
        "object-src": [
            SELF,
            f"https://{AWS_S3_CUSTOM_DOMAIN}/",  # for embedded PDFs
        ],
        "style-src": [
            SELF,
            "'report-sample'",
            f"https://{AWS_S3_CUSTOM_DOMAIN}/",
            "https://hcaptcha.com/",
            "https://*.hcaptcha.com/",
            "'unsafe-inline'",
        ],
        "font-src": [
            SELF,
            f"https://{AWS_S3_CUSTOM_DOMAIN}/",
            "data:",  # Some browser extensions like this.
        ],
        "frame-src": [
            SELF,
            f"https://{AWS_S3_CUSTOM_DOMAIN}/",  # for embedded PDFs
            "https://hcaptcha.com/",
            "https://*.hcaptcha.com/",
        ],
        "img-src": [
            SELF,
            f"https://{AWS_S3_CUSTOM_DOMAIN}/",
            "https://portraits.free.law/",
            "https://seals.free.law/",
            "data:",  # @tailwindcss/forms uses data URIs for images.
        ],
        "media-src": [
            SELF,
            f"https://{AWS_S3_CUSTOM_DOMAIN}/",
            "data:",  # Some browser extensions like this.
        ],
        "base-uri": [SELF],
        "upgrade-insecure-requests": False,
    }
}
if not any(
    (DEVELOPMENT, TESTING)
):  # Development and test aren’t used over HTTPS (yet)
    CONTENT_SECURITY_POLICY["DIRECTIVES"]["upgrade-insecure-requests"] = True
