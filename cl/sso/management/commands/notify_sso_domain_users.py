import argparse
from typing import Any

from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.management.base import CommandError

from cl.lib.command_utils import VerboseCommand
from cl.sso.emails import emails
from cl.sso.models import OrganizationDomain
from cl.sso.policy import sso_start_url


class Command(VerboseCommand):
    help = (
        "Email the existing accounts on a verified domain that their "
        "organization now uses SSO, so they link their accounts before "
        "enforcement is turned on. Counts only, unless --send is given."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("domain", help="The domain, e.g. acmelaw.com")
        parser.add_argument(
            "--send",
            action="store_true",
            default=False,
            help="Actually send the emails.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
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
        users = (
            User.objects.filter(
                is_active=True,
                email__iendswith=f"@{domain.domain}",
                profile__stub_account=False,
                profile__email_confirmed=True,
            )
            .exclude(socialaccount__provider__in=provider_ids)
            .order_by("pk")
        )
        self.stdout.write(
            f"{users.count()} confirmed account(s) on {domain} not yet "
            "linked to SSO."
        )
        if not options["send"]:
            self.stdout.write("Dry run; pass --send to email them.")
            return
        email = emails["firm_now_uses_sso"]
        for user in users:
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
        self.stdout.write("Sent.")
