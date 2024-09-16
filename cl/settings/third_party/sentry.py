import environ
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.redis import RedisIntegration

env = environ.FileAwareEnv()
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_REPORT_URI = env("SENTRY_REPORT_URI", default="")

# IA's library logs a lot of errors, which get sent to sentry unnecessarily
ignore_logger("internetarchive.session")
ignore_logger("internetarchive.item")


def fingerprint_sentry_error(event: dict, hint: dict) -> dict:
    """Captures fingerprint information from logger.error call, if present

    logger.error calls allow to pass an `extra` dictionary with arbitrary keys
    We use this to pass a `fingerprint` key. The value should be a list.
    For example:
    error.log(extra={"fingerprint": [court_id, "citation-not-found"]})

    By default, Sentry events are grouped into issues using Sentry's
    internal algorithms.
    By passing an explicit `fingerprint` key in the `event` dictionary,
    we can force the grouping of all events with the same fingerprint
    making Sentry's issues more granular and useful.

    :param event: event dict to be sent to Sentry
    :param hint: dict with extra information about the event

    :return: the event that will be sent to Sentry,
                with explicit fingerprint values
    """
    if fingerprint := event.get("extra", {}).pop("fingerprint", []):
        event["fingerprint"] = fingerprint

    return event


if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            AsyncioIntegration(),
            CeleryIntegration(),
            DjangoIntegration(),
            RedisIntegration(),
        ],
        ignore_errors=[KeyboardInterrupt],
        before_send=fingerprint_sentry_error,
    )
