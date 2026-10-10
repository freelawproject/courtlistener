from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import requests
import time_machine
from asgiref.sync import sync_to_async
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.test.client import AsyncClient, Client
from django.urls import reverse
from django.utils.timezone import now

from cl.api.constants import TIER_1_RATES, TIER_2_RATES
from cl.api.models import APIThrottle, ThrottleType
from cl.donate.api_views import MembershipWebhookViewSet
from cl.donate.factories import NeonMembershipFactory, NeonWebhookEventFactory
from cl.donate.models import (
    MembershipPaymentStatus,
    NeonMembership,
    NeonMembershipLevel,
    NeonWebhookEvent,
)
from cl.lib.neon_utils import NeonClient
from cl.lib.test_helpers import UserProfileWithParentsFactory
from cl.tests.cases import SimpleTestCase, TestCase
from cl.users.models import UserProfile
from cl.users.utils import create_stub_account


class MembershipWebhookTest(TestCase):
    def setUp(self) -> None:
        self.async_client = AsyncClient()
        self.user_profile = UserProfileWithParentsFactory(
            user__email="test_3@email.com"
        )
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
        "cl.donate.api_views.MembershipWebhookViewSet._handle_membership_creation",
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
        self.assertEqual(membership.level, NeonMembershipLevel.TIER_1)

    @patch("cl.donate.api_views.tag_zoho_record_for_membership")
    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_create_membership_fires_zoho_tag_task(
        self, mock_store_webhook, mock_tag_task
    ) -> None:
        """createMembership webhooks enqueue the Zoho tag task with the
        new membership's level so the user's Zoho record gets the
        appropriate tag."""
        self.data["eventTrigger"] = "createMembership"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        mock_tag_task.delay.assert_called_once_with(
            self.user_profile.user.pk, NeonMembershipLevel.TIER_1
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_can_create_membership_for_failed_transaction(
        self, mock_store_webhook
    ) -> None:
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["status"] = "FAILED"
        self.data["data"]["membership"]["payments"] = [
            {"paymentStatus": "Failed"}
        ]
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.FAILED
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_can_create_membership_for_pending_transaction(
        self, mock_store_webhook
    ) -> None:
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["status"] = "PENDING"
        self.data["data"]["membership"]["payments"] = [
            {"paymentStatus": "Pending"}
        ]
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.PENDING
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_create_membership_with_no_payment_data_is_succeeded(
        self, mock_store_webhook
    ) -> None:
        """Memberships without payment data (manual grants, free tiers) land as SUCCEEDED."""
        self.data["eventTrigger"] = "createMembership"
        # Default payload has no "payments" key — that's the case under test.
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        membership = await NeonMembership.objects.filter(
            neon_id="12345"
        ).afirst()
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.SUCCEEDED
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_unknown_payment_status_falls_back_to_pending(
        self, mock_store_webhook
    ) -> None:
        """Unrecognized non-empty paymentStatus values still map to PENDING."""
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["payments"] = [
            {"paymentStatus": "in_review"}
        ]
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        membership = await NeonMembership.objects.filter(
            neon_id="12345"
        ).afirst()
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.PENDING
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_edu_unconfirmed_email_sends_confirmation(
        self, mock_store_webhook
    ) -> None:
        self.user_profile.user.email = "test@university.edu"
        await self.user_profile.user.asave()

        # mark user's email as unconfirmed
        self.user_profile.email_confirmed = False
        await self.user_profile.asave()

        # Simulate incoming webhook data for creating an EDU membership
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["membershipName"] = "EDU Membership"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )

        # Assert that the webhook request was accepted
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        # A confirmation email should be sent to the user
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertIn(
            "Confirm Your .edu Membership Email", message_sent.subject
        )
        await self.user_profile.arefresh_from_db()
        self.assertIn(self.user_profile.activation_key, message_sent.body)
        self.assertIn("test@university.edu", message_sent.to)

        # The EDU membership should still be created for the user
        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(membership.level, NeonMembershipLevel.EDU)

    @patch(
        "cl.lib.neon_utils.NeonClient.get_account_by_id",
    )
    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_no_edu_account_sends_registration_email(
        self, mock_store_webhook, mock_get_account
    ) -> None:
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["accountId"] = "9999"
        self.data["data"]["membership"]["membershipName"] = "EDU Membership"

        # mocks the Neon API response
        mock_get_account.return_value = {
            "accountId": "9999",
            "primaryContact": {
                "email1": "test@free.edu",
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

        # Webhook should be accepted
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        # A registration email should be sent to the user
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertIn(
            "Complete Your .edu Membership Registration", message_sent.subject
        )
        self.assertIn("test@free.edu", message_sent.to)

        # The EDU membership should still be created for the user
        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(membership.level, NeonMembershipLevel.EDU)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_reject_edu_membership_for_non_edu_mail(
        self, mock_store_webhook
    ) -> None:
        # Ensure the user's email is confirmed
        self.user_profile.email_confirmed = True
        await self.user_profile.asave()

        # Simulate a webhook request for an EDU membership
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["membershipName"] = "EDU Membership"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        # Verify that the EDU membership was not created (user lacks .edu email)
        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 0)

        # A rejection email should be sent to inform the user
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertIn("Request for a .edu Membership", message_sent.subject)
        self.assertIn(self.user_profile.user.email, message_sent.to)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_create_edu_membership_for_valid_user(
        self, mock_store_webhook
    ) -> None:
        # Set a valid .edu email for the user
        self.user_profile.user.email = "test@university.edu"
        await self.user_profile.user.asave()

        # Mark the user's email as confirmed
        self.user_profile.email_confirmed = True
        await self.user_profile.asave()

        # Simulate a webhook request to create an EDU membership
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["membershipName"] = "EDU Membership"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        # Verify that the EDU membership was created
        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(membership.level, NeonMembershipLevel.EDU)
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.SUCCEEDED
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_create_lso_1_membership(self, mock_store_webhook) -> None:
        """LSO 1 webhooks create an active membership at the LSO_1 level."""
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["membershipName"] = "LSO 1"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        query = NeonMembership.objects.filter(neon_id="12345")
        self.assertEqual(await query.acount(), 1)

        membership = await query.afirst()
        self.assertEqual(membership.level, NeonMembershipLevel.LSO_1)
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.SUCCEEDED
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_edu_membership_with_explicit_payment_status(
        self, mock_store_webhook
    ) -> None:
        """EDU webhooks with explicit payment info should respect that value."""
        self.user_profile.user.email = "test@university.edu"
        await self.user_profile.user.asave()

        self.user_profile.email_confirmed = True
        await self.user_profile.asave()

        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["membershipName"] = "EDU Membership"
        self.data["data"]["membership"]["payments"] = [
            {"paymentStatus": "Failed"}
        ]
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        membership = await NeonMembership.objects.filter(
            neon_id="12345"
        ).afirst()
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.FAILED
        )

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
        self.data["data"]["membership"]["membershipName"] = (
            "CL Membership - Tier 4"
        )
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
        self.assertEqual(membership.level, NeonMembershipLevel.TIER_1)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_update_membership(self, mock_store_webhook) -> None:
        await NeonMembership.objects.acreate(
            user=self.user_profile.user,
            neon_id="12345",
            level=NeonMembershipLevel.TIER_1,
        )

        # Update the membership level and the trigger type
        self.data["eventTrigger"] = "editMembership"
        self.data["data"]["membership"]["membershipName"] = (
            "CL Membership - Tier 4"
        )

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        membership = await NeonMembership.objects.aget(neon_id="12345")

        self.assertEqual(membership.neon_id, "12345")
        self.assertEqual(membership.level, NeonMembershipLevel.TIER_4)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_can_update_pending_membership(
        self, mock_store_webhook
    ) -> None:
        await NeonMembership.objects.acreate(
            user=self.user_profile.user,
            neon_id="12345",
            level=NeonMembershipLevel.TIER_1,
            payment_status=MembershipPaymentStatus.PENDING,
        )

        # Update payment status
        self.data["eventTrigger"] = "updateMembership"
        self.data["data"]["membership"]["payments"] = [
            {"paymentStatus": "Succeeded"}
        ]

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        membership = await NeonMembership.objects.aget(neon_id="12345")

        self.assertEqual(membership.neon_id, "12345")
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.SUCCEEDED
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_can_update_failed_membership(
        self, mock_store_webhook
    ) -> None:
        await NeonMembership.objects.acreate(
            user=self.user_profile.user,
            neon_id="12345",
            level=NeonMembershipLevel.TIER_1,
            payment_status=MembershipPaymentStatus.FAILED,
        )

        # Update payment status
        self.data["eventTrigger"] = "updateMembership"
        self.data["data"]["membership"]["payments"] = [
            {"paymentStatus": "Succeeded"}
        ]

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v4"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        membership = await NeonMembership.objects.aget(neon_id="12345")

        self.assertEqual(membership.neon_id, "12345")
        self.assertEqual(
            membership.payment_status, MembershipPaymentStatus.SUCCEEDED
        )

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_delete_membership(self, mock_store_webhook) -> None:
        await NeonMembership.objects.acreate(
            user=self.user_profile.user,
            neon_id="9876",
            level=NeonMembershipLevel.BASIC,
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
        "cl.lib.neon_utils.NeonClient.get_account_by_id",
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
        "cl.lib.neon_utils.NeonClient.get_account_by_id",
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
        self.assertEqual(membership.user.first_name, "test")
        self.assertEqual(membership.user.last_name, "test")

    @patch(
        "cl.lib.neon_utils.NeonClient.get_account_by_id",
    )
    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_uses_insensitive_match_for_emails(
        self, mock_store_webhook, mock_get_account
    ):
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["accountId"] = "9524"
        # mocks the Neon API response
        mock_get_account.return_value = {
            "accountId": "9524",
            "primaryContact": {
                "email1": "TesT_3@email.com",
                "firstName": "test",
                "lastName": "test",
            },
        }

        # Assert the existing user's Neon account ID is different than "9524"
        self.assertNotEqual(self.user_profile.neon_account_id, "9524")

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

        # Check the new membership is linked to the expected user
        membership = await query.afirst()
        self.assertEqual(membership.user_id, self.user_profile.user_id)

        # Confirm the user's email address remains unchanged
        self.assertEqual(membership.user.email, "test_3@email.com")

        # Check the neon_account_id was updated properly
        self.assertEqual(membership.user.profile.neon_account_id, "9524")

    @patch(
        "cl.lib.neon_utils.requests.get",
    )
    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_uses_cl_id_from_neon_to_match_users(
        self, mock_store_webhook, mock_get
    ):
        # Mock the Neon API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "individualAccount": {
                "accountId": "9524",
                "primaryContact": {
                    "firstName": "test",
                    "lastName": "test",
                },
                "accountCustomFields": [
                    {"name": "CL User Id", "value": self.user_profile.user_id}
                ],
            }
        }
        mock_get.return_value = mock_response

        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["accountId"] = "9524"
        # Assert the existing user's Neon account ID is different than "9524"
        self.assertNotEqual(self.user_profile.neon_account_id, "9524")

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

        # Verify the new membership is linked to the expected user
        # The match should be based on the "CL User Id" custom field, since
        # the mocked response does not include a matching email or Neon ID.
        membership = await query.afirst()
        self.assertEqual(membership.user_id, self.user_profile.user_id)

        # Confirm the user's email address remains unchanged
        self.assertEqual(membership.user.email, "test_3@email.com")

        # Check the neon_account_id was updated properly
        self.assertEqual(membership.user.profile.neon_account_id, "9524")

    @patch(
        "cl.lib.neon_utils.NeonClient.get_account_by_id",
    )
    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    async def test_updates_account_with_recent_login(
        self, mock_store_webhook, mock_get_account
    ) -> None:
        # Create two profile records - one stub, one regular user,
        _, stub_profile = await sync_to_async(create_stub_account)(
            {
                "email": "test_4@email.com",
                "first_name": "test",
                "last_name": "test",
            },
            defaultdict(lambda: ""),
        )

        user_profile = await sync_to_async(UserProfileWithParentsFactory)(
            user__email="test_4@email.com"
        )
        user = user_profile.user
        # Updates last login field for the regular user
        user.last_login = now()
        await user.asave()

        # mocks the Neon API response
        mock_get_account.return_value = {
            "accountId": "1246",
            "primaryContact": {
                "email1": "test_4@email.com",
                "firstName": "test",
                "lastName": "test",
            },
        }

        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["accountId"] = "1246"
        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        # Refresh both profiles to ensure updated data
        await stub_profile.arefresh_from_db()
        await user_profile.arefresh_from_db()

        # Verify stub account remains untouched
        self.assertEqual(stub_profile.neon_account_id, "")

        # Verify regular user account is updated with Neon data
        self.assertEqual(user_profile.neon_account_id, "1246")


