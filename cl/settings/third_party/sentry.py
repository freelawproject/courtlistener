"""Settings for Sentry, initializing it when a DSN is configured."""

from typing import Any

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
    """Captures fingerprint information from logger.error call, if present.

    logger.error calls allow to pass an `extra` dictionary with arbitrary keys
    We use this to pass a `fingerprint` key. The value should be a list.
    For example:
    error.log(extra={"fingerprint": [court_id, "citation-not-found"]})

    By default, Sentry events are grouped into issues using Sentry's
    internal algorithms.
    By passing an explicit `fingerprint` key in the `event` dictionary,
    we can force the grouping of all events with the same fingerprint
    making Sentry's issues more granular and useful.

    Args:
        event: event dict to be sent to Sentry
        hint: dict with extra information about the event

    Returns:
        the event that will be sent to Sentry,
                with explicit fingerprint values
    """
    if fingerprint := event.get("extra", {}).pop("fingerprint", []):
        event["fingerprint"] = fingerprint

    return event


# The frames Django's @sensitive_variables and @sensitive_post_parameters
# decorators put around the (sync) functions they mark, as (module, function).
_SENSITIVE_VARIABLES_FRAME = (
    "django.views.decorators.debug",
    "sensitive_variables_wrapper",
)
_SENSITIVE_POST_PARAMETERS_FRAME = (
    "django.views.decorators.debug",
    "sensitive_post_parameters_wrapper",
)


def _stacks(event: dict[str, Any], key: str) -> list[list[dict[str, Any]]]:
    """Return the frame lists of an event's exceptions or threads."""
    return [
        (value.get("stacktrace") or {}).get("frames", [])
        for value in (event.get(key) or {}).get("values", [])
    ]


def _first(frames: list[dict[str, Any]], location: tuple[str, str]) -> int:
    """Return the index of the first frame at a location, or -1 if none is."""
    for i, frame in enumerate(frames):
        if (frame.get("module"), frame.get("function")) == location:
            return i
    return -1


def scrub_sensitive_data(event: dict[str, Any]) -> dict[str, Any]:
    """Hide data marked with Django's sensitive_* decorators from Sentry.

    Django hides what these decorators mark in its own error reports, but
    Sentry doesn't know about them. This applies them to Sentry events, more
    strictly than Django does:

    - Under @sensitive_variables, every local variable is dropped, in the
      decorated function and in everything it calls (e.g. Django's
      serializer), not just the named variables.
    - Under @sensitive_post_parameters, the whole request body is dropped,
      not just the named fields.

    Caveat: Django tracks async functions differently, so this only works on
    sync functions.

    Args:
        event: event dict to be sent to Sentry

    Returns:
        the same event, with the sensitive data removed
    """
    exceptions = _stacks(event, "exception")
    threads = _stacks(event, "threads")

    # A chained exception only has the frames from where it was raised to
    # where it was caught, so it can lack the wrapper even when it happened
    # under it. If any exception went through the wrapper, scrub chained ones
    # that didn't in full.
    under_wrapper = any(
        _first(frames, _SENSITIVE_VARIABLES_FRAME) >= 0
        for frames in exceptions
    )
    stacks = [(frames, under_wrapper) for frames in exceptions] + [
        (frames, False) for frames in threads
    ]
    for frames, scrub_all_without_wrapper in stacks:
        start = _first(frames, _SENSITIVE_VARIABLES_FRAME)
        if start < 0:
            start = 0 if scrub_all_without_wrapper else len(frames)
        # Frames run from the outermost call to the innermost, so every frame
        # after the wrapper was called on the marked function's behalf.
        for frame in frames[start:]:
            frame.pop("vars", None)

    request = event.get("request") or {}
    if "data" in request and any(
        _first(frames, _SENSITIVE_POST_PARAMETERS_FRAME) >= 0
        for frames in exceptions + threads
    ):
        request["data"] = "[Filtered]"
    return event


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Prepare an event for Sentry: scrub sensitive data, then fingerprint it.

    Args:
        event: event dict to be sent to Sentry
        hint: dict with extra information about the event

    Returns:
        the event that will be sent to Sentry
    """
    return fingerprint_sentry_error(scrub_sensitive_data(event), hint)


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
        before_send=before_send,
        attach_stacktrace=True,
    )
