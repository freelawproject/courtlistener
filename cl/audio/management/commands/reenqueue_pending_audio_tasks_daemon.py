"""Daemon wrapper around reenqueue_pending_audio_tasks.

Acts as the **only** dispatcher of OpenAI transcription tasks. Each cycle
caps the number of dispatches at ``AUDIO_REENQUEUE_MAX_PER_SWEEP`` so the
cluster-wide transcription rate stays under OpenAI's safe concurrency:

    rate ≈ AUDIO_REENQUEUE_MAX_PER_SWEEP / AUDIO_REENQUEUE_WAIT

The dispatch helpers in ``cl.audio.dispatch`` enforce per-pk dedup so
two daemon cycles overlapping (or a manual one-shot run alongside) never
double-fire for the same audio.

``settings.AUDIO_REENQUEUE_DAEMON_ENABLED`` is the boot-time enable flag.
Django settings are read once at process start, so flipping the env var on
a running pod takes effect on the next restart — which is also the drain.
The in-loop ``while`` check exists so tests can use ``override_settings``
to exit the loop cleanly.
"""

import argparse
import signal
import time
from typing import Any

from django.conf import settings
from sentry_sdk import capture_exception

from cl.audio.management.commands.reenqueue_pending_audio_tasks import (
    run_reenqueue_cycle,
)
from cl.lib.command_utils import VerboseCommand, logger

shutdown_requested = False


def _request_shutdown(signum: int, _frame: Any) -> None:
    global shutdown_requested
    logger.info(
        "Signal %s received. Shutting down after current cycle.", signum
    )
    shutdown_requested = True


def _interruptible_sleep(total_seconds: int) -> None:
    """Sleep in 1s ticks so SIGTERM doesn't have to wait an hour."""
    for _ in range(total_seconds):
        if shutdown_requested:
            return
        time.sleep(1)


class Command(VerboseCommand):
    help = (
        "Long-running daemon that periodically dispatches audios needing "
        "standardization or transcription. Acts as the cluster-wide rate "
        "limiter for OpenAI calls. Cadence is settings.AUDIO_REENQUEUE_"
        "WAIT; throughput cap is settings.AUDIO_REENQUEUE_MAX_PER_SWEEP. "
        "To drain, set AUDIO_REENQUEUE_DAEMON_ENABLED=False and restart "
        "the pod (the env var is read once at Django startup)."
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
        parser.add_argument(
            "--older-than-hours",
            type=int,
            default=0,
            help=(
                "Skip audios newer than this many hours. Default 0: pick "
                "up freshly-scraped audios on the next cycle."
            ),
        )
        parser.add_argument(
            "--newer-than-days",
            type=int,
            default=7,
            help="Forwarded to run_reenqueue_cycle. Default: 7.",
        )
        parser.add_argument(
            "--max-per-sweep",
            type=int,
            default=None,
            help=(
                "Override settings.AUDIO_REENQUEUE_MAX_PER_SWEEP. Cap on "
                "dispatches per stage per cycle — together with the "
                "cadence this is the OpenAI rate limit."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)

        signal.signal(signal.SIGTERM, _request_shutdown)
        signal.signal(signal.SIGINT, _request_shutdown)

        testing_iterations: int = options["testing_iterations"]
        iterations_completed = 0
        max_per_sweep: int = (
            options["max_per_sweep"]
            if options["max_per_sweep"] is not None
            else settings.AUDIO_REENQUEUE_MAX_PER_SWEEP
        )

        logger.info(
            "Audio re-enqueue daemon starting. Cadence=%ss, "
            "max_per_sweep=%s, enabled=%s.",
            settings.AUDIO_REENQUEUE_WAIT,
            max_per_sweep,
            settings.AUDIO_REENQUEUE_DAEMON_ENABLED,
        )

        while (
            not shutdown_requested and settings.AUDIO_REENQUEUE_DAEMON_ENABLED
        ):
            try:
                run_reenqueue_cycle(
                    older_than_hours=options["older_than_hours"],
                    newer_than_days=options["newer_than_days"],
                    limit=max_per_sweep,
                    skip_processing=False,
                    skip_transcription=False,
                    dry_run=False,
                    verbose=False,
                )
            except Exception as e:
                # One bad cycle (e.g. DB blip) shouldn't crash the pod and
                # cause a k8s restart loop. Hard failures (import errors,
                # OOM) still escape and correctly trigger a restart.
                logger.exception("Re-enqueue cycle failed; continuing.")
                capture_exception(e)

            iterations_completed += 1
            if (
                testing_iterations
                and iterations_completed >= testing_iterations
            ):
                break

            _interruptible_sleep(settings.AUDIO_REENQUEUE_WAIT)

        logger.info(
            "Audio re-enqueue daemon stopped after %s iteration(s).",
            iterations_completed,
        )
