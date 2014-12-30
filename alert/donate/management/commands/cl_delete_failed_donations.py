from optparse import make_option
from django.core.management.base import BaseCommand
from datetime import timedelta, date
from alert.donate.models import Donation


TOO_MANY_DAYS_AGO = date.today() - timedelta(days=7)


class Command(BaseCommand):
    help = 'Deletes donations that never went through so they are not in ' \
           'the database forever.'
    option_list = BaseCommand.option_list + (
        make_option(
            '--simulate',
            dest='simulate',
            action='store_true',
            default=False,
            help='Run the command in simulate mode so that no items are '
                 'actually deleted.'
        ),
    )

    def handle(self, *args, **options):
        simulate = options['simulate']

        self.stdout.write('#########################\n')
        if simulate:
            self.stdout.write('# SIMULATE MODE IS ON.  #\n')
        else:
            self.stdout.write('# SIMULATE MODE IS OFF. #\n')
        self.stdout.write('#########################\n')

        # The statuses here are rather conservative and will likely need
        # updating as further failed payments trickle in.
        qs = {
            'Dwolla': Donation.objects.filter(
                payment_provider='dwolla',
                date_created__lt=TOO_MANY_DAYS_AGO,
                status__in=[
                    0,  # Awaiting payment
                    1,  # Unknown error
                ],
            ),
            'PayPal': Donation.objects.filter(
                payment_provider='paypal',
                date_created__lt=TOO_MANY_DAYS_AGO,
                status__in=[
                    0,
                    1,
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

        for provider, q in qs.iteritems():
            self.stdout.write('Processing %s:\n' % provider)
            self.stdout.write('  Deleted %s items.\n' % q.count())
            if not simulate:
                q.delete()
