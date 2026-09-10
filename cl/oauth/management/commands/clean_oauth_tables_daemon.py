"""Daemon that runs ``cl.oauth.cleanup_utils.run_cleanup_pass`` every
``settings.OAUTH_CLEANUP_INTERVAL`` seconds. ``OAUTH_CLEANUP_DAEMON_ENABLED``
enables this daemon.
"""

import argparse
import signal
import time
from typing import Any

from django.conf import settings
from sentry_sdk import capture_exception

from cl.lib.command_utils import VerboseCommand, logger
from cl.oauth.cleanup_utils import run_cleanup_pass

shutdown_requested = False


def _request_shutdown(signum: int, _frame: Any) -> None:
    """Finish the current pass, then exit the loop."""
    global shutdown_requested
    logger.info(
        "Signal %s received. Shutting down after current pass.", signum
    )
    shutdown_requested = True


def _interruptible_sleep(total_seconds: int) -> None:
    """Sleep in 1s ticks so SIGTERM doesn't wait out the whole interval."""
    for _ in range(total_seconds):
        if shutdown_requested:
            return
        time.sleep(1)


class Command(VerboseCommand):
    help = (
        "Long-running daemon that deletes OAuth applications registered "
        "through /o/register/ that no user ever authorized; clearing "
        "expired tokens is staged for a later PR. "
        "Cadence is settings.OAUTH_CLEANUP_INTERVAL; set "
        "OAUTH_CLEANUP_DAEMON_ENABLED=False and restart the pod to stop it."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--testing-iterations",
            type=int,
            default=0,
            help=(
                "Number of passes to run before exiting. 0 means run "
                "forever. Default: 0."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Log what each pass would delete without deleting anything.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)

        signal.signal(signal.SIGTERM, _request_shutdown)
        signal.signal(signal.SIGINT, _request_shutdown)

        testing_iterations: int = options["testing_iterations"]
        dry_run: bool = options["dry_run"]
        iterations_completed = 0

        logger.info(
            "OAuth cleanup daemon starting. Cadence=%ss, batch_size=%s, "
            "dry_run=%s, enabled=%s.",
            settings.OAUTH_CLEANUP_INTERVAL,
            settings.OAUTH_CLEANUP_BATCH_SIZE,
            dry_run,
            settings.OAUTH_CLEANUP_DAEMON_ENABLED,
        )

        while not shutdown_requested and settings.OAUTH_CLEANUP_DAEMON_ENABLED:
            try:
                run_cleanup_pass(dry_run=dry_run)
            except Exception as e:
                # Log and continue so a transient DB error doesn't crash-loop
                # the pod.
                logger.exception("OAuth cleanup pass failed; continuing.")
                capture_exception(e)

            iterations_completed += 1
            if (
                testing_iterations
                and iterations_completed >= testing_iterations
            ):
                break

            _interruptible_sleep(settings.OAUTH_CLEANUP_INTERVAL)

        logger.info(
            "OAuth cleanup daemon stopped after %s pass(es).",
            iterations_completed,
        )