class ProfileMembershipTest(TestCase):
    def setUp(self) -> None:
        self.user_profile = UserProfileWithParentsFactory()

    def test_is_member_returns_true_until_termination_date_passes(self):
        """
        checks the `is_member` property correctly identifies a user as a member
        until their termination date has passed
        """
        termination_date = now().date() + timedelta(weeks=4)
        NeonMembership.objects.create(
            level=NeonMembershipLevel.LEGACY,
            user=self.user_profile.user,
            termination_date=termination_date,
            payment_status=MembershipPaymentStatus.SUCCEEDED,
        )
        self.user_profile.refresh_from_db()

        # Test just before the termination date
        with time_machine.travel(
            termination_date - timedelta(seconds=1), tick=False
        ):
            self.assertTrue(self.user_profile.is_member)

        # Test exactly at the termination date
        with time_machine.travel(termination_date, tick=False):
            self.assertTrue(self.user_profile.is_member)

        with time_machine.travel(
            termination_date + timedelta(hours=4), tick=False
        ):
            self.assertTrue(self.user_profile.is_member)

        # Test a full day after the termination date
        with time_machine.travel(
            termination_date + timedelta(days=1), tick=False
        ):
            self.assertFalse(
                self.user_profile.is_member,
                "Should not be a member a day after termination.",
            )

    def test_is_member_true_when_payment_pending(self):
        """A member keeps benefits while their payment is still pending."""
        NeonMembership.objects.create(
            level=NeonMembershipLevel.LEGACY,
            user=self.user_profile.user,
            payment_status=MembershipPaymentStatus.PENDING,
        )
        self.user_profile.refresh_from_db()
        self.assertTrue(self.user_profile.is_member)

    def test_is_member_false_when_payment_failed(self):
        """A failed/declined payment revokes membership benefits."""
        NeonMembership.objects.create(
            level=NeonMembershipLevel.LEGACY,
            user=self.user_profile.user,
            payment_status=MembershipPaymentStatus.FAILED,
        )
        self.user_profile.refresh_from_db()
        self.assertFalse(self.user_profile.is_member)


