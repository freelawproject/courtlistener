"""Cleans the django-oauth-toolkit tables;
See ``cl.oauth.cleanup_utils.run_cleanup_pass``.
"""

import argparse
from typing import Any

from cl.lib.command_utils import VerboseCommand
from cl.oauth.cleanup_utils import run_cleanup_pass


class Command(VerboseCommand):
    help = (
        "Delete OAuth applications registered through /o/register/ that no "
        "user ever authorized, then clear expired grants and tokens."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Count the applications that would be deleted without "
                "deleting anything, and skip token clearing entirely."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)
        run_cleanup_pass(dry_run=options["dry_run"])
