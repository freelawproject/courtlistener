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
from cl.recap.fetch_queue import touch_daemon_heartbeat
from cl.recap.fetch_scheduler import fail_stale_fetches, run_dispatch_cycle

# Seconds to wait after one dispatch cycle finishes before starting the next.
DISPATCH_WAIT = 0.5

# Seconds between sweeps for requests that waited too long. Sweeping is a
# database query, so it runs far less often than dispatching.
SWEEP_WAIT = 60

# Longest wait between cycles after repeated failures. Backing off keeps a
# Redis or database outage from flooding the logs, and the API stops queueing
# on its own once the heartbeat goes stale.
MAX_FAILURE_WAIT = 30

shutdown_requested = False


def _request_shutdown(signum: int, _frame: Any) -> None:
    """Ask the daemon to stop once the current cycle finishes."""
    global shutdown_requested
    logger.info(
        "Signal %s received. Shutting down after current cycle.", signum
    )
    shutdown_requested = True


def _wait_after(failures_in_a_row: int) -> float:
    """Get how long to wait before the next cycle.

    Args:
        failures_in_a_row: How many cycles in a row have failed.

    Returns:
        DISPATCH_WAIT after a good cycle, then twice as long after each
        failure, up to MAX_FAILURE_WAIT.
    """
    return min(DISPATCH_WAIT * 2**failures_in_a_row, MAX_FAILURE_WAIT)


class Command(VerboseCommand):
    """Run the RECAP Fetch scheduler until it is told to stop."""

    help = (
        "Long-running daemon that hands waiting RECAP Fetch requests to "
        "Celery and fails requests that waited too long to succeed. To stop "
        "it, set RECAP_FETCH_SCHEDULER_DAEMON_ENABLED=False and restart the "
        "pod (the env var is read once at Django startup)."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add the daemon's command-line options."""
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
        """Dispatch and sweep in a loop until a signal or the setting stops it."""
        super().handle(*args, **options)

        signal.signal(signal.SIGTERM, _request_shutdown)
        signal.signal(signal.SIGINT, _request_shutdown)

        testing_iterations: int = options["testing_iterations"]
        iterations_completed = 0
        # Sweep on the first cycle, so a restart doesn't delay it.
        next_sweep = time.monotonic()
        failures_in_a_row = 0

        logger.info(
            "RECAP Fetch scheduler daemon starting. enabled=%s.",
            settings.RECAP_FETCH_SCHEDULER_DAEMON_ENABLED,
        )

        while (
            not shutdown_requested
            and settings.RECAP_FETCH_SCHEDULER_DAEMON_ENABLED
        ):
            try:
                # The API only queues requests while this heartbeat is fresh.
                touch_daemon_heartbeat()
                run_dispatch_cycle()
                if time.monotonic() >= next_sweep:
                    next_sweep = time.monotonic() + SWEEP_WAIT
                    if failed := fail_stale_fetches():
                        logger.info("Failed %s stale fetch requests.", failed)
                failures_in_a_row = 0
            except Exception as e:
                # One bad cycle (e.g. a Redis or DB blip) shouldn't crash the
                # pod and cause a restart loop. Waiting requests stay in Redis
                # and the next cycle picks them up. Only the first failure of
                # a streak goes to Sentry.
                failures_in_a_row += 1
                if failures_in_a_row == 1:
                    logger.exception("Scheduler cycle failed; continuing.")
                    capture_exception(e)
                else:
                    logger.warning(
                        "Scheduler cycle failed %s times in a row: %s",
                        failures_in_a_row,
                        e,
                    )

            iterations_completed += 1
            if (
                testing_iterations
                and iterations_completed >= testing_iterations
            ):
                break

            time.sleep(_wait_after(failures_in_a_row))

        logger.info(
            "RECAP Fetch scheduler daemon stopped after %s iteration(s).",
            iterations_completed,
        )
