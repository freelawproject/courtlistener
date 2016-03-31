from django.core.management.base import BaseCommand
from datetime import timedelta
from django.utils.timezone import now
from cl.donate.models import Donation


TOO_MANY_DAYS_AGO = now() - timedelta(days=7)


class Command(BaseCommand):
    help = 'Deletes donations that never went through so they are not in ' \
           'the database forever.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--simulate',
            action='store_true',
            default=False,
            help='Run the command in simulate mode so that no items are '
                 'actually deleted.'
        )

    def handle(self, *args, **options):
        self.stdout.write('%s\n' % '#' * 25)
        if options['simulate']:
            self.stdout.write('# SIMULATE MODE IS ON.  #\n')
        else:
            self.stdout.write('# SIMULATE MODE IS OFF. #\n')
        self.stdout.write('%s\n' % '#' * 25)

        # The statuses here are rather conservative and will likely need
        # updating as further failed payments trickle in.
        qs = {
            'PayPal': Donation.objects.filter(
                payment_provider='paypal',
                date_created__lt=TOO_MANY_DAYS_AGO,
                status__in=[
                    0,
                    1,
                    3,  # Cancelled
                ]
            ),
            'Stripe': Donation.objects.filter(
                payment_provider='stripe',
                date_created__lt=TOO_MANY_DAYS_AGO,
                status__in=[
                    0,
                ]
            ),
        }

        for provider, q in qs.items():
            self.stdout.write('Processing %s:\n' % provider)
            self.stdout.write('  Deleted %s items.\n' % q.count())
            if not options['simulate']:
                q.delete()
