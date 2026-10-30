import threading
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from io import StringIO
from unittest.mock import MagicMock, patch

import requests
import time_machine
from asgiref.sync import sync_to_async
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings
from django.test.client import AsyncClient, Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.timezone import make_aware, now

from cl.api.constants import TIER_1_RATES, TIER_2_RATES
from cl.api.models import APIThrottle, ThrottleType
from cl.api.utils import (
    CloudFrontAnonRateThrottle,
    ExceptionalUserRateThrottle,
    apply_membership_throttles,
)
from cl.donate import api_views
from cl.donate.api_views import MembershipWebhookViewSet
from cl.donate.factories import (
    NeonMembershipFactory,
    NeonWebhookEventFactory,
)
from cl.donate.management.commands.sync_neon_memberships import (
    SyncResult,
    sync_membership_from_neon,
)
from cl.donate.models import (
    MembershipPaymentStatus,
    NeonMembership,
    NeonMembershipLevel,
    NeonWebhookEvent,
)
from cl.lib.neon_utils import NeonClient
from cl.lib.test_helpers import UserProfileWithParentsFactory
from cl.tests.cases import SimpleTestCase, TestCase, TransactionTestCase
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
    def test_update_membership_locks_row(self, mock_store_webhook) -> None:
        """updateMembership must lock the row it reads before saving it, and
        lock the User first, both with FOR NO KEY UPDATE.

        During an upgrade Neon sends createMembership and updateMembership
        at nearly the same time. Without a row lock the update handler can
        save stale data over the upgrade or crash if the row changes between
        its reads. createMembership locks the User first, so this handler
        must too, or the two can deadlock. FOR UPDATE on the User would
        instead deadlock with sync_neon_memberships, whose APIThrottle
        foreign key check takes FOR KEY SHARE on the User.
        """
        NeonMembership.objects.create(
            user=self.user_profile.user,
            neon_id="12345",
            level=NeonMembershipLevel.TIER_1,
        )
        self.data["eventTrigger"] = "updateMembership"
        self.data["data"]["membership"]["membershipName"] = (
            "CL Membership - Tier 4"
        )

        with CaptureQueriesContext(connection) as ctx:
            r = Client().post(
                reverse("membership-webhooks-list", kwargs={"version": "v4"}),
                data=self.data,
                content_type="application/json",
            )

        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        locked_tables = [
            table
            for q in ctx.captured_queries
            if "FOR NO KEY UPDATE" in q["sql"]
            for table in ("auth_user", "donate_neonmembership")
            if f'FROM "{table}"' in q["sql"]
        ]
        self.assertEqual(
            locked_tables,
            ["auth_user", "donate_neonmembership"],
            msg=ctx.captured_queries,
        )
        membership = NeonMembership.objects.get(neon_id="12345")
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

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "membership-webhook-throttle-test",
            }
        }
    )
    @patch(
        "cl.donate.api_views.MembershipWebhookViewSet._handle_membership_creation",
    )
    def test_webhook_is_never_rate_limited(self, mock_creation) -> None:
        """Neon's webhook bursts must get 201s, whatever the API throttles say."""
        # Neon posts from a few fixed addresses with no API user, so in
        # production every webhook counts against one ident's "anon" and
        # "user" buckets. Tighten both to a single request: if the viewset
        # consulted either throttle, every call after the first would be 429.
        self.data["eventTrigger"] = "createMembership"
        rates = {"anon": "1/day", "user": "1/day"}
        client = Client()
        with (
            patch.object(CloudFrontAnonRateThrottle, "THROTTLE_RATES", rates),
            patch.object(ExceptionalUserRateThrottle, "THROTTLE_RATES", rates),
        ):
            for version in ("v3", "v4"):
                url = reverse(
                    "membership-webhooks-list", kwargs={"version": version}
                )
                for attempt in (1, 2):
                    with self.subTest(version=version, attempt=attempt):
                        r = client.post(
                            url,
                            data=self.data,
                            content_type="application/json",
                        )
                        self.assertEqual(r.status_code, HTTPStatus.CREATED)


