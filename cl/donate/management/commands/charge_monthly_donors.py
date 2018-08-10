from datetime import timedelta

from django.core.mail import send_mail
from django.utils.timezone import now

from cl.donate.models import MonthlyDonation, Donation
from cl.donate.stripe_helpers import process_stripe_payment
from cl.donate.utils import emails, PaymentFailureException
from cl.lib.command_utils import VerboseCommand


class Command(VerboseCommand):
    help = "Charges people that have monthly subscriptions."

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        m_donations = MonthlyDonation.objects.filter(
            enabled=True,
            monthly_donation_day=now().date().day,
            # This is a safety to account for timezones. We want to be very
            # careful that we don't double-bill people right when they sign up,
            # so this ensures that we don't bill anybody except when the
            # recurring donation is more than 15 days old.
            date_created__lt=now() - timedelta(days=15),
        ).order_by('-date_created')

        results = {'amount': 0, 'users': []}
        for m_donation in m_donations:
            if m_donation.payment_provider == PROVIDERS.CREDIT_CARD:
                response = process_stripe_payment(
                    # Stripe rejects the charge if there are decimals;
                    # cast to int.
                    int(m_donation.monthly_donation_amount * 100),
                    m_donation.donor.email,
                    {'customer': m_donation.stripe_customer_id,
                     'metadata': {'recurring': True}},
                )
            else:
                raise NotImplementedError(
                    "%s is not a supported provider for monthly donations" %
                    m_donation.payment_provider
                )

            if response.get('status') == Donation.AWAITING_PAYMENT:
                # It worked. Create a donation in our system as well.
                results['amount'] += m_donation.monthly_donation_amount
                results['users'].append(' - %s %s (%s): $%s' % (
                    m_donation.donor.first_name,
                    m_donation.donor.last_name,
                    m_donation.donor.email,
                    m_donation.monthly_donation_amount,
                ))
                Donation.objects.create(
                    donor=m_donation.donor,
                    amount=m_donation.monthly_donation_amount,
                    payment_provider=m_donation.payment_provider,
                    status=response['status'],
                    payment_id=response['payment_id'],
                    # Only applies to PayPal
                    transaction_id=response.get('transaction_id'),
                    referrer='monthly_donation_%s' % m_donation.pk,
                )
                # Thank you email is triggered later when the stripe callback
                # is triggered.

        if results['users']:
            email = emails['donation_report']
            send_mail(
                email['subject'] % results['amount'],
                email['body'] % (results['amount'],
                                 '\n'.join(results['users'])),
                email['from'],
                email['to'],
            )
