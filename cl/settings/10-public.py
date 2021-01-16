import datetime
import os
import re
import sys
from pathlib import Path

import sentry_sdk
from django.contrib.messages import constants as message_constants
from django.http import UnreadablePostError
from judge_pics import judge_root
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.redis import RedisIntegration

from cl.lib.redis_utils import make_redis_interface

INSTALL_ROOT = Path(__file__).resolve().parents[1]

MAINTENANCE_MODE_ENABLED = False
MAINTENANCE_MODE_ALLOW_STAFF = True
MAINTENANCE_MODE_ALLOWED_IPS = []
MAINTENANCE_MODE = {
    "enabled": MAINTENANCE_MODE_ENABLED,
    "allow_staff": MAINTENANCE_MODE_ALLOW_STAFF,
    "allowed_ips": MAINTENANCE_MODE_ALLOWED_IPS,
}

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
            os.path.join(INSTALL_ROOT, "cl/assets/templates/"),
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
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "ratelimit.middleware.RatelimitMiddleware",
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
    "markdown_deux",
    "mathfilters",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_swagger",
    "django_filters",
    "storages",
    # CourtListener Apps
    "cl.alerts",
    "cl.audio",
    "cl.api",
    "cl.citations",
    "cl.cleanup",
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


# This is where the @login_required decorator redirects. By default it's
# /accounts/login. Also where users are redirected after they login. Default:
# /account/profile
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

########
# Solr #
########
SOLR_OPINION_URL = "%s/solr/collection1" % SOLR_HOST
SOLR_AUDIO_URL = "%s/solr/audio" % SOLR_HOST
SOLR_PEOPLE_URL = "%s/solr/person" % SOLR_HOST
SOLR_RECAP_URL = "%s/solr/recap" % SOLR_RECAP_HOST
SOLR_URLS = {
    "audio.Audio": SOLR_AUDIO_URL,
    "people_db.Person": SOLR_PEOPLE_URL,
    "search.Docket": SOLR_RECAP_URL,
    "search.RECAPDocument": SOLR_RECAP_URL,
    "search.Opinion": SOLR_OPINION_URL,
    "search.OpinionCluster": SOLR_OPINION_URL,
}

SOLR_OPINION_TEST_CORE_NAME = "opinion_test"
SOLR_AUDIO_TEST_CORE_NAME = "audio_test"
SOLR_PEOPLE_TEST_CORE_NAME = "person_test"
SOLR_RECAP_TEST_CORE_NAME = "recap_test"

SOLR_OPINION_TEST_URL = "%s/solr/opinion_test" % SOLR_HOST
SOLR_AUDIO_TEST_URL = "%s/solr/audio_test" % SOLR_HOST
SOLR_PEOPLE_TEST_URL = "%s/solr/person_test" % SOLR_HOST
SOLR_RECAP_TEST_URL = "%s/solr/recap_test" % SOLR_RECAP_HOST
SOLR_TEST_URLS = {
    "audio.Audio": SOLR_AUDIO_TEST_URL,
    "people_db.Person": SOLR_PEOPLE_TEST_URL,
    "search.Docket": SOLR_RECAP_TEST_URL,
    "search.RECAPDocument": SOLR_RECAP_TEST_URL,
    "search.Opinion": SOLR_OPINION_TEST_URL,
    "search.OpinionCluster": SOLR_OPINION_TEST_URL,
}
SOLR_EXAMPLE_CORE_PATH = os.path.join(
    os.sep, "usr", "local", "solr", "example", "solr", "collection1"
)
SOLR_TEMP_CORE_PATH_LOCAL = os.path.join(os.sep, "tmp", "solr")
SOLR_TEMP_CORE_PATH_DOCKER = os.path.join(os.sep, "tmp", "solr")


#########
# Redis #
#########
# Redis is configured with 16 databases out of the box. This keeps them neatly
# mapped.
REDIS_DATABASES = {
    "CELERY": 0,
    "CACHE": 1,
    "STATS": 2,
    "ALERTS": 3,
}

##########
# CELERY #
##########
if DEVELOPMENT:
    # In a development machine, these setting make sense
    CELERY_WORKER_CONCURRENCY = 2
    # This makes the tasks run outside the async worker and is needed for tests
    # to pass
    CELERY_TASK_ALWAYS_EAGER = True
