import environ
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.redis import RedisIntegration

env = environ.FileAwareEnv()
SENTRY_DSN = env("SENTRY_DSN")

ignore_logger("internetarchive.session")
ignore_logger("internetarchive.item")

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[
        CeleryIntegration(),
        DjangoIntegration(),
        RedisIntegration(),
    ],
    ignore_errors=[KeyboardInterrupt],
)
