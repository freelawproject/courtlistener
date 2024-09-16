from datetime import timedelta

from django.utils.timezone import now

from cl.donate.models import Donation
from cl.lib.command_utils import VerboseCommand

TOO_MANY_DAYS_AGO = now() - timedelta(days=7)


class Command(VerboseCommand):
    help = (
        "Deletes donations that never went through so they are not in "
        "the database forever."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--simulate",
            action="store_true",
            default=False,
            help="Run the command in simulate mode so that no items are "
            "actually deleted.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.stdout.write("#\n" * 25)
        if options["simulate"]:
            self.stdout.write("# SIMULATE MODE IS ON.  #\n")
        else:
            self.stdout.write("# SIMULATE MODE IS OFF. #\n")
        self.stdout.write("#\n" * 25)

        # The statuses here are rather conservative and will likely need
        # updating as further failed payments trickle in.
        qs = {
            "PayPal": Donation.objects.filter(
                payment_provider="paypal",
                date_created__lt=TOO_MANY_DAYS_AGO,
                status__in=[
                    Donation.AWAITING_PAYMENT,
                    Donation.UNKNOWN_ERROR,
                    Donation.CANCELLED,
                ],
            ),
            "Stripe": Donation.objects.filter(
                payment_provider="stripe",
                date_created__lt=TOO_MANY_DAYS_AGO,
                status=Donation.AWAITING_PAYMENT,
            ),
        }

        for provider, q in qs.items():
            self.stdout.write(f"Processing {provider}:\n")
            self.stdout.write(f"  Deleted {q.count()} items.\n")
            if not options["simulate"]:
                q.delete()
