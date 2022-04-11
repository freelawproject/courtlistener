import os
import sys
from pathlib import Path
from typing import List

import environ

env = environ.FileAwareEnv(
    ALLOWED_HOSTS=(list, []),
)
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS: List[str] = env("ALLOWED_HOSTS")

INSTALL_ROOT = Path(__file__).resolve().parents[1]
STATICFILES_DIRS = (os.path.join(INSTALL_ROOT, "cl/assets/static-global/"),)

# Where should the bulk data be stored?
BULK_DATA_DIR = os.path.join(INSTALL_ROOT, "cl/assets/media/bulk-data/")

SITE_ROOT = environ.Path("__file__") - 1
DEBUG = env.bool("DEBUG", default=True)
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)
MEDIA_ROOT = SITE_ROOT.path("cl/assets/media/")
STATIC_URL = env.str("STATIC_URL", default="static/")
STATIC_ROOT = SITE_ROOT.path("cl/assets/static/")
TEMPLATE_ROOT = SITE_ROOT.path("cl/assets/templates/")
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

TESTING = "test" in sys.argv
TEST_RUNNER = "cl.tests.runner.TestRunner"
if TESTING:
    PAGINATION_COUNT = 10
    DEBUG = False
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]
    CELERY_BROKER = "memory://"


if not any([TESTING, DEBUG]):
    STATICFILES_STORAGE = "cl.lib.storage.SubDirectoryS3ManifestStaticStorage"


MAINTENANCE_MODE_ENABLED = False
MAINTENANCE_MODE_ALLOW_STAFF = True
MAINTENANCE_MODE_ALLOWED_IPS = []
MAINTENANCE_MODE = {
    "enabled": MAINTENANCE_MODE_ENABLED,
    "allow_staff": MAINTENANCE_MODE_ALLOW_STAFF,
    "allowed_ips": MAINTENANCE_MODE_ALLOWED_IPS,
}

PLAUSIBLE_API_URL = "https://plausible.io/api/v1/stats/breakdown"


################
# Misc. Django #
################
SITE_ID = 1
USE_I18N = False
DEFAULT_CHARSET = "utf-8"
LANGUAGE_CODE = "en-us"
USE_TZ = True
DATETIME_FORMAT = "N j, Y, P e"
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10240

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            # Don't forget to use absolute paths, not relative paths.
            str(TEMPLATE_ROOT),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": (
                "django.contrib.messages.context_processors.messages",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.request",
                "django.template.context_processors.static",
                "cl.lib.context_processors.inject_settings",
                "cl.lib.context_processors.inject_random_tip",
            ),
            "debug": DEBUG,
        },
    }
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "ratelimit.middleware.RatelimitMiddleware",
    "waffle.middleware.WaffleMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "cl.lib.middleware.MaintenanceModeMiddleware",
]

ROOT_URLCONF = "cl.urls"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.admindocs",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.humanize",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "corsheaders",
    "hcaptcha",
    "markdown_deux",
    "mathfilters",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "storages",
    "waffle",
    # CourtListener Apps
    "cl.alerts",
    "cl.audio",
    "cl.api",
    "cl.citations",
    "cl.corpus_importer",
    "cl.custom_filters",
    "cl.disclosures",
    "cl.donate",
    "cl.favorites",
    "cl.people_db",
    "cl.lasc",
    "cl.lib",
    "cl.opinion_page",
    "cl.recap",
    "cl.recap_rss",
    "cl.scrapers",
    "cl.search",
    "cl.simple_pages",
    "cl.stats",
    "cl.users",
    "cl.visualizations",
]

if DEVELOPMENT:
    INSTALLED_APPS.append("django_extensions")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", default="courtlistener"),
        "USER": env("DB_USER", default="postgres"),
        "PASSWORD": env("DB_PASSWORD", default="postgres"),
        "CONN_MAX_AGE": env("DB_CONN_MAX_AGE", default=0),
        "HOST": env("DB_HOST", default="cl-postgresql"),
    },
}


############
# Security #
############
SECURE_BROWSER_XSS_FILTER = True
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
    # INSTALLED_APPS.append('debug_toolbar')
    INTERNAL_IPS = ("127.0.0.1",)

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

##########
# Waffle #
##########
WAFFLE_CREATE_MISSING_FLAGS = True
WAFFLE_CREATE_MISSING_SWITCHES = True
WAFFLE_CREATE_MISSING_SAMPLES = True


try:
    from judge_pics import judge_root
except ImportError:
    # When we're not in the full docker env, just fake it. Useful for e.g. mypy
    # Use random phrase to prevent access to root!
    judge_root = "/dummy-directory-john-stingily-granite/"
