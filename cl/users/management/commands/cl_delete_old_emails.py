from datetime import datetime, timedelta

from django.utils.timezone import make_aware, utc

from cl.lib.command_utils import VerboseCommand
from cl.users.models import EmailSent


def delete_old_emails(days: int) -> int:
    """Delete stored emails older than the specified number of days."""

    older_than = make_aware(datetime.now(), utc) - timedelta(days=int(days))
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
            help="Delete emails older than this number of days.",
            required=True,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options
        emails = delete_old_emails(options["older_than_days"])
        print(f"Emails deleted: {emails}")
