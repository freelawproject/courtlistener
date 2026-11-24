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


# Code whose local variables hold a user's personal data, such as their data
# export, keyed by module. None means every function in the module.
_PRIVATE_FUNCTIONS: dict[str, set[str] | None] = {
    "cl.users.data_export": None,
    "cl.users.views": {"take_out"},
}


def _is_private_frame(frame: dict[str, Any]) -> bool:
    """Is this stack frame in code listed in _PRIVATE_FUNCTIONS?"""
    module = frame.get("module")
    if module not in _PRIVATE_FUNCTIONS:
        return False
    functions = _PRIVATE_FUNCTIONS[module]
    return functions is None or frame.get("function") in functions


def scrub_private_frames(event: dict[str, Any]) -> dict[str, Any]:
    """Drop local variables that could hold a user's personal data.

    Sentry sends each frame's local variables with an error. This removes them
    from frames in the code listed in _PRIVATE_FUNCTIONS, and from every frame
    that code called (e.g. Django's serializer), since those work on the same
    data. Frames elsewhere in the stack keep their variables.

    Args:
        event: event dict to be sent to Sentry

    Returns:
        the same event, with the private variables removed
    """
    for key in ("exception", "threads"):
        for value in (event.get(key) or {}).get("values", []):
            # Frames run from the outermost call to the innermost, so every
            # frame after a private one was called on its behalf.
            in_private_code = False
            for frame in (value.get("stacktrace") or {}).get("frames", []):
                in_private_code = in_private_code or _is_private_frame(frame)
                if in_private_code:
                    frame.pop("vars", None)
    return event


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Prepare an event for Sentry: scrub private data, then fingerprint it.

    Args:
        event: event dict to be sent to Sentry
        hint: dict with extra information about the event

    Returns:
        the event that will be sent to Sentry
    """
    return fingerprint_sentry_error(scrub_private_frames(event), hint)


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
