import simplejson
from datetime import datetime, timedelta
from django.conf import settings
from django.core import mail
from django.test import TestCase, Client
from django.utils.timezone import now
import stripe
from alert.donate.management.commands.cl_send_donation_reminders import Command
from alert.donate.models import Donation

# From: https://stripe.com/docs/testing#cards
stripe_test_numbers = {
    'good': {
        'visa': '4242424242424242',
    },
    'bad': {
        'cvc_fail': '4000000000000127',
    }
}


class EmailCommandTest(TestCase):
    fixtures = ['donate_test_data.json']

    def test_sending_an_email(self):
        """Do we send emails correctly?"""
        # Set this value since the JSON will get stale and can't have dynamic
        # dates.
        about_a_year_ago = now() - timedelta(days=355)
        Donation.objects.filter(pk=1).update(date_created=about_a_year_ago)

        comm = Command()
        comm.handle()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('you donated $1', mail.outbox[0].body)
        self.assertIn('you donated $1', mail.outbox[0].alternatives[0][0])


class StripeTest(TestCase):
    def setUp(self):
        self.client = Client()

    def make_a_donation(self, cc_number, amount, amount_other=''):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        # Create a stripe token (this would normally be done via javascript in
        # the front end when the submit button was pressed)
        token = stripe.Token.create(
            card={
                'number': cc_number,
                'exp_month': '6',
                'exp_year': str(datetime.today().year + 1),
                'cvc': '123',
            }
        )

        # Place a donation as an anonymous (not logged in) person using the
        # token we just got
        r = self.client.post('/donate/', data={
            'amount': amount,
            'amount_other': amount_other,
            'payment_provider': 'cc',
            'first_name': 'Barack',
            'last_name': 'Obama',
            'address1': '1600 Pennsylvania Ave.',
            'address2': 'The Whitehouse',
            'city': 'DC',
            'state': 'DC',
            'zip_code': '20500',
            'email': 'barack@freelawproject.org',
            'referrer': 'tests.py',
            'stripeToken': token.id,
        })
        return token, r

    def get_stripe_event(self, fingerprint):
        """ Get the stripe event so we can post it to the webhook
        """
        # We don't know the event ID, so we have to get the latest ones, then
        # filter...
        events = stripe.Event.all()
        event = None
        for obj in events.data:
            if obj.data.object.card.fingerprint == fingerprint:
                event = obj
                break

        return event

    def assertEventPostsCorrectly(self, token):
        event = self.get_stripe_event(token.card.fingerprint)
        self.assertIsNotNone(
            event,
            msg="Unable to find correct event for token: %s"
                % token.card.fingerprint
        )

        r = self.client.post('/donate/callbacks/stripe/',
                             data=simplejson.dumps(event),
                             content_type='application/json')

        # Does it return properly?
        self.assertEqual(r.status_code, 200)

    def test_making_a_donation_and_getting_the_callback(self):
        """These two tests must live together because they need to be done
        sequentially.

        First, we place a donation using the client. Then we send a mock
        callback to our webhook, to make sure it accepts it properly.
        """
        token, r = self.make_a_donation(
            stripe_test_numbers['good']['visa'],
            amount='25',
        )

        self.assertEqual(r.status_code, 302)  # 302 (redirect after a post)
        self.assertEventPostsCorrectly(token)

    def test_making_a_donation_with_a_bad_card(self):
        """Do we do the right thing when bad credentials are provided?"""
        stripe.api_key = settings.STRIPE_SECRET_KEY
        # Create a stripe token (this would normally be done via javascript in
        # the front end when the submit button was pressed)
        token, r = self.make_a_donation(
            stripe_test_numbers['bad']['cvc_fail'],
            amount='25',
        )
        self.assertIn("Your card's security code is incorrect.", r.content)
        self.assertEventPostsCorrectly(token)

    def test_making_a_donation_with_a_decimal_value(self):
        """Do things work when people choose to donate with a decimal instead
        of an int?
        """
        stripe.api_key = settings.STRIPE_SECRET_KEY
        token, r = self.make_a_donation(
            stripe_test_numbers['good']['visa'],
            amount='other',
            amount_other='10.00',
        )
        self.assertEqual(r.status_code, 302)  # 302 (redirect after a post)
        self.assertEventPostsCorrectly(token)







