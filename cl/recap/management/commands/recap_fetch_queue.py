"""Inspect the RECAP Fetch queue and change how fast it sends to each court.

Examples:
    manage.py recap_fetch_queue --status
    manage.py recap_fetch_queue --set-rate dcd 1/2s
    manage.py recap_fetch_queue --clear-rate dcd

Rate changes take effect on the court's next request, including requests
already waiting, without a deploy or restart.
"""

import argparse
from typing import Any

from django.conf import settings
from django.core.management import CommandError

from cl.lib.command_utils import VerboseCommand
from cl.recap.fetch_queue import (
    daemon_is_alive,
    get_court_queue_status,
    get_court_rates,
    get_courts_with_waiting_fetches,
    set_court_rate,
)
from cl.search.models import Court, FederalCourtsQuerySet


class Command(VerboseCommand):
    """Show the RECAP Fetch queue or change a court's rate."""

    help = (
        "Show how many RECAP Fetch requests wait per court and per user, or "
        "change a court's rate."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add the command's options. Exactly one of them is required."""
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--status",
            action="store_true",
            help="Show the queue of every court with requests waiting.",
        )
        group.add_argument(
            "--set-rate",
            nargs=2,
            metavar=("COURT_ID", "RATE"),
            help='Give a court its own rate, like "1/2s" or "30/m".',
        )
        group.add_argument(
            "--clear-rate",
            metavar="COURT_ID",
            help="Return a court to the default rate.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the action that was asked for."""
        super().handle(*args, **options)
        if options["status"]:
            self._print_status()
        elif options["set_rate"]:
            court_id, rate = options["set_rate"]
            self._check_court(court_id)
            try:
                set_court_rate(court_id, rate)
            except ValueError as e:
                raise CommandError(str(e)) from e
            self.stdout.write(f"{court_id} now uses {rate}.")
        else:
            court_id = options["clear_rate"]
            self._check_court(court_id)
            set_court_rate(court_id, None)
            self.stdout.write(
                f"{court_id} now uses the default rate, "
                f"{settings.RECAP_FETCH_DEFAULT_COURT_RATE}."
            )

    @staticmethod
    def _check_court(court_id: str) -> None:
        """Make sure a court ID belongs to a court the Fetch API accepts.

        Args:
            court_id: The court ID given on the command line.

        Raises:
            CommandError: If no current PACER court has that ID.
        """
        # The queryset is built directly because type checkers can't see the
        # methods Court.federal_courts gets from it. It's the same check the
        # Fetch API runs.
        pacer_courts = FederalCourtsQuerySet(Court).all_pacer_courts()
        if not pacer_courts.filter(pk=court_id).exists():
            raise CommandError(f"No PACER court has the ID {court_id!r}.")

    def _print_status(self) -> None:
        """Print each waiting court's queue, then the courts' own rates."""
        alive = "running" if daemon_is_alive() else "NOT running"
        self.stdout.write(f"Scheduler daemon: {alive}")
        self.stdout.write(
            f"Default rate: {settings.RECAP_FETCH_DEFAULT_COURT_RATE}"
        )

        courts = sorted(get_courts_with_waiting_fetches())
        if not courts:
            self.stdout.write("No requests are waiting.")
        for court_id in courts:
            status = get_court_queue_status(court_id)
            total = sum(status.depth_by_user.values())
            self.stdout.write(
                f"\n{court_id}: {total} waiting, one request every "
                f"{status.interval_ms / 1000:g} s, next in "
                f"{status.next_in_ms / 1000:g} s, handed off and not "
                f"started: {status.pending_pk or 'none'}"
            )
            for user_id, depth in sorted(
                status.depth_by_user.items(), key=lambda item: -item[1]
            ):
                self.stdout.write(f"  user {user_id}: {depth}")

        if rates := get_court_rates():
            self.stdout.write("\nCourts with their own rate:")
            for court_id, rate in sorted(rates.items()):
                self.stdout.write(f"  {court_id}: {rate}")
