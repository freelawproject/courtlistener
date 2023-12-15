import json
from datetime import datetime, timedelta
from typing import Optional
from unittest import skipIf
from unittest.mock import MagicMock, patch

import stripe
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test.client import AsyncClient
from django.urls import reverse
from django.utils.timezone import now
from rest_framework.status import HTTP_200_OK, HTTP_302_FOUND

from cl.donate.factories import DonationFactory
from cl.donate.management.commands.cl_send_donation_reminders import (
    Command as DonationReminderCommand,
)
from cl.donate.models import FREQUENCIES, PROVIDERS, Donation, MonthlyDonation

# From: https://stripe.com/docs/testing#cards
from cl.donate.utils import emails
from cl.lib.test_helpers import SimpleUserDataMixin
from cl.tests.cases import TestCase

stripe_test_numbers = {
    "good": {"visa": "4242424242424242"},
    "bad": {"cvc_fail": "4000000000000127"},
}


class EmailCommandTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        about_a_year_ago = now() - timedelta(days=354, hours=12)
        d = DonationFactory.create(
            send_annual_reminder=True, status=Donation.PROCESSED
        )
        d.date_created = about_a_year_ago
        d.save()

    def test_sending_an_email(self) -> None:
        """Do we send emails correctly?"""
        DonationReminderCommand().handle()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("you donated $", mail.outbox[0].body)
        self.assertIn("you donated $", mail.outbox[0].alternatives[0][0])


