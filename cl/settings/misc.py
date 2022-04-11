import datetime
from typing import List

import environ
from django.contrib.messages import constants as message_constants
from django.http import UnreadablePostError

from cl.lib.redis_utils import make_redis_interface

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)
TESTING = env.bool("TESTING", default=True)

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
# SCDB #
########
# SCOTUS cases after this date aren't expected to have SCDB data.
SCDB_LATEST_CASE = datetime.datetime(2019, 6, 27)

########################
# Logging Machinations #
########################
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

SILENCED_SYSTEM_CHECKS = [
    # Allow index names >30 characters, because we aren’t using Oracle
    "models.E034",
    # Don't warn about HSTS being used
    "security.W004",
]

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


###################
#     Private     #
###################


LASC_USERNAME = env("LASC_USERNAME", default="")
LASC_PASSWORD = env("LASC_PASSWORD", default="")

CL_API_TOKEN = env("CL_API_TOKEN", default="")

ADMINS = (
    env("ADMIN_NAME", default="Joe Schmoe"),
    env("ADMIN_EMAIL", default="joe@courtlistener.com"),
)

MANAGERS = ADMINS
API_READ_DATABASES: List[str] = env("API_READ_DATABASES", default="replica")


DOCKER_SELENIUM_HOST = env(
    "DOCKER_SELENIUM_HOST", default="http://cl-selenium:4444/wd/hub"
)
DOCKER_DJANGO_HOST = env("DOCKER_DJANGO_HOST", default="cl-django")

SELENIUM_HEADLESS = env.bool("SELENIUM_HEADLESS", default=False)

# PACER
PACER_USERNAME = env("PACER_USERNAME", default="")
PACER_PASSWORD = env("PACER_PASSWORD", default="")

# Internet Archive
IA_ACCESS_KEY = env("IA_ACCESS_KEY", default="")
IA_SECRET_KEY = env("IA_SECRET_KEY", default="")
IA_COLLECTIONS = []
IA_OA_COLLECTIONS: List[str] = env("IA_OA_COLLECTIONS", default=[])


# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = env("TIMEZONE", default="America/Los_Angeles")