class MembershipWebhookThrottleSyncTest(TestCase):
    """End-to-end tests that Neon webhooks sync APIThrottle rows."""

    def setUp(self) -> None:
        self.async_client = AsyncClient()
        self.user_profile = UserProfileWithParentsFactory(
            user__email="test_throttle_sync@email.com"
        )
        self.user_profile.neon_account_id = "1234"
        self.user_profile.save()

        self.data = {
            "eventTimestamp": "2026-04-26T03:42:59.000-06:00",
            "data": {
                "membership": {
                    "membershipId": "12345",
                    "accountId": "1234",
                    "membershipName": "CL Membership - Tier 1",
                    "termEndDate": "2027-01-01-05:00",
                    "status": "SUCCEEDED",
                }
            },
        }

    @patch.object(
        MembershipWebhookViewSet,
        "_store_webhook_payload",
        return_value=None,
    )
    async def test_create_membership_webhook_assigns_throttles(
        self, mock_store_webhook
    ) -> None:
        """createMembership writes Tier 1 MEMBERSHIP rates for the user."""
        self.data["eventTrigger"] = "createMembership"

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        rates = sorted(
            [
                rate
                async for rate in APIThrottle.objects.filter(
                    user=self.user_profile.user,
                    throttle_type=ThrottleType.API,
                    source=APIThrottle.Source.MEMBERSHIP,
                ).values_list("rate", flat=True)
            ]
        )
        self.assertEqual(rates, sorted(["10/min", "75/hour", "300/day"]))

    @patch.object(
        MembershipWebhookViewSet,
        "_store_webhook_payload",
        return_value=None,
    )
    async def test_create_lso_1_membership_assigns_tier_1_throttles(
        self, mock_store_webhook
    ) -> None:
        """LSO 1 webhooks provision the Tier 1 MEMBERSHIP rates."""
        self.data["eventTrigger"] = "createMembership"
        self.data["data"]["membership"]["membershipName"] = "LSO 1"

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        rates = sorted(
            [
                rate
                async for rate in APIThrottle.objects.filter(
                    user=self.user_profile.user,
                    throttle_type=ThrottleType.API,
                    source=APIThrottle.Source.MEMBERSHIP,
                ).values_list("rate", flat=True)
            ]
        )
        self.assertEqual(rates, sorted(["10/min", "75/hour", "300/day"]))

    @patch.object(
        MembershipWebhookViewSet,
        "_store_webhook_payload",
        return_value=None,
    )
    async def test_update_membership_webhook_replaces_throttles(
        self, mock_store_webhook
    ) -> None:
        """updateMembership replaces the previous tier's MEMBERSHIP rates."""
        await NeonMembership.objects.acreate(
            user=self.user_profile.user,
            neon_id="12345",
            level=NeonMembershipLevel.TIER_1,
        )
        # Pre-seed MEMBERSHIP rows that match Tier 1 (as if a prior
        # webhook had run).
        for rate in ("10/min", "75/hour", "300/day"):
            await APIThrottle.objects.acreate(
                user=self.user_profile.user,
                throttle_type=ThrottleType.API,
                rate=rate,
                source=APIThrottle.Source.MEMBERSHIP,
            )

        self.data["eventTrigger"] = "editMembership"
        self.data["data"]["membership"]["membershipName"] = (
            "CL Membership - Tier 4"
        )

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        rates = sorted(
            [
                rate
                async for rate in APIThrottle.objects.filter(
                    user=self.user_profile.user,
                    throttle_type=ThrottleType.API,
                    source=APIThrottle.Source.MEMBERSHIP,
                ).values_list("rate", flat=True)
            ]
        )
        self.assertEqual(rates, sorted(["25/min", "300/hour", "1400/day"]))

    @patch.object(
        MembershipWebhookViewSet,
        "_store_webhook_payload",
        return_value=None,
    )
    async def test_delete_membership_webhook_clears_throttles(
        self, mock_store_webhook
    ) -> None:
        """deleteMembership clears MEMBERSHIP rows; MANUAL rows survive."""
        await NeonMembership.objects.acreate(
            user=self.user_profile.user,
            neon_id="12345",
            level=NeonMembershipLevel.TIER_1,
        )
        await APIThrottle.objects.acreate(
            user=self.user_profile.user,
            throttle_type=ThrottleType.API,
            rate="0/min",
            source=APIThrottle.Source.MANUAL,
        )
        await APIThrottle.objects.acreate(
            user=self.user_profile.user,
            throttle_type=ThrottleType.API,
            rate="10/min",
            source=APIThrottle.Source.MEMBERSHIP,
        )

        self.data["eventTrigger"] = "deleteMembership"

        r = await self.async_client.post(
            reverse("membership-webhooks-list", kwargs={"version": "v3"}),
            data=self.data,
            content_type="application/json",
        )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        remaining = [
            (rate, source)
            async for rate, source in APIThrottle.objects.filter(
                user=self.user_profile.user
            ).values_list("rate", "source")
        ]
        self.assertEqual(remaining, [("0/min", APIThrottle.Source.MANUAL)])


