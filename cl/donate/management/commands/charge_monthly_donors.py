from datetime import timedelta

from django.core.mail import send_mail
from django.urls import reverse
from django.utils.timezone import now

from cl.donate.models import MonthlyDonation, Donation, PAYMENT_TYPES
from cl.donate.stripe_helpers import process_stripe_payment
from cl.donate.utils import emails, PaymentFailureException, \
    send_failed_subscription_email
from cl.lib.command_utils import VerboseCommand

subscription_failure_threshold = 3


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
            try:
                response = process_stripe_payment(
                    # Stripe rejects the charge if there are decimals;
                    # cast to int.
                    int(m_donation.monthly_donation_amount * 100),
                    m_donation.donor.email,
                    {'customer': m_donation.stripe_customer_id,
                     'metadata': {'recurring': True,
                                  'type': PAYMENT_TYPES.DONATION}},
                    reverse('donate_complete'),
                )
            except PaymentFailureException as e:
                m_donation.failure_count += 1
                if m_donation.failure_count == subscription_failure_threshold:
                    m_donation.enabled = False
                    send_failed_subscription_email(m_donation)

                email = emails['admin_bad_subscription']
                body = email['body'] % (m_donation.pk, e.message)
                send_mail(email['subject'], body, email['from'],
                          email['to'])
                m_donation.save()
                continue

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
            email = emails['admin_donation_report']
            body = email['body'] % (results['amount'],
                                    '\n'.join(results['users']))
            send_mail(email['subject'] % results['amount'], body,
                      email['from'], email['to'])