else:
    # Celery settings for production sites
    CELERY_WORKER_CONCURRENCY = 20
    CELERY_BROKER_POOL_LIMIT = 30
    CELERY_RESULT_EXPIRES = 60 * 60
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        # This is the length of time a task will wait to be acknowledged by a
        # worker. This value *must* be greater than the largest ETA/countdown
        # that a task may be assigned with, or else it will be run over and
        # over in a loop. Our countdowns never tend to exceed one hour.
        "visibility_timeout": (60 * 60 * 6),  # six hours
    }

CELERY_BROKER_URL = "redis://%s:%s/%s" % (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DATABASES["CELERY"],
)
CELERY_RESULT_BACKEND = "redis://%s:%s/%s" % (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DATABASES["CELERY"],
)

# Rate limits aren't ever used, so disable them across the board for better
# performance
CELERY_WORKER_DISABLE_RATE_LIMITS = True
# We could pass around JSON, but it's *much* easier to pass around Python
# objects that support things like dates. Let's do that, shall we?
CELERY_RESULT_SERIALIZER = "pickle"
CELERY_TASK_SERIALIZER = "pickle"
CELERY_ACCEPT_CONTENT = {"json", "pickle"}


####################
# Cache & Sessions #
####################
CACHES = {
    "default": {
        "BACKEND": "redis_cache.RedisCache",
        "LOCATION": "%s:%s" % (REDIS_HOST, REDIS_PORT),
        "OPTIONS": {"DB": REDIS_DATABASES["CACHE"], "MAX_ENTRIES": 1e5},
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

#########
# Email #
#########
if DEVELOPMENT:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

SERVER_EMAIL = "CourtListener <noreply@courtlistener.com>"
DEFAULT_FROM_EMAIL = "CourtListener <noreply@courtlistener.com>"
DEFAULT_ALERTS_EMAIL = "CourtListener Alerts <alerts@courtlistener.com>"
SCRAPER_ADMINS = (
    ("Slack Juriscraper Channel", "j9f4b5n5x7k8x2r1@flp-talk.slack.com"),
    ("PA", "arderyp@protonmail.com"),
)

###############
# Directories #
###############
MEDIA_ROOT = os.path.join(INSTALL_ROOT, "cl/assets/media/")
STATIC_URL = "/static/"
STATICFILES_DIRS = (
    os.path.join(INSTALL_ROOT, "cl/assets/static-global/"),
    ("judge_pics", os.path.join(judge_root, "256")),
)
# This is where things get collected to
STATIC_ROOT = os.path.join(INSTALL_ROOT, "cl/assets/static/")

# Where should the bulk data be stored?
BULK_DATA_DIR = os.path.join(INSTALL_ROOT, "cl/assets/media/bulk-data/")


#####################
# Payments & Prices #
#####################
MIN_DONATION = {
    "rt_alerts": 10,
    "docket_alerts": 5,
}
MAX_FREE_DOCKET_ALERTS = 5
DOCKET_ALERT_RECAP_BONUS = 10
MAX_ALERT_RESULTS_PER_DAY = 30
# If people pay via XERO invoices, this is the ID we see in our stripe
# callbacks
XERO_APPLICATION_ID = "ca_1pvP3rYcArUkd3InUnImFI9llOiSIq6k"


#######
# API #
#######
REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
    ],
    # Versioning
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v3",
    "ALLOWED_VERSIONS": {"v3"},
    # Throttles
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "cl.api.utils.ExceptionalUserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {"anon": "100/day", "user": "5000/hour"},
    "OVERRIDE_THROTTLE_RATES": {
        # Throttling down.
        # Doing a background check service, we told them we didn't want to work
        # with them.
        "elios": "10/hour",
        "shreyngd": "100/hour",
        "leo": "100/hour",
        "miffy": "100/hour",
        "safetynet": "100/hour",
        # Send multiple emails, but they haven't responded
        "linkfenzhao": "10/hour",
        # From fokal.ai, using multiple accounts to dodge limitations
        "manu.jose": "10/hour",
        "shishir": "10/hour",
        "shishir.kumar": "10/hour",
        # Throttling up.
        "YFIN": "430000/day",
        "mlissner": "1000000/hour",  # Needed for benchmarking (not greed)
        "gpilapil": "10000/hour",
        "peidelman": "20000/hour",
        "waldo": "10000/hour",
        "hdave4": "15000/hour",  # GSU
        "ellliottt": "15000/hour",
        "flooie": "20000/hour",  # Needed for testing
    },
    # Auth
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    # Rendering and Parsing
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework_xml.parsers.XMLParser",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
        "rest_framework_xml.renderers.XMLRenderer",
    ),
    # Filtering
    "DEFAULT_FILTER_BACKENDS": (
        # This is a tweaked version of RestFrameworkFilterBackend
        "cl.api.utils.DisabledHTMLFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    # Assorted & Sundry
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "URL_FIELD_NAME": "resource_uri",
    "DEFAULT_METADATA_CLASS": "cl.api.utils.SimpleMetadataWithFilters",
    "ORDERING_PARAM": "order_by",
    "HTML_SELECT_CUTOFF": 100,
    "UPLOADED_FILES_USE_URL": False,
}

