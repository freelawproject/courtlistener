"""Daemon that hands waiting RECAP Fetch requests to Celery.

This is the only place that sends a request made through the Fetch API to
Celery. See ``cl.recap.fetch_scheduler`` for how requests wait.

``settings.RECAP_FETCH_SCHEDULER_DAEMON_ENABLED`` is the boot-time enable
flag. Django settings are read once at process start, so changing the env var
takes effect on the next restart. The in-loop check exists so tests can use
``override_settings`` to exit the loop cleanly.
"""

import argparse
import signal
import time
from typing import Any

from django.conf import settings
from sentry_sdk import capture_exception

from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.fetch_scheduler import run_dispatch_cycle

# Seconds to wait after one dispatch cycle finishes before starting the next.
DISPATCH_WAIT = 0.5

shutdown_requested = False


def _request_shutdown(signum: int, _frame: Any) -> None:
    """Ask the daemon to stop once the current cycle finishes."""
    global shutdown_requested
    logger.info(
        "Signal %s received. Shutting down after current cycle.", signum
    )
    shutdown_requested = True


class Command(VerboseCommand):
    help = (
        "Long-running daemon that hands waiting RECAP Fetch requests to "
        "Celery. To stop it, set RECAP_FETCH_SCHEDULER_DAEMON_ENABLED=False "
        "and restart the pod (the env var is read once at Django startup)."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--testing-iterations",
            type=int,
            default=0,
            help=(
                "Number of cycles to run before exiting. 0 means run "
                "forever. Default: 0."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)

        signal.signal(signal.SIGTERM, _request_shutdown)
        signal.signal(signal.SIGINT, _request_shutdown)

        testing_iterations: int = options["testing_iterations"]
        iterations_completed = 0

        logger.info(
            "RECAP Fetch scheduler daemon starting. enabled=%s.",
            settings.RECAP_FETCH_SCHEDULER_DAEMON_ENABLED,
        )

        while (
            not shutdown_requested
            and settings.RECAP_FETCH_SCHEDULER_DAEMON_ENABLED
        ):
            try:
                run_dispatch_cycle()
            except Exception as e:
                # One bad cycle (e.g. a Redis or DB blip) shouldn't crash the
                # pod and cause a restart loop. Waiting requests stay in Redis
                # and the next cycle picks them up.
                logger.exception("Scheduler cycle failed; continuing.")
                capture_exception(e)

            iterations_completed += 1
            if (
                testing_iterations
                and iterations_completed >= testing_iterations
            ):
                break

            time.sleep(DISPATCH_WAIT)

        logger.info(
            "RECAP Fetch scheduler daemon stopped after %s iteration(s).",
            iterations_completed,
        )
