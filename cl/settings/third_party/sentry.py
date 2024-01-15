from typing import Any, Dict

import environ
import sentry_sdk
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


def fingerprint_event(
    event: Dict[str, Any], hint: Dict[str, Any]
) -> Dict[str, Any]:
    """If a fingerprint key is present in "extra", pass it to Sentry

    This function expects error.log(extra={"fingerprint": []})
    to be a List

    The fingerprint will be a "group ID" on Sentry, forcing all events
    with that key to be grouped on a single issue

    :param event: event dict to be sent to Sentry
    :param hint: dict with extra information about the event

    :return: the event that will be sent to Sentry
    """
    # logger.error calls can take an 'extra' keyword argument
    # which is used here to pass the fingerprint key
    if fingerprint := event.get("extra", {}).pop("fingerprint", []):
        event["fingerprint"] = fingerprint

    return event


if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            CeleryIntegration(),
            DjangoIntegration(),
            RedisIntegration(),
        ],
        ignore_errors=[KeyboardInterrupt],
        before_send=fingerprint_event,
    )