class MembershipWebhookConcurrencyTest(TransactionTestCase):
    """Overlapping writers to one user's membership must not deadlock.

    Each test runs two writers (Neon webhooks or the sync_neon_memberships
    command) from separate threads, so they run in separate database
    transactions. The first one pauses partway through, holding its row
    locks, while the second one starts.
    """

    def setUp(self) -> None:
        self.user_profile = UserProfileWithParentsFactory(
            user__email="test_concurrency@email.com"
        )
        self.user_profile.neon_account_id = "1234"
        self.user_profile.save()
        self.user = self.user_profile.user
        NeonMembership.objects.create(
            user=self.user,
            neon_id="12345",
            level=NeonMembershipLevel.TIER_1,
        )
        apply_membership_throttles(self.user, NeonMembershipLevel.TIER_1)

    @staticmethod
    def _payload(trigger: str, membership_id: str, name: str) -> dict:
        """Build a Neon membership webhook payload for this user."""
        return {
            "eventTrigger": trigger,
            "eventTimestamp": "2026-10-23T03:42:59.000-06:00",
            "data": {
                "membership": {
                    "membershipId": membership_id,
                    "accountId": "1234",
                    "membershipName": name,
                    "termEndDate": "2027-10-23-05:00",
                    "status": "SUCCEEDED",
                }
            },
        }

    @staticmethod
    def _webhook(payload: dict) -> Callable[[], int]:
        """Return a callable that posts a webhook and returns its status."""

        def post() -> int:
            return (
                Client()
                .post(
                    reverse(
                        "membership-webhooks-list", kwargs={"version": "v4"}
                    ),
                    data=payload,
                    content_type="application/json",
                )
                .status_code
            )

        return post

    def _race(
        self,
        first: Callable[[], object],
        second: Callable[[], object],
        pause_target: tuple[object, str],
        pause_after: bool,
    ) -> dict[str, object]:
        """Run two writers concurrently and return their outcomes.

        The first writer pauses at pause_target, an (object, attribute)
        pair to patch, while holding its locks. The second writer starts
        once the first has paused.

        :param first: The writer that runs first.
        :param second: The writer that runs once the first has paused.
        :param pause_target: The patch() target to pause at.
        :param pause_after: Pause after the target returns if True, else
        before calling it.
        :return: Each writer's return value, or the exception it raised.
        """
        first_paused = threading.Event()
        outcomes: dict[str, object] = {}

        def pause() -> None:
            # Only pause the first writer, which runs before the second one
            # starts.
            if not first_paused.is_set():
                first_paused.set()
                # Give the second writer time to take any locks it can.
                time.sleep(1)

        def run(name: str, writer: Callable[[], object]) -> None:
            try:
                if name == "second":
                    first_paused.wait(timeout=10)
                outcomes[name] = writer()
            except Exception as e:
                outcomes[name] = e
            finally:
                connection.close()

        target, attr = pause_target
        wrapped = getattr(target, attr)

        def paused(*args, **kwargs):
            if not pause_after:
                pause()
            result = wrapped(*args, **kwargs)
            if pause_after:
                pause()
            return result

        with patch.object(target, attr, paused):
            threads = [
                threading.Thread(target=run, args=("first", first)),
                threading.Thread(target=run, args=("second", second)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
        return outcomes

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    @patch("cl.donate.api_views.tag_zoho_record_for_membership")
    def test_create_and_update_do_not_deadlock(
        self, mock_zoho, mock_store_webhook
    ) -> None:
        """An upgrade's createMembership and updateMembership can overlap.

        createMembership pauses after locking the User. updateMembership
        must wait for that lock instead of locking the membership first.
        """
        outcomes = self._race(
            self._webhook(
                self._payload(
                    "createMembership", "12346", "CL Membership - Tier 4"
                )
            ),
            self._webhook(
                self._payload(
                    "updateMembership", "12345", "CL Membership - Tier 1"
                )
            ),
            (MembershipWebhookViewSet, "_get_member_record"),
            pause_after=True,
        )

        self.assertEqual(
            outcomes,
            {"first": HTTPStatus.CREATED, "second": HTTPStatus.CREATED},
        )
        membership = NeonMembership.objects.get(user=self.user)
        self.assertEqual(membership.neon_id, "12346")
        self.assertEqual(membership.level, NeonMembershipLevel.TIER_4)

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    @patch("cl.donate.api_views.tag_zoho_record_for_membership")
    def test_create_and_delete_do_not_deadlock(
        self, mock_zoho, mock_store_webhook
    ) -> None:
        """deleteMembership must also lock the User before the membership.

        createMembership pauses after saving the membership and before
        rewriting the throttle rows. A deleteMembership that cleared the
        throttle rows before locking the membership would deadlock with it.
        """
        outcomes = self._race(
            self._webhook(
                self._payload(
                    "createMembership", "12346", "CL Membership - Tier 4"
                )
            ),
            self._webhook(
                self._payload(
                    "deleteMembership", "12345", "CL Membership - Tier 1"
                )
            ),
            (api_views, "apply_membership_throttles"),
            pause_after=False,
        )

        self.assertEqual(
            outcomes,
            {"first": HTTPStatus.CREATED, "second": HTTPStatus.CREATED},
        )
        membership = NeonMembership.objects.get(user=self.user)
        self.assertEqual(membership.neon_id, "12346")

    @patch.object(
        MembershipWebhookViewSet, "_store_webhook_payload", return_value=None
    )
    @patch("cl.donate.api_views.tag_zoho_record_for_membership")
    @patch(
        "cl.donate.management.commands.sync_neon_memberships"
        ".tag_zoho_record_for_membership"
    )
    def test_create_and_sync_do_not_deadlock(
        self, mock_sync_zoho, mock_zoho, mock_store_webhook
    ) -> None:
        """createMembership and sync_neon_memberships can overlap.

        createMembership pauses after locking the User. The sync then
        updates the membership and rebuilds its throttles, whose foreign
        key check locks the User at commit. createMembership's User lock
        must not block that check.
        """
        membership = NeonMembership.objects.get(user=self.user)
        outcomes = self._race(
            self._webhook(
                self._payload(
                    "createMembership", "12346", "CL Membership - Tier 4"
                )
            ),
            lambda: sync_membership_from_neon(
                membership, make_neon_membership()
            ),
            (MembershipWebhookViewSet, "_get_member_record"),
            pause_after=True,
        )

        self.assertEqual(
            outcomes,
            {"first": HTTPStatus.CREATED, "second": SyncResult.UPDATED},
        )
        # The webhook ran last, so its data wins.
        membership.refresh_from_db()
        self.assertEqual(membership.neon_id, "12346")
        self.assertEqual(membership.level, NeonMembershipLevel.TIER_4)


class ProfileMembershipTest(TestCase):
    def setUp(self) -> None:
        self.user_profile = UserProfileWithParentsFactory()

    @override_settings(NEON_MEMBERSHIP_GRACE_PERIOD_DAYS=3)
    def test_is_member_returns_true_until_grace_period_passes(self):
        """is_member stays True through the grace period after termination."""
        term_day = now().date() + timedelta(weeks=4)
        NeonMembership.objects.create(
            level=NeonMembershipLevel.LEGACY,
            user=self.user_profile.user,
            # Local midnight, which is how the Neon webhooks store it.
            termination_date=make_aware(
                datetime(term_day.year, term_day.month, term_day.day)
            ),
            payment_status=MembershipPaymentStatus.SUCCEEDED,
        )
        self.user_profile.refresh_from_db()

        def noon_utc(days_after_term: int) -> datetime:
            """Noon UTC on that day, which is the same date in TIME_ZONE."""
            day = term_day + timedelta(days=days_after_term)
            return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)

        # Still a member the day before, on the day, and through the grace
        # period, including its last day.
        for days in (-1, 0, 1, 3):
            with (
                self.subTest(days_after_term=days),
                time_machine.travel(noon_utc(days), tick=False),
            ):
                self.assertTrue(self.user_profile.is_member)

        # Benefits end the day after the grace period.
        with time_machine.travel(noon_utc(4), tick=False):
            self.assertFalse(
                self.user_profile.is_member,
                "Should not be a member once the grace period has passed.",
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


@override_settings(NEON_MEMBERSHIP_GRACE_PERIOD_DAYS=3)
@time_machine.travel(datetime(2026, 10, 9, 12, 0, tzinfo=UTC), tick=False)
class NeonMembershipActiveTest(TestCase):
    """Tests for is_active, benefits_cutoff_date and objects.active()."""

    # "Today" is frozen at 2026-10-09, 05:00 in America/Los_Angeles. With a
    # 3-day grace period the cutoff is 2026-10-06: a term that ended on or
    # after that local date still grants benefits. Terms end at local
    # midnight, which is how the Neon webhooks store them.
    CASES = (
        # label, term end (local date), payment status, active
        (
            "ends in a month",
            date(2026, 11, 9),
            MembershipPaymentStatus.SUCCEEDED,
            True,
        ),
        (
            "ends today",
            date(2026, 10, 9),
            MembershipPaymentStatus.SUCCEEDED,
            True,
        ),
        (
            "ended yesterday",
            date(2026, 10, 8),
            MembershipPaymentStatus.SUCCEEDED,
            True,
        ),
        (
            "ended on the cutoff",
            date(2026, 10, 6),
            MembershipPaymentStatus.SUCCEEDED,
            True,
        ),
        (
            "ended before the cutoff",
            date(2026, 10, 5),
            MembershipPaymentStatus.SUCCEEDED,
            False,
        ),
        (
            "pending payment, ends today",
            date(2026, 10, 9),
            MembershipPaymentStatus.PENDING,
            True,
        ),
        (
            "failed payment, ends today",
            date(2026, 10, 9),
            MembershipPaymentStatus.FAILED,
            False,
        ),
        ("never ends", None, MembershipPaymentStatus.SUCCEEDED, True),
    )

    @staticmethod
    def local_datetime(day: date, hour: int = 0) -> datetime:
        """Return an aware datetime at the given hour of that day in TIME_ZONE."""
        return make_aware(datetime(day.year, day.month, day.day, hour))

    @classmethod
    def setUpTestData(cls) -> None:
        cls.memberships = {
            label: NeonMembershipFactory(
                termination_date=cls.local_datetime(day) if day else None,
                payment_status=payment_status,
            )
            for label, day, payment_status, _ in cls.CASES
        }

    def active_pks(self) -> set[int]:
        """Return the primary keys objects.active() currently selects."""
        return set(
            NeonMembership.objects.active().values_list("pk", flat=True)
        )

    def test_benefits_cutoff_date_is_today_minus_grace_period(self) -> None:
        """The cutoff is today's local date minus the grace period."""
        self.assertEqual(
            NeonMembership.benefits_cutoff_date(), date(2026, 10, 6)
        )

    def test_is_active_honors_grace_period(self) -> None:
        """is_active keeps benefits through the grace period after the term."""
        for label, _, _, active in self.CASES:
            with self.subTest(label):
                self.assertEqual(self.memberships[label].is_active, active)

    def test_active_queryset_applies_the_same_rule(self) -> None:
        """objects.active() selects exactly the memberships is_active accepts."""
        expected = {
            self.memberships[label].pk
            for label, _, _, active in self.CASES
            if active
        }

        self.assertEqual(self.active_pks(), expected)

    def test_zero_grace_period_ends_benefits_on_termination_date(self) -> None:
        """With no grace period, benefits end on the termination date itself."""
        ends_today = self.memberships["ends today"]
        ended_yesterday = self.memberships["ended yesterday"]

        with override_settings(NEON_MEMBERSHIP_GRACE_PERIOD_DAYS=0):
            self.assertEqual(
                NeonMembership.benefits_cutoff_date(), date(2026, 10, 9)
            )
            self.assertTrue(ends_today.is_active)
            self.assertFalse(ended_yesterday.is_active)
            active_pks = self.active_pks()

        self.assertIn(ends_today.pk, active_pks)
        self.assertNotIn(ended_yesterday.pk, active_pks)

    def test_python_and_sql_checks_agree_at_any_hour(self) -> None:
        """is_active and objects.active() never disagree, whatever the hour."""
        # Instants on both sides of the Pacific/UTC date boundary (the UTC
        # date runs a day ahead from 16:00 or 17:00 Pacific until midnight),
        # on an ordinary day and on the day after the 2026-11-01 fall-back.
        instants = [
            datetime(2026, 10, 9, hour, 30, tzinfo=UTC)
            for hour in (0, 6, 7, 8, 12, 23)
        ] + [
            datetime(2026, 11, 2, hour, 30, tzinfo=UTC)
            for hour in (0, 7, 8, 12, 23)
        ]
        # Terms ending at local midnight (webhooks) and at 22:00 local
        # (manual admin entries) on the days around each cutoff.
        memberships = [
            NeonMembershipFactory(
                termination_date=self.local_datetime(
                    start + timedelta(days=offset), hour
                )
            )
            for start in (date(2026, 10, 3), date(2026, 10, 27))
            for offset in range(8)
            for hour in (0, 22)
        ]

        for instant in instants:
            with (
                self.subTest(instant=instant.isoformat()),
                time_machine.travel(instant, tick=False),
            ):
                active_pks = self.active_pks()
                for membership in memberships:
                    self.assertEqual(
                        membership.is_active,
                        membership.pk in active_pks,
                        f"{membership.termination_date.isoformat()} at "
                        f"{instant.isoformat()}",
                    )

    def test_grace_period_counts_calendar_days_across_dst_change(
        self,
    ) -> None:
        """A term ending before the fall-back still gets its full grace days."""
        # 2026-10-30 plus three calendar days is 2026-11-02, even though the
        # clocks went back an hour on 2026-11-01. Adding 72 hours instead
        # would have ended benefits a day early.
        membership = NeonMembershipFactory(
            termination_date=self.local_datetime(date(2026, 10, 30))
        )

        with time_machine.travel(
            datetime(2026, 11, 2, 12, 30, tzinfo=UTC), tick=False
        ):
            self.assertTrue(membership.is_active)
            self.assertIn(membership.pk, self.active_pks())

        with time_machine.travel(
            datetime(2026, 11, 3, 12, 30, tzinfo=UTC), tick=False
        ):
            self.assertFalse(membership.is_active)
            self.assertNotIn(membership.pk, self.active_pks())


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
    term_end_date: str | None = "2027-10-04-05:00",
    payment_status: str = "Succeeded",
    status: str | None = "SUCCEEDED",
) -> dict:
    """Build a membership record shaped like the Neon API returns it."""
    return {
        "id": membership_id,
        "accountId": "1234",
        "membershipLevel": {"id": "2", "name": level_name},
        "termEndDate": term_end_date,
        "status": status,
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


@override_settings(NEON_MEMBERSHIP_GRACE_PERIOD_DAYS=2)
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
        logger_patcher = patch(
            "cl.donate.management.commands.sync_neon_memberships.logger"
        )
        self.mock_logger = logger_patcher.start()
        self.addCleanup(logger_patcher.stop)

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

    def test_payment_status_follows_neon_membership_status(self) -> None:
        """A SUCCEEDED membership is stored as paid whatever its payments say."""
        for label, payments in (
            (
                "failed attempt listed first",
                [
                    {"paymentStatus": "Failed"},
                    {"paymentStatus": "Succeeded"},
                ],
            ),
            ("null payment status", [{"paymentStatus": None}]),
            ("no payments", []),
            ("payments missing", None),
        ):
            with self.subTest(label):
                neon_membership = make_neon_membership()
                if payments is None:
                    del neon_membership["payments"]
                else:
                    neon_membership["payments"] = payments
                self.mock_get_membership.return_value = neon_membership

                call_command("sync_neon_memberships")

                self.membership.refresh_from_db()
                self.assertEqual(self.membership.neon_id, "200")
                self.assertEqual(
                    self.membership.payment_status,
                    MembershipPaymentStatus.SUCCEEDED,
                )
                self.assertTrue(self.membership.is_active)
                # Reset for the next case, as the command would otherwise
                # see nothing newer.
                self.membership.neon_id = "100"
                self.membership.termination_date = now() - timedelta(days=5)
                self.membership.save()

    def test_checks_membership_still_inside_grace_period(self) -> None:
        """Fixes a lapsed membership while the grace period keeps it active."""
        self.membership.termination_date = now() - timedelta(hours=30)
        self.membership.save()
        self.assertTrue(self.membership.is_active)
        self.mock_get_membership.return_value = make_neon_membership()

        call_command("sync_neon_memberships")

        self.mock_get_membership.assert_called_once_with("1234")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.neon_id, "200")
        self.assertTrue(self.membership.is_active)

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
        out = StringIO()

        call_command("sync_neon_memberships", stdout=out)

        self.assertEqual(self.mock_get_membership.call_count, 2)
        other_membership.refresh_from_db()
        self.assertEqual(other_membership.neon_id, "300")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.neon_id, "200")
        self.assertEqual(self.get_membership_rates(), sorted(TIER_2_RATES))
        self.assertIn(
            "1 updated, 0 deleted, 0 skipped, 1 failed", out.getvalue()
        )

    def test_continues_after_unexpected_error(self) -> None:
        """A malformed Neon record is logged with its traceback and skipped."""
        other_profile = UserProfileWithParentsFactory(neon_account_id="5678")
        other_membership = NeonMembershipFactory(
            user=other_profile.user,
            neon_id="300",
            termination_date=now() - timedelta(days=10),
        )
        malformed = make_neon_membership()
        del malformed["membershipLevel"]
        # Oldest expiration first, so the malformed record hits the other
        # member, who is old enough to delete but must be left alone.
        self.mock_get_membership.side_effect = [
            malformed,
            make_neon_membership(),
        ]
        out = StringIO()

        call_command("sync_neon_memberships", stdout=out)

        self.mock_logger.exception.assert_called_once()
        other_membership.refresh_from_db()
        self.assertEqual(other_membership.neon_id, "300")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.neon_id, "200")
        self.assertIn(
            "1 updated, 0 deleted, 0 skipped, 1 failed", out.getvalue()
        )

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

    def test_leaves_in_progress_membership_for_next_run(self) -> None:
        """Keeps a lapsed row untouched, and undeleted, while Neon retries."""
        # Older than the default 7-day delete threshold on purpose.
        self.membership.termination_date = now() - timedelta(days=10)
        self.membership.save()
        for status, payment_status in (
            ("PENDING", "Pending"),
            ("FAILED", "Failed"),
        ):
            with self.subTest(status=status):
                self.mock_get_membership.return_value = make_neon_membership(
                    status=status, payment_status=payment_status
                )

                call_command("sync_neon_memberships")

                self.assert_membership_untouched()

    def test_reports_unexpected_neon_status(self) -> None:
        """Skips and logs an error for statuses the command doesn't handle."""
        for status, payment_status in (
            ("CANCELED", "Canceled"),
            ("REFUNDED", "Refunded"),
            ("CANCEL_PENDING", "Succeeded"),
            ("DEFERRED", "Deferred"),
            ("WAITINGLIST", "Pending"),
            (None, "Succeeded"),
        ):
            with self.subTest(status=status):
                self.mock_get_membership.return_value = make_neon_membership(
                    status=status, payment_status=payment_status
                )

                # The mock accumulates calls across subTests.
                self.mock_logger.error.reset_mock()

                call_command("sync_neon_memberships")

                self.mock_logger.error.assert_called_once()
                self.assert_membership_untouched()

    def test_reports_missing_term_end_date(self) -> None:
        """Never stores a null termination date from Neon."""
        self.mock_get_membership.return_value = make_neon_membership(
            term_end_date=None
        )

        call_command("sync_neon_memberships")

        self.mock_logger.error.assert_called_once()
        self.assert_membership_untouched()

    def test_ignores_neon_record_no_newer_than_ours(self) -> None:
        """Treats a different but already expired Neon membership as unchanged."""
        self.mock_get_membership.return_value = make_neon_membership(
            term_end_date=(now() - timedelta(days=8)).date().isoformat(),
            status="CANCELED",
        )

        call_command("sync_neon_memberships")

        # The date check runs before the status check, so an expired
        # CANCELED record must not be reported as an error.
        self.mock_logger.error.assert_not_called()
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

    def test_rejects_delete_threshold_inside_grace_period(self) -> None:
        """--delete-after-days must exceed the grace period unless it is 0."""
        self.mock_get_membership.return_value = None
        # The class pins the grace period to 2 days.
        for days in (1, 2):
            with self.subTest(days=days), self.assertRaises(CommandError):
                call_command("sync_neon_memberships", delete_after_days=days)
        self.assert_membership_untouched()

        for days in (0, 3):
            with self.subTest(days=days):
                call_command("sync_neon_memberships", delete_after_days=days)
