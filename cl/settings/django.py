from pathlib import Path
from typing import List

import environ
from django.contrib.messages import constants as message_constants

from .project.testing import TESTING
from .third_party.redis import REDIS_DATABASES, REDIS_HOST, REDIS_PORT

env = environ.FileAwareEnv()

SECRET_KEY = env("SECRET_KEY", default="THIS-is-a-Secret")


############
# Database #
############
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", default="courtlistener"),
        "USER": env("DB_USER", default="postgres"),
        "PASSWORD": env("DB_PASSWORD", default="postgres"),
        "CONN_MAX_AGE": env("DB_CONN_MAX_AGE", default=0),
        "HOST": env("DB_HOST", default="cl-postgres"),
        # Disable DB serialization during tests for small speed boost
        "TEST": {"SERIALIZE": False},
        "OPTIONS": {
            # See: https://www.postgresql.org/docs/current/libpq-ssl.html#LIBPQ-SSL-PROTECTION
            # "prefer" is fine in dev, but poor in prod, where it should be
            # "require" or above.
            "sslmode": env("DB_SSL_MODE", default="prefer"),
        },
    },
}
if env("DB_REPLICA_HOST", default=""):
    DATABASES["replica"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_REPLICA_NAME", default="courtlistener"),
        "USER": env("DB_REPLICA_USER", default="postgres"),
        "PASSWORD": env("DB_REPLICA_PASSWORD", default="postgres"),
        "HOST": env("DB_REPLICA_HOST", default=""),
        "PORT": "",
        "CONN_MAX_AGE": env("DB_REPLICA_CONN_MAX_AGE", default=0),
        "OPTIONS": {
            "sslmode": env("DB_REPLICA_SSL_MODE", default="prefer"),
        },
    }

MAX_REPLICATION_LAG = env.int("MAX_REPLICATION_LAG", default=1e8)  # 100MB
API_READ_DATABASES: List[str] = env("API_READ_DATABASES", default="replica")


####################
# Cache & Sessions #
####################
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}",
        "OPTIONS": {"db": REDIS_DATABASES["CACHE"]},
    },
    "db_cache": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
        "OPTIONS": {"MAX_ENTRIES": 2.5e5},
    },
}
# This sets Redis as the session backend. This is often advised against, but we
# have pretty good persistency in Redis, so it's fairly well backed up.
SESSION_ENGINE = "django.contrib.sessions.backends.cache"


#####################################
# Directories, Apps, and Middleware #
#####################################
INSTALL_ROOT = Path(__file__).resolve().parents[2]
STATICFILES_DIRS = (INSTALL_ROOT / "cl/assets/static-global/",)
DEBUG = env.bool("DEBUG", default=True)
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)
MEDIA_ROOT = env("MEDIA_ROOT", default=INSTALL_ROOT / "cl/assets/media/")
STATIC_URL = env.str("STATIC_URL", default="static/")
STATIC_ROOT = INSTALL_ROOT / "cl/assets/static/"
TEMPLATE_ROOT = INSTALL_ROOT / "cl/assets/templates/"

if not any([TESTING, DEBUG]):
    STORAGES = {
        "staticfiles": {
            "BACKEND": "cl.lib.storage.SubDirectoryS3ManifestStaticStorage",
        },
    }

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
                "cl.lib.context_processors.inject_email_ban_status",
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
    "django_ratelimit.middleware.RatelimitMiddleware",
    "waffle.middleware.WaffleMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "cl.lib.middleware.RobotsHeaderMiddleware",
    "cl.lib.middleware.MaintenanceModeMiddleware",
    "pghistory.middleware.HistoryMiddleware",
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
    "admin_cursor_paginator",
    "pghistory",
    "pgtrigger",
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
    MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")


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

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = env("TIMEZONE", default="America/Los_Angeles")

MANAGERS = [
    (
        env("MANAGER_NAME", default="Joe Schmoe"),
        env("MANAGER_EMAIL", default="joe@courtlistener.com"),
    )
]


LOGIN_URL = "/sign-in/"
LOGIN_REDIRECT_URL = "/"

# These remap some of the the messages constants to correspond with bootstrap
MESSAGE_TAGS = {
    message_constants.DEBUG: "alert-warning",
    message_constants.INFO: "alert-info",
    message_constants.SUCCESS: "alert-success",
    message_constants.WARNING: "alert-warning",
    message_constants.ERROR: "alert-danger",
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

SILENCED_SYSTEM_CHECKS = [
    # Allow index names >30 characters, because we aren’t using Oracle
    "models.E034",
    # Don't warn about HSTS being used
    "security.W004",
]
