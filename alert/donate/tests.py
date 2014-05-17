import simplejson
from datetime import datetime, timedelta
from django.conf import settings
from django.core import mail
from django.test import TestCase, Client
from django.utils.timezone import now
import stripe
from alert.donate.management.commands.cl_send_donation_reminders import Command
from alert.donate.models import Donation


class EmailCommandTest(TestCase):
    fixtures = ['donate_test_data.json']

    def test_sending_an_email(self):
        """Do we send emails correctly?"""
        # Set this value since the JSON will get stale and can't have dynamic dates.
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

    def test_making_a_donation_and_getting_the_callback(self):
        """These two tests must live together because they need to be done sequentially.

        First, we place a donation using the client. Then we send a mock callback to our
        webhook, to make sure it accepts it properly.
        """
        stripe.api_key = settings.STRIPE_SECRET_KEY
        # Create a stripe token (this would normally be done via javascript in the front
        # end when the submit button was pressed)
        token = stripe.Token.create(
            card={
                'number': '4242424242424242',
                'exp_month': '6',
                'exp_year': str(datetime.today().year + 1),
                'cvc': '123',
            }
        )

        # Place a donation as an anonymous (not logged in) person using the
        # token we just got
        r = self.client.post('/donate/', data={
            'amount': '25',
            'payment_provider': 'cc',
            'first_name': 'Barack',
            'last_name': 'Obama',
            'address1': '1600 Pennsylvania Ave.',
            'address2': 'The Whitehouse',
            'city': 'DC',
            'state': 'DC',
            'zip_code': '20500',
            'email': 'barack@freelawproject.org',
            'referrer': 'footer',
            'stripeToken': token.id,
        })

        self.assertEqual(r.status_code, 302)  # 302 because we redirect after a post.

        # Get the stripe event so we can post it to the webhook
        # We don't know the event ID, so we have to get the latest ones, then filter...
        events = stripe.Event.all()
        event = None
        for obj in events.data:
            if obj.data.object.card.fingerprint == token.card.fingerprint:
                event = obj
                break
        self.assertIsNotNone(event, msg="Unable to find correct event for token: %s" % token.card.fingerprint)

        r = self.client.post('/donate/callbacks/stripe/',
                             data=simplejson.dumps(event),
                             content_type='application/json')

        # Does it return properly?
        self.assertEqual(r.status_code, 200)