if DEVELOPMENT:
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["anon"] = "10000/day"

# CORS
CORS_ORIGIN_ALLOW_ALL = True
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_METHODS = (
    "GET",
    "HEAD",
    "OPTIONS",
)
CORS_ALLOW_CREDENTIALS = True

############
# Markdown #
############
MARKDOWN_DEUX_STYLES = {
    "default": {
        "extras": {
            "code-friendly": None,
            "cuddled-lists": None,
            "footnotes": None,
            "header-ids": None,
            "link-patterns": None,
            "nofollow": None,
            "smarty-pants": None,
            "tables": None,
        },
        "safe_mode": "escape",
        "link_patterns": [
            (
                re.compile(r"network\s+#?(\d+)\b", re.I),
                r"/visualizations/scotus-mapper/\1/md/",
            ),
            (re.compile(r"opinion\s+#?(\d+)\b", re.I), r"/opinion/\1/md/"),
        ],
    },
}


##########
# MATOMO #
##########

MATOMO_URL = "http://192.168.0.243/piwik.php"
MATOMO_REPORT_URL = "http://192.168.0.243/"
MATOMO_FRONTEND_BASE_URL = "//matomo.courtlistener.com/"
MATOMO_SITE_ID = "1"

########
# SCDB #
########
# SCOTUS cases after this date aren't expected to have SCDB data.
SCDB_LATEST_CASE = datetime.datetime(2019, 6, 27)


############
# Security #
############
RATELIMIT_VIEW = "cl.simple_pages.views.ratelimited"
if DEVELOPMENT:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_DOMAIN = None
    # For debug_toolbar
    # INSTALLED_APPS.append('debug_toolbar')
    INTERNAL_IPS = ("127.0.0.1",)

    if "test" in sys.argv:
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

########################
# Logging Machinations #
########################
if not DEVELOPMENT:
    # IA's library logs a lot of errors, which get sent to sentry unnecessarily
    ignore_logger("internetarchive.session")
    ignore_logger("internetarchive.item")
    sentry_sdk.init(
        dsn="https://18f5941395e249f48e746dd7c6de84b1@o399720.ingest.sentry.io/5257254",
        integrations=[
            CeleryIntegration(),
            DjangoIntegration(),
            RedisIntegration(),
        ],
        ignore_errors=[KeyboardInterrupt],
    )