@skipIf(
    settings.PAYPAL_SECRET_KEY is None or settings.PAYPAL_SECRET_KEY == "",
    "Only run PayPal tests if we have an API key available.",
)
@patch("hcaptcha.fields.hCaptchaField.validate", return_value=True)
class DonationFormSubmissionTest(TestCase):
    def setUp(self) -> None:
        self.async_client = AsyncClient()
        self.params = {
            "address1": "123 Sesame St.",
            "city": "New York",
            "state": "NY",
            "zip_code": "12345",
            "wants_newsletter": True,
            "first_name": "Elmo",
            "last_name": "Muppet",
            "email": "pandora@courtlistener.com",
            "send_annual_reminder": True,
            "payment_provider": "paypal",
            "frequency": "once",
        }

    async def test_paypal_with_other_value_as_anonymous(
        self, mock: MagicMock
    ) -> None:
        """Can a paypal donation go through using the "Other" field?"""
        self.params.update({"amount": "other", "amount_other": "5"})
        r = await self.async_client.post(
            reverse("donate"), self.params, follow=True
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

    async def test_paypal_with_regular_value_as_anonymous(
        self, mock: MagicMock
    ) -> None:
        """Can a stripe donation go through using the "Other" field?"""
        self.params.update({"amount": "25"})
        r = await self.async_client.post(
            reverse("donate"), self.params, follow=True
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)


def get_stripe_event(fingerprint):
    """Get the stripe event so we can post it to the webhook"""
    # We don't know the event ID, so we have to get the latest ones, then
    # filter...
    events = stripe.Event.list()
    event = None
    for obj in events.data:
        try:
            if obj.data.object.card.fingerprint == fingerprint:
                event = obj
                break
        except AttributeError:
            # Events don't all have the same attributes, and if we run tests in
            # parallel, we can get different types of events here than the ones
            # we're expecting. Instead of crashing, just try the next event.
            pass

    return event


@skipIf(
    settings.STRIPE_SECRET_KEY is None or settings.STRIPE_SECRET_KEY == "",
    "Only run Stripe tests if we have an API key available.",
)
@patch("hcaptcha.fields.hCaptchaField.validate", return_value=True)
class StripeTest(TestCase):
    def setUp(self) -> None:
        self.async_client = AsyncClient()

    async def make_a_donation(
        self, cc_number, amount, amount_other="", param_overrides=None
    ):
        if param_overrides is None:
            param_overrides = {}

        stripe.api_key = settings.STRIPE_SECRET_KEY
        # Create a stripe token (this would normally be done via javascript in
        # the front end when the submit button was pressed)
        token = stripe.Token.create(
            card={
                "number": cc_number,
                "exp_month": "6",
                "exp_year": str(datetime.today().year + 1),
                "cvc": "123",
            }
        )

        # Place a donation as an anonymous (not logged in) person using the
        # token we just got
        params = {
            "amount": amount,
            "amount_other": amount_other,
            "payment_provider": "cc",
            "first_name": "Barack",
            "last_name": "Obama",
            "address1": "1600 Pennsylvania Ave.",
            "address2": "The Whitehouse",
            "city": "DC",
            "state": "DC",
            "zip_code": "20500",
            "email": "barack@freelawproject.org",
            "referrer": "tests.py",
            "stripeToken": token.id,
            "frequency": "once",
        }
        params.update(param_overrides)
        r = await self.async_client.post(reverse("donate"), data=params)
        return token, r

    async def assertEventPostsCorrectly(self, token):
        event = get_stripe_event(token.card.fingerprint)
        self.assertIsNotNone(
            event,
            msg=f"Unable to find correct event for token: {token.card.fingerprint}",
        )

        r = await self.async_client.post(
            reverse("stripe_callback"),
            data=json.dumps(event),
            content_type="application/json",
        )

        # Does it return properly?
        self.assertEqual(r.status_code, HTTP_200_OK)

    def test_making_a_donation_and_getting_the_callback(
        self, mock: MagicMock
    ) -> None:
        """These two tests must live together because they need to be done
        sequentially.

        First, we place a donation using the client. Then we send a mock
        callback to our webhook, to make sure it accepts it properly.
        """
        token, r = self.make_a_donation(
            stripe_test_numbers["good"]["visa"], amount="25"
        )

        self.assertEqual(
            r.status_code, HTTP_302_FOUND
        )  # redirect after a post
        self.assertEventPostsCorrectly(token)

    def test_making_a_donation_with_a_bad_card(self, mock: MagicMock) -> None:
        """Do we do the right thing when bad credentials are provided?"""
        stripe.api_key = settings.STRIPE_SECRET_KEY
        # Create a stripe token (this would normally be done via javascript in
        # the front end when the submit button was pressed)
        token, r = self.make_a_donation(
            stripe_test_numbers["bad"]["cvc_fail"], amount="25"
        )
        self.assertIn(
            "Your card's security code is incorrect.", r.content.decode()
        )
        self.assertEventPostsCorrectly(token)

    def test_making_a_donation_with_a_decimal_value(
        self, mock: MagicMock
    ) -> None:
        """Do things work when people choose to donate with a decimal instead
        of an int?
        """
        stripe.api_key = settings.STRIPE_SECRET_KEY
        token, r = self.make_a_donation(
            stripe_test_numbers["good"]["visa"],
            amount="other",
            amount_other="10.00",
        )
        self.assertEqual(
            r.status_code, HTTP_302_FOUND
        )  # redirect after a post
        self.assertEventPostsCorrectly(token)

    def test_making_a_donation_that_is_too_small(
        self, mock: MagicMock
    ) -> None:
        """Donations less than $5 are no good."""
        stripe.api_key = settings.STRIPE_SECRET_KEY
        token, r = self.make_a_donation(
            stripe_test_numbers["good"]["visa"],
            amount="other",
            amount_other="0.40",
        )
        self.assertEqual(r.status_code, HTTP_200_OK)

    def test_making_a_monthly_donation(self, mock: MagicMock) -> None:
        """Can we make a monthly donation correctly?"""
        stripe.api_key = settings.STRIPE_SECRET_KEY
        token, r = self.make_a_donation(
            stripe_test_numbers["good"]["visa"],
            amount="25",
            param_overrides={"frequency": FREQUENCIES.MONTHLY},
        )
        # Redirect after a successful POST?
        self.assertEqual(r.status_code, HTTP_302_FOUND)
        self.assertEventPostsCorrectly(token)


@skipIf(
    settings.STRIPE_SECRET_KEY is None or settings.STRIPE_SECRET_KEY == "",
    "Only run Stripe tests if we have an API key available.",
)
@skipIf(
    settings.PAYPAL_SECRET_KEY is None or settings.PAYPAL_SECRET_KEY == "",
    "Only run PayPal tests if we have an API key available.",
)
@patch("hcaptcha.fields.hCaptchaField.validate", return_value=True)
class DonationIntegrationTest(SimpleUserDataMixin, TestCase):
    """Attempt to handle all types/rates/providers/etc of payments

    See discussion in: https://github.com/freelawproject/courtlistener/issues/928
    """

    credentials = {
        "username": "pandora",
        "password": "password",
    }

    def setUp(self) -> None:
        self.async_client = AsyncClient()

        self.params = {
            # Donation info
            "frequency": FREQUENCIES.ONCE,
            "payment_provider": PROVIDERS.PAYPAL,
            "amount": "25",
            # Personal info
            "first_name": "Elmo",
            "last_name": "Muppet",
            "email": "pandora@courtlistener.com",
            "address1": "123 Sesame St.",
            "city": "New York",
            "state": "NY",
            "zip_code": "12345",
            # Tailing checkboxes
            "wants_newsletter": True,
            "send_annual_reminder": True,
        }

        self.new_email = "some-user@free.law"

    async def tearDown(self) -> None:
        await Donation.objects.all().adelete()
        await MonthlyDonation.objects.all().adelete()
        await User.objects.filter(email=self.new_email).adelete()

    async def do_post_and_assert(
        self,
        url: str,
        target: Optional[str] = None,
    ) -> None:
        r = await self.async_client.post(url, data=self.params, follow=True)
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)
        if target is not None:
            self.assertRedirects(r, target)

    def assertEmailSubject(self, subject: str) -> None:
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, subject)

    def make_stripe_token(self) -> None:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.token = stripe.Token.create(
            card={
                "number": stripe_test_numbers["good"]["visa"],
                "exp_month": "6",
                "exp_year": str(datetime.today().year + 1),
                "cvc": "123",
            }
        )

    def set_stripe_params(self) -> None:
        self.params["payment_provider"] = PROVIDERS.CREDIT_CARD
        self.make_stripe_token()
        self.params["stripeToken"] = self.token.id

    def set_new_stub_params(self) -> None:
        self.params["email"] = self.new_email

    def set_monthly_params(self) -> None:
        self.params["frequency"] = FREQUENCIES.MONTHLY

    async def check_monthly_donation_created(self) -> None:
        self.assertEqual(await MonthlyDonation.objects.acount(), 1)

    async def do_stripe_callback(self) -> None:
        event = get_stripe_event(self.token.card.fingerprint)
        await self.async_client.post(
            reverse("stripe_callback"),
            data=json.dumps(event),
            content_type="application/json",
        )

    async def test_one_time_paypal_logged_in_donation(
        self, mock: MagicMock
    ) -> None:
        self.assertTrue(await self.async_client.alogin(**self.credentials))
        await self.do_post_and_assert(reverse("donate"))

    async def test_one_time_paypal_logged_out_donation_existing_account(
        self, mock: MagicMock
    ) -> None:
        await self.async_client.alogout()
        await self.do_post_and_assert(reverse("donate"))

    async def test_one_time_paypal_logged_out_donation_new_stub(
        self, mock: MagicMock
    ) -> None:
        self.set_new_stub_params()
        await self.do_post_and_assert(reverse("donate"))
        # Did we create an account?
        self.assertTrue(
            await User.objects.filter(email=self.new_email).aexists()
        )

    async def test_one_time_stripe_logged_in_donation(
        self, mock: MagicMock
    ) -> None:
        self.set_stripe_params()
        self.assertTrue(await self.async_client.alogin(**self.credentials))
        await self.do_post_and_assert(reverse("donate"))

    async def test_one_time_stripe_logged_out_donation_existing_account(
        self, mock: MagicMock
    ) -> None:
        self.set_stripe_params()
        await self.async_client.alogout()
        await self.do_post_and_assert(reverse("donate"))

    async def test_one_time_stripe_logged_out_donation_new_stub(
        self, mock: MagicMock
    ) -> None:
        self.set_stripe_params()
        await self.async_client.alogout()
        self.set_new_stub_params()
        await self.do_post_and_assert(reverse("donate"))

    async def test_monthly_stripe_logged_in_donation(
        self, mock: MagicMock
    ) -> None:
        self.set_monthly_params()
        self.set_stripe_params()
        self.assertTrue(await self.async_client.alogin(**self.credentials))
        await self.do_post_and_assert(reverse("donate"))
        await self.check_monthly_donation_created()

    async def test_monthly_stripe_logged_out_donation_existing_account(
        self, mock: MagicMock
    ) -> None:
        self.set_monthly_params()
        self.set_stripe_params()
        await self.async_client.alogout()
        await self.do_post_and_assert(reverse("donate"))
        await self.check_monthly_donation_created()

    async def test_monthly_stripe_logged_out_donation_new_stub(
        self, mock: MagicMock
    ) -> None:
        self.set_monthly_params()
        self.set_stripe_params()
        await self.async_client.alogout()
        self.set_new_stub_params()
        await self.do_post_and_assert(reverse("donate"))
        await self.check_monthly_donation_created()

    async def test_one_time_stripe_logged_in_payment(
        self, mock: MagicMock
    ) -> None:
        self.set_stripe_params()
        self.assertTrue(await self.async_client.alogin(**self.credentials))
        await self.do_post_and_assert(reverse("cc_payment"))

    async def test_one_time_stripe_logged_out_payment_existing_account(
        self, mock: MagicMock
    ) -> None:
        self.set_stripe_params()
        await self.async_client.alogout()
        await self.do_post_and_assert(reverse("cc_payment"))

    async def test_one_time_stripe_logged_out_payment_new_stub(
        self, mock: MagicMock
    ) -> None:
        self.set_stripe_params()
        await self.async_client.alogout()
        self.set_new_stub_params()
        await self.do_post_and_assert(reverse("cc_payment"))

    #
    # Test redirection and emails
    #
    # Paypal does some annoying redirection stuff that requires a log-in and
    # makes it nearly impossible to test as we do Stripe. Below we should have
    # a test for email and redirection of paypal payments, but it just wasn't
    # possible without undue effort. This is why we like Stripe.
    async def test_email_and_redirection_regular_donation_stripe(
        self, mock: MagicMock
    ) -> None:
        self.set_stripe_params()
        await self.async_client.alogout()
        await self.do_post_and_assert(
            reverse("donate"), target=reverse("donate_complete")
        )
        await self.do_stripe_callback()
        self.assertEmailSubject(emails["donation_thanks"]["subject"])

    async def test_email_and_redirection_monthly_donation(
        self, mock: MagicMock
    ) -> None:
        await self.async_client.alogout()
        self.set_stripe_params()
        self.set_monthly_params()
        await self.do_post_and_assert(
            reverse("donate"), target=reverse("donate_complete")
        )
        await self.check_monthly_donation_created()
        await self.do_stripe_callback()
        self.assertEmailSubject(emails["donation_thanks_recurring"]["subject"])

    async def test_email_and_redirection_one_time_payment(
        self, mock: MagicMock
    ) -> None:
        await self.async_client.alogout()
        self.set_stripe_params()
        await self.do_post_and_assert(
            reverse("cc_payment"), target=reverse("payment_complete")
        )
        await self.do_stripe_callback()
        self.assertEmailSubject(emails["payment_thanks"]["subject"])
