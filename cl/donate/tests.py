import json
from datetime import datetime, timedelta
from typing import Optional
from unittest import skipIf
from unittest.mock import MagicMock, patch

import stripe
import time_machine
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from django.test.client import AsyncClient, Client
from django.urls import reverse
from django.utils.timezone import now
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_302_FOUND

from cl.donate.api_views import MembershipWebhookViewSet
from cl.donate.factories import (
    DonationFactory,
    MonthlyDonationFactory,
    NeonWebhookEventFactory,
)
from cl.donate.management.commands.charge_monthly_donors import (
    Command as ChargeMonthlyDonorsCommand,
)
from cl.donate.management.commands.cl_send_donation_reminders import (
    Command as DonationReminderCommand,
)
from cl.donate.models import (
    FREQUENCIES,
    PROVIDERS,
    Donation,
    MonthlyDonation,
    NeonMembership,
    NeonWebhookEvent,
)
from cl.donate.utils import PaymentFailureException

# From: https://stripe.com/docs/testing#cards
from cl.lib.test_helpers import (
    SimpleUserDataMixin,
    UserProfileWithParentsFactory,
)
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


class ChargeMonthlyDonationTest(TestCase):
    def setUp(self) -> None:
        twenty_days_ago = now() - timedelta(days=20)
        with time_machine.travel(twenty_days_ago, tick=False):
            self.monthly_donation = MonthlyDonationFactory(
                stripe_customer_id="test_1"
            )
        self.monthly_donation.monthly_donation_day = now().date().day
        self.monthly_donation.save()

    @patch(
        "cl.donate.management.commands.charge_monthly_donors.process_stripe_payment",
        side_effect=PaymentFailureException("failed charge"),
    )
    def test_can_send_failed_subscription_email(
        self, mock_process_stripe_payment
    ):
        ChargeMonthlyDonorsCommand().handle()

        self.monthly_donation.refresh_from_db()
        self.assertFalse(self.monthly_donation.enabled)
        self.assertEqual(self.monthly_donation.failure_count, 1)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            "https://donate.free.law/forms/membership", mail.outbox[0].body
        )
        self.assertIn(
            "https://donate.free.law/forms/supportflp", mail.outbox[0].body
        )


class MembershipWebhookTest(TestCase):
    def setUp(self) -> None:
        self.async_client = AsyncClient()
        self.user_profile = UserProfileWithParentsFactory()
        self.user_profile.neon_account_id = "1234"
        self.user_profile.save()

        self.data = {
            "eventTimestamp": "2017-05-04T03:42:59.000-06:00",
            "data": {
                "membership": {
                    "membershipId": "12345",
                    "accountId": "1234",
                    "membershipName": "CL Membership - Tier 1",
                    "termEndDate": "2024-01-01-05:00",
                    "status": "SUCCEEDED",
                }
            },
        }

    @override_settings(NEON_MAX_WEBHOOK_NUMBER=10)
    def test_store_and_truncate_webhook_data(self) -> None:
        self.data["eventTrigger"] = "createMembership"
        client = Client()
        r = client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTP_201_CREATED)
        self.assertEqual(NeonWebhookEvent.objects.all().count(), 1)

        NeonWebhookEventFactory.create_batch(18)

        # Update the trigger type and Adds a new webhook to the log. After
        # adding this new record the post_save signal should truncate the
        # events table and keep the latest NEON_MAX_WEBHOOK_NUMBER records
        self.data["eventTrigger"] = "editMembership"
        client = Client()
        r = client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTP_201_CREATED)
        self.assertEqual(NeonWebhookEvent.objects.all().count(), 10)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_create_new_membership(self, mock_store_webhook) -> None:
        self.data["eventTrigger"] = "createMembership"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTP_201_CREATED)

        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(membership.user_id, self.user_profile.user.pk)
        self.assertEqual(membership.level, NeonMembership.TIER_1)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_avoid_creating_membership_for_failed_transaction(
        self, mock_store_webhook
    ) -> None:
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["status"] = "FAILED"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTP_201_CREATED)

        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 0)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_skip_update_membership_webhook_with_old_data(
        self, mock_store_webhook
    ) -> None:
        self.data["eventTrigger"] = "createMembership"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTP_201_CREATED)

        self.data["eventTrigger"] = "updateMembership"
        self.data["data"]["membership"]["membershipId"] = "12344"
        self.data["data"]["membership"][
            "membershipName"
        ] = "CL Membership - Tier 4"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTP_201_CREATED)

        # checks the neon_id was not updated
        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        # checks the level was not updated
        membership = await query.afirst()
        self.assertEqual(membership.level, NeonMembership.TIER_1)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_update_membership(self, mock_store_webhook) -> None:
        await NeonMembership.objects.acreate(
            user=self.user_profile.user,
            neon_id="12345",
            level=NeonMembership.TIER_1,
        )

        # Update the membership level and the trigger type
        self.data["eventTrigger"] = "editMembership"
        self.data["data"]["membership"][
            "membershipName"
        ] = "CL Membership - Tier 4"

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTP_201_CREATED)
        membership = await NeonMembership.objects.aget(neon_id="12345")

        self.assertEqual(membership.neon_id, "12345")
        self.assertEqual(membership.level, NeonMembership.TIER_4)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_delete_membership(self, mock_store_webhook) -> None:
        await NeonMembership.objects.acreate(
            user=self.user_profile.user,
            neon_id="9876",
            level=NeonMembership.BASIC,
        )

        # Update trigger type and membership id
        self.data["eventTrigger"] = "deleteMembership"
        self.data["data"]["membership"]["membershipId"] = "9876"

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        query = NeonMembership.objects.filter(neon_id="9876")
        self.assertEqual(r.status_code, HTTP_201_CREATED)
        self.assertEqual(await query.acount(), 0)

    @patch(
        "cl.lib.neon_utils.NeonClient.get_acount_by_id",
    )
    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_create_stub_account_missing_address(
        self, mock_store_webhook, mock_get_account
    ):
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["accountId"] = "1245"

        # mocks the Neon API response
        mock_get_account.return_value = {
            "accountId": "1245",
            "primaryContact": {
                "email1": "test@free.law",
                "firstName": "test",
                "lastName": "test",
                "addresses": [],
            },
        }

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTP_201_CREATED)

        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

    @patch(
        "cl.lib.neon_utils.NeonClient.get_acount_by_id",
    )
    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_can_create_stub_account_properly(
        self, mock_store_webhook, mock_get_account
    ):
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["accountId"] = "9524"

        # mocks the Neon API response
        mock_get_account.return_value = {
            "accountId": "9524",
            "primaryContact": {
                "email1": "test@free.law",
                "firstName": "test",
                "lastName": "test",
                "addresses": [
                    {
                        "addressId": "91449",
                        "addressLine1": "Suite 338 886 Hugh Shoal",
                        "addressLine2": "",
                        "addressLine3": None,
                        "addressLine4": None,
                        "city": "New Louveniamouth",
                        "stateProvince": {
                            "code": "WA",
                            "name": "Washington",
                            "status": None,
                        },
                        "country": {
                            "id": "1",
                            "name": "United States of America",
                            "status": None,
                        },
                        "territory": None,
                        "zipCode": "30716",
                    }
                ],
            },
        }

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTP_201_CREATED)

        query = NeonMembership.objects.select_related(
            "user", "user__profile"
        ).filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(membership.user.email, "test@free.law")
        self.assertEqual(membership.user.profile.neon_account_id, "9524")