def make_neon_membership(
    membership_id: str = "200",
    level_name: str = "CL Membership - Tier 2",
    term_end_date: str = "2027-10-04-05:00",
    payment_status: str = "Succeeded",
) -> dict:
    """Build a membership record shaped like the Neon API returns it."""
    return {
        "id": membership_id,
        "accountId": "1234",
        "membershipLevel": {"id": "2", "name": level_name},
        "termEndDate": term_end_date,
        "status": "SUCCEEDED",
        "payments": [{"paymentStatus": payment_status}],
    }


class NeonClientMembershipTest(SimpleTestCase):
    """Tests for NeonClient.get_primary_active_membership."""

    @patch("cl.lib.neon_utils.requests.get")
    def test_returns_first_membership_or_none(self, mock_get) -> None:
        """Returns Neon's first membership, or None when the list is empty."""
        neon_membership = make_neon_membership()
        for memberships, expected in (
            ([neon_membership], neon_membership),
            ([], None),
        ):
            with self.subTest(memberships=memberships):
                mock_get.return_value = MagicMock(
                    status_code=200,
                    **{"json.return_value": {"memberships": memberships}},
                )
                result = NeonClient().get_primary_active_membership("1234")
                self.assertEqual(result, expected)
                self.assertTrue(
                    mock_get.call_args.args[0].endswith(
                        "/accounts/1234/memberships"
                    )
                )
                params = mock_get.call_args.kwargs["params"]
                self.assertEqual(params["primaryActiveMembership"], "true")
                self.assertEqual(params["sortDirection"], "DESC")


