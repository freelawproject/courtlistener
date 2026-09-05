from argparse import ArgumentParser
from pathlib import Path

from cl.lib.command_utils import VerboseCommand, logger
from cl.users.duplicate_census import (
    run_census,
    write_account_csv,
    write_collision_csv,
)

ACCOUNTS_CSV = "duplicate_accounts.csv"
COLLISIONS_CSV = "username_email_collisions.csv"


class Command(VerboseCommand):
    """Census of accounts that share an email address. Read-only.

    Writes one CSV row per account in a duplicate group, a second CSV listing
    every account whose username is another account's email address, and
    prints a summary with a count per blocker class. Nothing in the database
    or Redis is modified, so it is safe against a production replica and safe
    to run on a schedule once the duplicates are merged, so they cannot
    silently return.

    The CSVs are concentrated PII. Keep them out of git and public buckets.
    """

    help = (
        "Report accounts that share an email address, which one a merge "
        "would keep, and what blocks an automatic merge. Read-only."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--output-dir",
            type=Path,
            required=True,
            help=f"Directory to write {ACCOUNTS_CSV} and {COLLISIONS_CSV} "
            "into. Created if missing.",
        )
        parser.add_argument(
            "--email",
            default=None,
            help="Only report the group for this address, e.g. to "
            "investigate a support report. Skips the whole-table username "
            "collision scan.",
        )

    def handle(self, *args: str, **options: object) -> None:
        super().handle(*args, **options)
        # call_command() hands the raw value through, so convert here rather
        # than trusting the argparse type.
        output_dir = Path(str(options["output_dir"]))
        email: str | None = options["email"]  # type: ignore[assignment]
        output_dir.mkdir(parents=True, exist_ok=True)

        report = run_census(email=email)

        accounts_path = output_dir / ACCOUNTS_CSV
        with accounts_path.open("w", newline="", encoding="utf-8") as f:
            write_account_csv(report, f)
        logger.info("Wrote %s", accounts_path)

        if not email:
            collisions_path = output_dir / COLLISIONS_CSV
            with collisions_path.open("w", newline="", encoding="utf-8") as f:
                write_collision_csv(report, f)
            logger.info("Wrote %s", collisions_path)

        self.stdout.write("\n".join(report.summary_lines()))