def skip_unreadable_post(record):
    if record.exc_info:
        exc_value = record.exc_info[1]
        if isinstance(exc_value, UnreadablePostError):
            cache_key = "settings.unreadable_post_error"
            r = make_redis_interface("CACHE")
            if r.get(cache_key) is not None:
                # We've seen this recently; let it through; hitting it a lot
                # might mean something.
                return True
            else:
                # Haven't seen this recently; cache it with a minute expiry,
                # and don't let it through.
                r.set(cache_key, "True", ex=60)
                return False
    return True


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "skip_unreadable_posts": {
            "()": "django.utils.log.CallbackFilter",
            "callback": skip_unreadable_post,
        },
    },
    "formatters": {
        "verbose": {
            "format": '%(levelname)s %(asctime)s (%(pathname)s %(funcName)s): "%(message)s"'
        },
        "simple": {"format": "%(levelname)s %(message)s"},
        "django.server": {
            "()": "django.utils.log.ServerFormatter",
            "format": "[%(server_time)s] %(message)s",
        },
    },
    "handlers": {
        "null": {"level": "DEBUG", "class": "logging.NullHandler"},
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["skip_unreadable_posts"],
        },
        # Use this if you're not yet dockerized. If dockerized, the stream
        # handler will send everything to stdout, which is what you want.
        "log_file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/courtlistener/django.log",
            "maxBytes": 16777216,  # 16 megabytes
            "formatter": "verbose",
            "filters": ["skip_unreadable_posts"],
        },
        "django.server": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "django.server",
            "filters": ["skip_unreadable_posts"],
        },
        "mail_admins": {"class": "logging.NullHandler"},
    },
    "loggers": {
        # Disable SuspiciousOperation.DisallowedHost exception ("Invalid
        # HTTP_HOST" header messages.) This appears to be caused by clients
        # that don't support SNI, and which are browsing to other domains on
        # the server. The most relevant bad client is the googlebot.
        "django.security.DisallowedHost": {
            "handlers": ["null"],
            "propagate": False,
        },
        "django.server": {
            "handlers": ["django.server"],
            "level": "INFO",
            "propagate": False,
        },
        # This is the one that's used practically everywhere in the code.
        "cl": {"handlers": ["console"], "level": "INFO", "propagate": True},
    },
}

if DEVELOPMENT:
    # Log SQL queries
    LOGGING["loggers"]["django.db.backends"] = {
        "handlers": ["console"],
        "level": "DEBUG",
        "propagate": False,
    }
    # Versbose logs for devs
    LOGGING["handlers"]["console"]["formatter"] = "verbose"

###################
# Related content #
###################

RELATED_COUNT = 5
RELATED_USE_CACHE = True
RELATED_CACHE_TIMEOUT = 60 * 60 * 24 * 7
RELATED_MLT_MAXQT = 10
RELATED_MLT_MINTF = 5
RELATED_MLT_MAXDF = 1000
RELATED_MLT_MINWL = 3
RELATED_MLT_MAXWL = 0
RELATED_FILTER_BY_STATUS = "Precedential"

#######
# AWS #
#######
AWS_STORAGE_BUCKET_NAME = "com-courtlistener-storage"
AWS_S3_CUSTOM_DOMAIN = "%s.s3.amazonaws.com" % AWS_STORAGE_BUCKET_NAME
AWS_DEFAULT_ACL = "public-read"
AWS_QUERYSTRING_AUTH = False

if DEVELOPMENT:
    AWS_STORAGE_BUCKET_NAME = "dev-com-courtlistener-storage"
    AWS_S3_CUSTOM_DOMAIN = "%s.s3.amazonaws.com" % AWS_STORAGE_BUCKET_NAME

CLOUDFRONT_DOMAIN = ""


####################################
# Binary Transformers & Extractors #
####################################
BTE_URLS = {
    # Testing
    "heartbeat": {"url": f"{BTE_HOST}", "timeout": 5},
    # Audio Processing
    # this should change but currently in a PR so will alter later
    "convert-audio": {"url": f"{BTE_HOST}/convert/audio", "timeout": 60 * 60},
    # Document processing
    "pdf-to-text": {
        "url": f"{BTE_HOST}/document/pdf_to_text",
        "timeout": 60 * 5,
    },
    "document-extract": {
        "url": f"{BTE_HOST}/document/extract_text",
        "timeout": 60 * 15,
    },
    "page-count": {"url": f"{BTE_HOST}/document/page_count", "timeout": 30},
    "thumbnail": {"url": f"{BTE_HOST}/document/thumbnail", "timeout": 30},
    "mime-type": {"url": f"{BTE_HOST}/document/mime_type", "timeout": 30},
    # Image conversion
    "images-to-pdf": {
        "url": f"{BTE_HOST}/financial_disclosure/images_to_pdf",
        "timeout": 60 * 10,
    },
    # Financial Disclosures
    "extract-disclosure": {
        "url": f"{BTE_HOST}/financial_disclosure/extract_record",
        "timeout": 60 * 60 * 12,
    },
    "extract-disclosure-jw": {
        "url": f"{BTE_HOST}/financial_disclosure/extract_jw",
        "timeout": 60 * 60 * 12,
    },
}
