from datetime import datetime, timedelta

from django.utils.timezone import make_aware, utc

from cl.lib.command_utils import VerboseCommand
from cl.users.models import EmailSent


class Command(VerboseCommand):
    """Command to delete stored messages older than the specified number of
    days."""

    help = "Delete stored messages older than the specified number of days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days",
            type=int,
            help="Delete messages older than this number of days.",
            required=True,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options
        messages = self.delete_old_messages(options["older_than_days"])
        print(f"Messages deleted: {messages}")

    def delete_old_messages(self, days):
        """Delete stored messages older than the specified number of days."""

        older_than = make_aware(datetime.now(), utc) - timedelta(
            days=int(days)
        )
        messages = EmailSent.objects.filter(date_created__lt=older_than)
        print(f"Deleting messages created before: {older_than}")

        counter = 0
        if messages:
            counter = messages.count()
            messages.delete()
        return counter
