from django.utils.timezone import now

from cl.donate.models import MonthlyDonation, PROVIDERS, Donation
from cl.donate.stripe_helpers import process_stripe_payment
from cl.lib.command_utils import VerboseCommand


class Command(VerboseCommand):
    help = "Charges people that have monthly subscriptions."

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        m_donations = MonthlyDonation.objects.filter(
            enabled=True,
            monthly_donation_day=now().date().day,
        )

        for m_donation in m_donations:
            # Charge each m_donation.
            if m_donation.payment_provider == PROVIDERS.CREDIT_CARD:
                response = process_stripe_payment(
                    m_donation.monthly_donation_amount * 100,
                    m_donation.donor.email,
                    {'customer', m_donation.stripe_customer_id},
                )
                if response['status'] == Donation.AWAITING_PAYMENT:
                    # It worked. Create a donation in our system as well.
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
