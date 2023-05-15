from datetime import datetime, timedelta, timezone

from django.utils.timezone import make_aware

from cl.lib.command_utils import VerboseCommand
from cl.users.models import EmailSent


def delete_old_emails(days: int) -> int:
    """Delete stored emails older than the specified number of days."""

    older_than = make_aware(datetime.now(), timezone.utc) - timedelta(
        days=days
    )
    emails = EmailSent.objects.filter(date_created__lt=older_than)
    print(f"Deleting emails created before: {older_than}")

    count = 0
    if emails:
        count = emails.count()
        emails.delete()
    return count


class Command(VerboseCommand):
    """Command to delete stored emails older than the specified number of
    days."""

    help = "Delete stored emails older than the specified number of days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days",
            type=int,
            help="Delete emails older than this number of days, the date is "
            "computed based on UTC.",
            required=True,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options
        emails = delete_old_emails(options["older_than_days"])
        print(f"Emails deleted: {emails}")
