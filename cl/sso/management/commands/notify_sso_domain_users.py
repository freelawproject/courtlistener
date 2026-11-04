import argparse
import logging
from collections import Counter
from typing import Any

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.management.base import CommandError

from cl.lib.command_utils import VerboseCommand
from cl.sso.emails import emails
from cl.sso.models import Enforcement, OrganizationDomain
from cl.sso.policy import enabled_connection, sso_start_url

logger = logging.getLogger(__name__)


class Command(VerboseCommand):
    """Tell a domain's existing accounts that their organization uses SSO."""

    help = (
        "Email the existing accounts on a verified domain that their "
        "organization now uses SSO, so they link their accounts before "
        "enforcement is turned on. Counts only, unless --send is given."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add the domain argument and the --send option."""
        parser.add_argument("domain", help="The domain, e.g. acmelaw.com")
        parser.add_argument(
            "--send",
            action="store_true",
            default=False,
            help="Actually send the emails.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Count, or with --send email, the domain's existing accounts."""
        super().handle(*args, **options)
        domain = (
            OrganizationDomain.objects.filter(
                domain=options["domain"].strip().lower(),
                verified_at__isnull=False,
            )
            .select_related("organization")
            .first()
        )
        if domain is None:
            raise CommandError(f"{options['domain']} isn't a verified domain.")
        organization = domain.organization
        provider_ids = [c.provider_id for c in organization.connections.all()]
        # Only confirmed accounts: nobody has proven they read the others.
        users = User.objects.filter(
            is_active=True,
            email__iendswith=f"@{domain.domain}",
            profile__stub_account=False,
            profile__email_confirmed=True,
        ).order_by("pk")
        exempt = {
            e.lower()
            for e in organization.email_exceptions.values_list(
                "email", flat=True
            )
        }
        users = [u for u in users if u.email.lower() not in exempt]
        # SSO links only one account per address, so shared addresses go to
        # support instead. Count them before dropping linked accounts.
        counts = Counter(u.email.lower() for u in users)
        shared = sorted(e for e, n in counts.items() if n > 1)
        linked = set(
            SocialAccount.objects.filter(
                provider__in=provider_ids
            ).values_list("user_id", flat=True)
        )
        users = [
            u
            for u in users
            if counts[u.email.lower()] == 1 and u.pk not in linked
        ]
        self.stdout.write(
            f"{len(users)} confirmed account(s) on {domain} not yet "
            "linked to SSO."
        )
        if shared:
            self.stdout.write(
                "Skipped, more than one account: " + ", ".join(shared)
            )
        if not options["send"]:
            self.stdout.write("Dry run; pass --send to email them.")
            return
        if (
            domain.enforcement == Enforcement.OFF
            or enabled_connection(organization) is None
        ):
            raise CommandError(
                f"{domain} doesn't offer SSO yet. Turn on enforcement and "
                "enable a connection first."
            )
        email = emails["firm_now_uses_sso"]
        failed = []
        for user in users:
            try:
                send_mail(
                    email["subject"] % organization.name,
                    email["body"]
                    % (
                        user.first_name or user.username,
                        organization.name,
                        sso_start_url(email=user.email),
                        user.username,
                    ),
                    email["from_email"],
                    [user.email],
                )
            except Exception:
                logger.exception("Couldn't email %s", user.email)
                failed.append(user.email)
        self.stdout.write(f"Sent {len(users) - len(failed)}.")
        if failed:
            self.stdout.write("Failed: " + ", ".join(failed))
