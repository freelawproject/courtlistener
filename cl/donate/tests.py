from datetime import timedelta
from http import HTTPStatus
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.test.client import AsyncClient, Client
from django.urls import reverse
from django.utils.timezone import now

from cl.donate.api_views import MembershipWebhookViewSet
from cl.donate.factories import DonationFactory, NeonWebhookEventFactory
from cl.donate.management.commands.cl_send_donation_reminders import (
    Command as DonationReminderCommand,
)
from cl.donate.models import Donation, NeonMembership, NeonWebhookEvent
from cl.lib.test_helpers import UserProfileWithParentsFactory
from cl.tests.cases import TestCase
from cl.users.models import UserProfile


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
    @patch(
        "cl.donate.api_views.MembershipWebhookViewSet._handle_membership_creation_or_update",
    )
    def test_store_and_truncate_webhook_data(
        self, mock_membership_creation
    ) -> None:
        self.data["eventTrigger"] = "createMembership"
        client = Client()
        r = client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        self.assertEqual(NeonWebhookEvent.objects.all().count(), 1)

        # Make sure to save the webhook payload even if an error occurs.
        mock_membership_creation.side_effect = Exception()
        self.data["data"]["membership"]["accountId"] = "9999"
        with self.assertRaises(Exception):
            client.post(
                reverse("membership-webhooks-list", kwargs={"version": "v3"}),
                data=self.data,
                content_type="application/json",
            )
        failed_log_query = NeonWebhookEvent.objects.filter(account_id="9999")
        self.assertEqual(failed_log_query.count(), 1)
        self.assertEqual(NeonWebhookEvent.objects.all().count(), 2)
        profile_query = UserProfile.objects.filter(neon_account_id="9999")
        self.assertEqual(profile_query.count(), 0)

        NeonWebhookEventFactory.create_batch(17)

        # Update the trigger type and Adds a new webhook to the log. After
        # adding this new record the post_save signal should truncate the
        # events table and keep the latest NEON_MAX_WEBHOOK_NUMBER records
        self.data["eventTrigger"] = "editMembership"
        mock_membership_creation.side_effect = None
        r = client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
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

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

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

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

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

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

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

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

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

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
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
        self.assertEqual(r.status_code, HTTPStatus.CREATED)
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

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

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

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        query = NeonMembership.objects.select_related(
            "user", "user__profile"
        ).filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(membership.user.email, "test@free.law")
        self.assertEqual(membership.user.profile.neon_account_id, "9524")
