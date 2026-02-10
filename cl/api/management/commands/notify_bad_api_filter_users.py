import sys
from datetime import date
from typing import Any

from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template import loader

from cl.api.utils import (
    clear_bad_filter_params_for_user,
    get_all_users_with_bad_filter_params,
    get_bad_filter_params_for_user,
)
from cl.lib.command_utils import VerboseCommand, logger

ENFORCEMENT_DATE = date(2026, 2, 10)


class Command(VerboseCommand):
    """Send notification emails to users who have used invalid API filter
    parameters.

    This command should be run nightly to notify users about their invalid
    API usage before we start blocking such requests.
    """

    help = (
        "Sends notification emails to users who have used invalid API filter "
        "parameters, warning them that such requests will soon be blocked."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--simulate",
            action="store_true",
            default=False,
            help="Don't send any emails, just show what would be sent.",
        )
        parser.add_argument(
            "--clear-after-send",
            action="store_true",
            default=False,
            help="Clear Redis records after sending emails (use with caution to prevent repeat emails).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)
        self.options = options

        if self.options["simulate"]:
            sys.stdout.write(
                "**********************************\n"
                "* SIMULATE MODE - NO EMAILS SENT *\n"
                "**********************************\n\n"
            )

        user_ids = get_all_users_with_bad_filter_params()
        if not user_ids:
            logger.info("No users with bad filter parameters found.")
            return

        logger.info(
            f"Found {len(user_ids)} user(s) with bad filter parameters"
        )

        messages = []
        users_to_clear: list[int] = []

        for user_id in user_ids:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                logger.warning(f"User {user_id} not found, skipping")
                continue

            bad_params = get_bad_filter_params_for_user(user_id)
            if not bad_params:
                continue

            message = self._create_email(user, bad_params)
            messages.append(message)
            users_to_clear.append(user_id)

            if self.options["simulate"]:
                self._print_simulation(user, bad_params)

        if not messages:
            logger.info("No emails to send.")
            return

        if not self.options["simulate"]:
            connection = get_connection()
            connection.send_messages(messages)
            logger.info(f"Sent {len(messages)} notification email(s).")

            if self.options["clear_after_send"]:
                for user_id in users_to_clear:
                    clear_bad_filter_params_for_user(user_id)
                logger.info(
                    f"Cleared Redis records for {len(users_to_clear)} user(s)."
                )
        else:
            sys.stdout.write(
                f"\nSimulation complete. Would have sent {len(messages)} "
                "email(s).\n"
            )

    def _create_email(
        self,
        user: User,
        bad_params: list[dict[str, Any]],
    ) -> EmailMultiAlternatives:
        """Create an email message for a user with bad filter parameters.

        :param user: The user to notify.
        :param bad_params: List of bad parameter records.
        :return: An EmailMultiAlternatives object ready to send.
        """
        txt_template = loader.get_template(
            "emails/bad_api_filter_params_email.txt"
        )

        # Group bad params by endpoint for cleaner display
        params_by_endpoint: dict[str, list[dict[str, Any]]] = {}
        for record in bad_params:
            endpoint = record["endpoint"]
            if endpoint not in params_by_endpoint:
                params_by_endpoint[endpoint] = []
            params_by_endpoint[endpoint].append(record)

        context = {
            "name": user.first_name or user.username,
            "params_by_endpoint": params_by_endpoint,
            "total_count": sum(r["count"] for r in bad_params),
            "enforcement_date": ENFORCEMENT_DATE,
        }

        email_txt = txt_template.render(context)

        return EmailMultiAlternatives(
            subject="Action Required: Invalid API Filter Parameters Detected",
            body=email_txt,
            from_email="CourtListener <noreply@courtlistener.com>",
            to=[user.email],
            headers={"X-Entity-Ref-ID": f"bad_api_filter:{user.pk}"},
        )

    def _print_simulation(
        self,
        user: User,
        bad_params: list[dict[str, Any]],
    ) -> None:
        """Print simulation output for a user.

        :param user: The user who would receive the email.
        :param bad_params: List of bad parameter records.
        """
        sys.stdout.write(f"\n{'=' * 60}\n")
        sys.stdout.write(f"Would email: {user.email} (User ID: {user.pk})\n")
        sys.stdout.write(f"{'=' * 60}\n")

        for record in bad_params:
            sys.stdout.write(
                f"  Endpoint: {record['endpoint']}\n"
                f"  Parameter: {record['param']}\n"
                f"  Count: {record['count']}\n"
                f"  First seen: {record['first_seen']}\n"
                f"  Last seen: {record['last_seen']}\n"
                f"  ---\n"
            )
