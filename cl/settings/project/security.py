import socket

import environ

from ..django import DATABASES, INSTALLED_APPS, TESTING

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)

ALLOWED_HOSTS: list[str] = env(
    "ALLOWED_HOSTS", default=["www.courtlistener.com"]
)

EGRESS_PROXY_HOST = env(
    "EGRESS_PROXY_HOST", default="http://cl-webhook-sentry:9090"
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
    # For debug_toolbar
    INSTALLED_APPS.append("debug_toolbar")

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
