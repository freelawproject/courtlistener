# type: ignore

import environ
from django.http import UnreadablePostError

from cl.lib.redis_utils import get_redis_interface

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)


def skip_unreadable_post(record):
    if record.exc_info:
        exc_value = record.exc_info[1]
        if isinstance(exc_value, UnreadablePostError):
            cache_key = "settings.unreadable_post_error"
            r = get_redis_interface("CACHE")
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
        # Juriscraper's logger is called "Logger"
        # CRITICAL is the highest log level, which will make the logger
        # reject most logger calls from juriscraper: debug, info and warning
        # This level may be modified on a VerboseCommand call with the
        # proper verbosity value
        "Logger": {
            "handlers": ["console"],
            "propagate": True,
            "level": "CRITICAL",
        },
    },
}

if DEVELOPMENT:
    # Log SQL queries
    LOGGING["loggers"]["django.db.backends"] = {
        "handlers": ["console"],
        "level": "DEBUG",
        "propagate": False,
    }
    # Verbose logs for devs
    LOGGING["handlers"]["console"]["formatter"] = "verbose"