@time_machine.travel(datetime(2026, 10, 9, 12, 0, tzinfo=UTC), tick=False)
class SyncNeonMembershipsCommandTest(TestCase):
    """Tests for the sync_neon_memberships command."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_profile = UserProfileWithParentsFactory(
            user__email="member@example.com", neon_account_id="1234"
        )
        cls.user = cls.user_profile.user

    def setUp(self) -> None:
        # A Tier 1 membership that lapsed five days ago, i.e. inside the
        # default 24-hour-to-90-day sync window.
        self.membership = NeonMembershipFactory(
            user=self.user,
            neon_id="100",
            level=NeonMembershipLevel.TIER_1,
            termination_date=now() - timedelta(days=5),
        )
        patcher = patch.object(NeonClient, "get_primary_active_membership")
        self.mock_get_membership = patcher.start()
        self.addCleanup(patcher.stop)
        zoho_patcher = patch(
            "cl.donate.management.commands.sync_neon_memberships"
            ".tag_zoho_record_for_membership"
        )
        self.mock_tag_zoho = zoho_patcher.start()
        self.addCleanup(zoho_patcher.stop)

    def get_membership_rates(self) -> list[str]:
        """Return the user's MEMBERSHIP-source API throttle rates, sorted."""
        return sorted(
            APIThrottle.objects.filter(
                user=self.user,
                throttle_type=ThrottleType.API,
                source=APIThrottle.Source.MEMBERSHIP,
            ).values_list("rate", flat=True)
        )

    def called_account_ids(self) -> set[str]:
        """Return the Neon account ids the mocked client was asked about."""
        return {
            call.args[0] for call in self.mock_get_membership.call_args_list
        }

    def assert_membership_untouched(self) -> None:
        """Assert the lapsed membership, throttles and Zoho were left alone."""
        self.assertTrue(
            NeonMembership.objects.filter(pk=self.membership.pk).exists()
        )
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.neon_id, "100")
        self.assertEqual(self.membership.level, NeonMembershipLevel.TIER_1)
        self.assertFalse(self.membership.is_active)
        self.assertEqual(self.get_membership_rates(), [])
        self.mock_tag_zoho.delay.assert_not_called()

    def test_updates_lapsed_membership_from_neon(self) -> None:
        """Syncs id, level, term end and payment, then rebuilds throttles."""
        self.mock_get_membership.return_value = make_neon_membership()

        call_command("sync_neon_memberships")

        self.mock_get_membership.assert_called_once_with("1234")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.neon_id, "200")
        self.assertEqual(self.membership.level, NeonMembershipLevel.TIER_2)
        self.assertEqual(
            self.membership.termination_date.date(), date(2027, 10, 4)
        )
        self.assertEqual(
            self.membership.payment_status, MembershipPaymentStatus.SUCCEEDED
        )
        self.assertTrue(self.membership.is_active)
        self.assertEqual(self.get_membership_rates(), sorted(TIER_2_RATES))
        self.mock_tag_zoho.delay.assert_called_once_with(
            self.user.pk, NeonMembershipLevel.TIER_2
        )

    def test_updates_extended_term_on_same_membership(self) -> None:
        """Picks up a new term end date even when the membership id matches."""
        self.mock_get_membership.return_value = make_neon_membership(
            membership_id="100",
            level_name="CL Membership - Tier 1",
            term_end_date="2027-01-01",
        )

        call_command("sync_neon_memberships")

        self.membership.refresh_from_db()
        self.assertEqual(self.membership.neon_id, "100")
        self.assertEqual(
            self.membership.termination_date.date(), date(2027, 1, 1)
        )
        self.assertTrue(self.membership.is_active)
        self.assertEqual(self.get_membership_rates(), sorted(TIER_1_RATES))

    def test_leaves_matching_membership_alone(self) -> None:
        """Keeps a lapse younger than a week when Neon's record matches ours."""
        self.mock_get_membership.return_value = make_neon_membership(
            membership_id="100",
            level_name="CL Membership - Tier 1",
            term_end_date=self.membership.termination_date.date().isoformat(),
        )

        call_command("sync_neon_memberships")

        self.assert_membership_untouched()

    def test_skips_when_neon_has_no_active_membership(self) -> None:
        """Keeps a lapse younger than a week when Neon has nothing newer."""
        self.mock_get_membership.return_value = None

        call_command("sync_neon_memberships")

        self.mock_get_membership.assert_called_once_with("1234")
        self.assert_membership_untouched()

    def test_only_checks_memberships_inside_window(self) -> None:
        """Checks lapses between 24 hours and 90 days old unless told otherwise."""
        for account_id, expired_for in (
            ("too-recent", timedelta(hours=1)),
            ("too-old", timedelta(days=91)),
        ):
            profile = UserProfileWithParentsFactory(neon_account_id=account_id)
            NeonMembershipFactory(
                user=profile.user, termination_date=now() - expired_for
            )
        self.mock_get_membership.return_value = None

        # Deletion is off so every run sees the same records.
        for options, expected_account_ids in (
            ({}, {"1234"}),
            ({"max_days_expired": 0}, {"1234", "too-old"}),
            (
                {"min_hours_expired": 0, "max_days_expired": 30},
                {"1234", "too-recent"},
            ),
        ):
            with self.subTest(options=options):
                self.mock_get_membership.reset_mock()
                call_command(
                    "sync_neon_memberships", delete_after_days=0, **options
                )
                self.assertEqual(
                    self.called_account_ids(), expected_account_ids
                )

    def test_skips_user_without_neon_account_id(self) -> None:
        """Never calls Neon for a member whose profile has no account id."""
        self.user_profile.neon_account_id = ""
        self.user_profile.save()

        call_command("sync_neon_memberships")

        self.mock_get_membership.assert_not_called()
        self.assert_membership_untouched()

    def test_continues_after_neon_api_error(self) -> None:
        """A failed Neon request skips that member and processes the rest."""
        other_profile = UserProfileWithParentsFactory(neon_account_id="5678")
        other_membership = NeonMembershipFactory(
            user=other_profile.user,
            neon_id="300",
            termination_date=now() - timedelta(days=10),
        )
        # Memberships are processed oldest expiration first, so the failure
        # hits the other member and ours is still synced afterwards. The
        # failed one is over a week old but must not be deleted unchecked.
        self.mock_get_membership.side_effect = [
            requests.HTTPError("500 Server Error"),
            make_neon_membership(),
        ]

        call_command("sync_neon_memberships")

        self.assertEqual(self.mock_get_membership.call_count, 2)
        other_membership.refresh_from_db()
        self.assertEqual(other_membership.neon_id, "300")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.neon_id, "200")
        self.assertEqual(self.get_membership_rates(), sorted(TIER_2_RATES))

    def test_skips_unknown_level_and_edu_without_edu_email(self) -> None:
        """Keeps records with levels we don't map or EDU for non-.edu users."""
        # Old enough to delete, but skipped records are left for a human.
        self.membership.termination_date = now() - timedelta(days=10)
        self.membership.save()
        for level_name in ("Not a real level", "EDU Membership"):
            with self.subTest(level_name=level_name):
                self.mock_get_membership.return_value = make_neon_membership(
                    level_name=level_name
                )

                call_command("sync_neon_memberships")

                self.assert_membership_untouched()

    def test_deletes_stale_membership_neon_confirms_unchanged(self) -> None:
        """Deletes a week-old lapse Neon matches, and only its MEMBERSHIP throttles."""
        self.membership.termination_date = now() - timedelta(days=10)
        self.membership.save()
        for rate, source in (
            ("10/min", APIThrottle.Source.MEMBERSHIP),
            ("500/day", APIThrottle.Source.MANUAL),
        ):
            APIThrottle.objects.create(
                user=self.user,
                throttle_type=ThrottleType.API,
                rate=rate,
                source=source,
            )
        self.mock_get_membership.return_value = make_neon_membership(
            membership_id="100",
            level_name="CL Membership - Tier 1",
            term_end_date=self.membership.termination_date.date().isoformat(),
        )

        call_command("sync_neon_memberships")

        self.assertFalse(
            NeonMembership.objects.filter(pk=self.membership.pk).exists()
        )
        remaining = list(
            APIThrottle.objects.filter(user=self.user).values_list(
                "rate", "source"
            )
        )
        self.assertEqual(remaining, [("500/day", APIThrottle.Source.MANUAL)])
        self.mock_tag_zoho.delay.assert_not_called()

    def test_deletes_stale_membership_when_neon_has_none(self) -> None:
        """Deletes a week-old lapse when Neon has no active membership."""
        self.membership.termination_date = now() - timedelta(days=8)
        self.membership.save()
        self.mock_get_membership.return_value = None

        call_command("sync_neon_memberships")

        self.assertFalse(
            NeonMembership.objects.filter(pk=self.membership.pk).exists()
        )

    def test_delete_threshold_is_configurable(self) -> None:
        """Honors --delete-after-days, and 0 turns deletion off."""
        self.membership.termination_date = now() - timedelta(days=10)
        self.membership.save()
        self.mock_get_membership.return_value = None

        call_command("sync_neon_memberships", delete_after_days=0)
        self.assert_membership_untouched()

        call_command("sync_neon_memberships", delete_after_days=30)
        self.assert_membership_untouched()

        call_command("sync_neon_memberships", delete_after_days=9)
        self.assertFalse(
            NeonMembership.objects.filter(pk=self.membership.pk).exists()
        )
