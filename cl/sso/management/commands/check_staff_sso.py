import argparse
from typing import Any

from django.core.mail import mail_managers

from cl.lib.command_utils import VerboseCommand
from cl.sso.staff import build_staff_sso_report


class Command(VerboseCommand):
    """Report staff accounts that can sign in without FLP's IdP."""

    help = (
        "Check that staff can only sign in through FLP's IdP: unlinked staff "
        "accounts and staff API tokens. Run it on a schedule and keep the "
        "output as SOC 2 evidence."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add the --email option."""
        parser.add_argument(
            "--email",
            action="store_true",
            default=False,
            help="Email the report to the MANAGERS when it finds problems.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Print the staff SSO report, emailing it if asked."""
        super().handle(*args, **options)
        report = build_staff_sso_report()
        lines = [f"Staff organization: {report.staff_organization or 'none'}"]
        lines += [f"PROBLEM: {p}" for p in report.problems]
        lines += [f"NOTE: {n}" for n in report.notes]
        if not report.problems:
            lines.append("No problems found.")
        output = "\n".join(lines)
        self.stdout.write(output)
        if options["email"] and report.problems:
            mail_managers("Staff SSO check found problems", output)
