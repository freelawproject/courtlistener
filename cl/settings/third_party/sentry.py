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


def refine_fingerprint(event: Dict[str, Any], hint: Dict[str, Any]):
    """If a fingerprint key is present in "extra", pass it to Sentry

    This fingerprint will be a "group ID" on Sentry, forcing all events
    with that key to be grouped on a single issue

    This implementation expects the fingerprint to be a string
    The event["fingerprint"] should be a list
    """
    if fingerprint := event.get("extra", {}).pop("fingerprint", ""):
        event["fingerprint"] = [fingerprint]

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
        before_send=refine_fingerprint,
    )
