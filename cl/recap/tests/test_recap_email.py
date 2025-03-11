import json
from http import HTTPStatus
from pathlib import Path
from unittest import mock

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from cl.alerts.models import DocketAlert
from cl.api.factories import WEBHOOK_EVENT_STATUS, WebhookFactory
from cl.api.models import Webhook, WebhookEvent, WebhookEventType
from cl.api.utils import get_webhook_deprecation_date
from cl.recap.factories import (
    AppellateAttachmentFactory,
    AppellateAttachmentPageFactory,
    RECAPEmailDocketDataFactory,
    RECAPEmailDocketEntryDataFactory,
    RECAPEmailNotificationDataFactory,
)
from cl.recap.models import (
    PROCESSING_STATUS,
    UPLOAD_TYPE,
    EmailProcessingQueue,
    PacerFetchQueue,
    ProcessingQueue,
)
from cl.recap.tasks import (
    get_and_copy_recap_attachment_docs,
    mark_pq_successful,
    set_rd_sealed_status,
)
from cl.recap.tests.tests import mock_bucket_open
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.models import Docket, DocketEntry, RECAPDocument
from cl.tests.cases import TestCase
from cl.tests.utils import AsyncAPIClient, MockResponse
from cl.users.factories import UserProfileWithParentsFactory


@override_settings(
    EGRESS_PROXY_HOSTS=["http://proxy_1:9090", "http://proxy_2:9090"]
)
class RecapEmailToEmailProcessingQueueTest(TestCase):
    """Test the rest endpoint, but exclude the processing tasks."""

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="txwd", jurisdiction="FB")
        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "recap" / "test_assets"
        with open(
            test_dir / "recap_mail_custom_receipt.json",
            encoding="utf-8",
        ) as file:
            recap_mail_receipt = json.load(file)
            cls.data = {
                "court": cls.court.id,
                "mail": recap_mail_receipt["mail"],
                "receipt": recap_mail_receipt["receipt"],
            }

    def setUp(self) -> None:
        self.async_client = AsyncAPIClient()
        self.user = User.objects.get(username="recap-email")
        token = f"Token {self.user.auth_token.key}"
        self.async_client.credentials(HTTP_AUTHORIZATION=token)
        self.path = "/api/rest/v3/recap-email/"

    async def test_non_pacer_court_fails(self):
        self.data["court"] = "scotus"
        r = await self.async_client.post(self.path, self.data, format="json")
        j = json.loads(r.content)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            j["non_field_errors"], ["scotus is not a PACER court ID."]
        )

    async def test_missing_mail_properties_fails(self):
        del self.data["mail"]["headers"]
        r = await self.async_client.post(self.path, self.data, format="json")
        j = json.loads(r.content)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            j["non_field_errors"],
            ["The JSON value at key 'mail' should include 'headers'."],
        )

    async def test_missing_receipt_properties_fails(self):
        del self.data["receipt"]["recipients"]
        r = await self.async_client.post(self.path, self.data, format="json")
        j = json.loads(r.content)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            j["non_field_errors"],
            ["The JSON value at key 'receipt' should include 'recipients'."],
        )

    @mock.patch(
        "cl.recap.tasks.RecapEmailSESStorage.open",
        side_effect=mock_bucket_open,
    )
    @mock.patch("cl.recap.tasks.get_or_cache_pacer_cookies")
    @mock.patch(
        "cl.recap.tasks.is_docket_entry_sealed",
        return_value=False,
    )
    async def test_email_processing_queue_create(
        self, mock_is_docket_entry_sealed, mock_bucket_open, mock_cookies
    ):
        self.assertEqual(await EmailProcessingQueue.objects.acount(), 0)
        await self.async_client.post(self.path, self.data, format="json")
        self.assertEqual(await EmailProcessingQueue.objects.acount(), 1)


@mock.patch("cl.recap.tasks.enqueue_docket_alert", return_value=True)
@mock.patch(
    "cl.recap.tasks.RecapEmailSESStorage.open",
    side_effect=mock_bucket_open,
)
@mock.patch(
    "cl.recap.tasks.get_or_cache_pacer_cookies",
    side_effect=lambda x, y, z: (None, None),
)
@mock.patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
@mock.patch(
    "cl.recap.tasks.is_docket_entry_sealed",
    return_value=False,
)
class RecapEmailDocketAlerts(TestCase):
    """Test recap email docket alerts"""

    @classmethod
    def setUpTestData(cls):
        cls.user_profile = UserProfileWithParentsFactory()
        cls.user_profile_2 = UserProfileWithParentsFactory()
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_nda = CourtFactory(id="ca9", jurisdiction="F")
        cls.court_nyed = CourtFactory(id="nyed", jurisdiction="FD")
        cls.court_jpml = CourtFactory(id="jpml", jurisdiction="FS")
        cls.webhook = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=True,
            version=1,
        )
        cls.webhook_2 = WebhookFactory(
            user=cls.user_profile_2.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=True,
            version=2,
        )
        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "recap" / "test_assets"
        with (
            open(
                test_dir / "recap_mail_custom_receipt.json",
                encoding="utf-8",
            ) as file,
            open(
                test_dir / "recap_mail_custom_receipt_2.json",
                encoding="utf-8",
            ) as file_2,
            open(
                test_dir / "recap_mail_custom_receipt_3.json",
                encoding="utf-8",
            ) as file_3,
            open(
                test_dir / "recap_mail_custom_receipt_4.json",
                encoding="utf-8",
            ) as file_4,
            open(
                test_dir / "recap_mail_custom_receipt_nda.json",
                encoding="utf-8",
            ) as file_5,
            open(
                test_dir / "recap_mail_custom_receipt_no_re_user.json",
                encoding="utf-8",
            ) as file_6,
            open(
                test_dir / "recap_mail_custom_receipt_multi_nef_jpml.json",
                encoding="utf-8",
            ) as file_jpml,
        ):
            recap_mail_receipt = json.load(file)
            recap_mail_receipt_2 = json.load(file_2)
            recap_mail_receipt_3 = json.load(file_3)
            recap_mail_receipt_4 = json.load(file_4)
            recap_mail_receipt_nda = json.load(file_5)
            recap_mail_receipt_no_re_user = json.load(file_6)
            recap_mail_receipt_multi_nef_jpml = json.load(file_jpml)

        cls.data = {
            "court": cls.court.id,
            "mail": recap_mail_receipt["mail"],
            "receipt": recap_mail_receipt["receipt"],
        }
        cls.data_2 = {
            "court": cls.court.id,
            "mail": recap_mail_receipt_2["mail"],
            "receipt": recap_mail_receipt_2["receipt"],
        }

        cls.data_3 = {
            "court": cls.court.id,
            "mail": recap_mail_receipt_3["mail"],
            "receipt": recap_mail_receipt_3["receipt"],
        }
        cls.data_4 = {
            "court": cls.court_nyed.id,
            "mail": recap_mail_receipt_4["mail"],
            "receipt": recap_mail_receipt_4["receipt"],
        }
        cls.data_5 = {
            "court": cls.court_nda.id,
            "mail": recap_mail_receipt_nda["mail"],
            "receipt": recap_mail_receipt_nda["receipt"],
        }
        cls.data_no_user = {
            "court": cls.court.id,
            "mail": recap_mail_receipt_no_re_user["mail"],
            "receipt": recap_mail_receipt_no_re_user["receipt"],
        }
        cls.data_multi_jpml = {
            "court": cls.court_jpml.id,
            "mail": recap_mail_receipt_multi_nef_jpml["mail"],
            "receipt": recap_mail_receipt_multi_nef_jpml["receipt"],
        }
        cls.no_magic_number_data = RECAPEmailNotificationDataFactory(
            contains_attachments=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(pacer_magic_num=None)
                    ],
                )
            ],
        )

        minute_entry_data = RECAPEmailDocketEntryDataFactory(
            pacer_magic_num=None,
            document_number=None,
            document_url=None,
            pacer_doc_id=None,
            pacer_seq_no=None,
            pacer_case_id="12345",
        )

        cls.minute_entry_data = RECAPEmailNotificationDataFactory(
            contains_attachments=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[minute_entry_data],
                )
            ],
        )

        minute_entry_data_2 = minute_entry_data.copy()
        minute_entry_data_2["pacer_case_id"] = "12346"
        cls.multi_nef_minute_entry_data = RECAPEmailNotificationDataFactory(
            contains_attachments=False,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[minute_entry_data],
                ),
                RECAPEmailDocketDataFactory(
                    docket_entries=[minute_entry_data_2],
                ),
            ],
        )

    def setUp(self) -> None:
        self.async_client = AsyncAPIClient()
        self.user = User.objects.get(username="recap-email")
        token = f"Token {self.user.auth_token.key}"
        self.async_client.credentials(HTTP_AUTHORIZATION=token)
        self.path = "/api/rest/v3/recap-email/"

        recipient_user = self.user_profile
        recipient_user.user.email = "testing_1@mail.com"
        recipient_user.user.password = make_password("password")
        recipient_user.user.save()
        recipient_user.recap_email = "testing_1@recap.email"
        recipient_user.auto_subscribe = True
        recipient_user.save()
        self.recipient_user = recipient_user

        recipient_user_2 = self.user_profile_2
        recipient_user_2.user.email = "testing_2@mail.com"
        recipient_user_2.user.password = make_password("password")
        recipient_user_2.user.save()
        recipient_user_2.recap_email = "testing_2@recap.email"
        recipient_user_2.auto_subscribe = True
        recipient_user_2.save()
        self.recipient_user_2 = recipient_user_2

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_recap_email_case_auto_subscription(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test verifies that if a new recap.email notification comes in
        (first time) and the user has the auto-subscribe option enabled, a new
        DocketAlert subscription is created for that user-case pair and then
        receives the docket alert email for this case.
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        # auto-subscription option enabled
        await self.async_client.post(self.path, self.data, format="json")

        # Can we get the recap.email recipient properly?
        email_processing = EmailProcessingQueue.objects.all()
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.destination_emails,
            ["testing_1@recap.email"],
        )

        # A DocketAlert should be created when receiving the first notification
        # for this case with Subscription type, since user has
        # auto-subscribe True.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(await docket_alert.acount(), 1)

        # A DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertEqual(message_sent.to, [self.recipient_user.user.email])

        # Webhook should be triggered
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 1)
        webhook_triggered_first = await webhook_triggered.afirst()
        self.assertEqual(
            webhook_triggered_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )
        content = webhook_triggered_first.content
        # Compare the content of the webhook to the recap document
        pacer_doc_id = content["payload"]["results"][0]["recap_documents"][0][
            "pacer_doc_id"
        ]
        docket_id = content["payload"]["results"][0]["docket"]
        self.assertEqual(docket.pk, docket_id)
        await recap_document_first.arefresh_from_db()
        self.assertEqual(recap_document_first.pacer_doc_id, pacer_doc_id)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_recap_email_case_auto_subscription_prev_user(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test verifies that if two users with the auto-subscribe option
        enabled are properly subscribed for a case when two recap.email
        notifications come in, the second notification should be also delivered
        for the previous user subscribed to the case.
        """

        # Trigger a new recap.email notification from testing_2@recap.email
        # auto-subscription option enabled
        await self.async_client.post(self.path, self.data_3, format="json")

        # Can we get the recap.email recipient properly?
        email_processing = EmailProcessingQueue.objects.all()
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.destination_emails,
            ["testing_2@recap.email"],
        )

        # A DocketAlert email for testing_2@recap.email should go out
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        self.assertEqual(await recap_document.acount(), 1)
        message_sent_2 = mail.outbox[0]
        self.assertEqual(message_sent_2.to, [self.recipient_user_2.user.email])

        # One webhook should be triggered
        webhook_triggered = WebhookEvent.objects.filter()
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 1)
        webhook_triggered_first = await webhook_triggered.afirst()
        self.assertEqual(
            webhook_triggered_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )

        with mock.patch("cl.users.signals.notify_new_or_updated_webhook"):
            webhook_2_1 = await sync_to_async(WebhookFactory)(
                user=self.user_profile.user,
                event_type=WebhookEventType.DOCKET_ALERT,
                url="https://example.com/",
                enabled=True,
                version=2,
            )
        self.assertEqual(
            await Webhook.objects.all().acount(),
            3,
            msg="Wrong number of webhook endpoints",
        )
        # Trigger a new recap.email notification, same case, different document
        # from testing_1@recap.email, auto-subscription option enabled
        await self.async_client.post(self.path, self.data, format="json")

        # A DocketAlert should be created when receiving the first notification
        # for this case and user (testing_1@recap.email)
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        self.assertEqual(await recap_document.acount(), 2)
        self.assertEqual(await Docket.objects.all().acount(), 1)
        docket_alert_2 = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(await docket_alert_2.acount(), 1)

        # 2 more emails should go out, one for testing_2@recap.email and one
        # for testing_1@recap.email
        message_sent = mail.outbox[1]
        self.assertEqual(message_sent.to, [self.recipient_user_2.user.email])
        message_sent = mail.outbox[2]
        self.assertEqual(message_sent.to, [self.recipient_user.user.email])
        self.assertEqual(len(mail.outbox), 3)

        # 3 more webhooks should be triggered, one for testing_2@recap.email
        # and 2 for testing_1@recap.email
        webhooks_triggered = WebhookEvent.objects.filter()
        self.assertEqual(
            await webhooks_triggered.acount(),
            4,
            msg="Wrong number of webhooks.",
        )

        async for webhook_sent in webhooks_triggered:
            self.assertEqual(
                webhook_sent.event_status, WEBHOOK_EVENT_STATUS.SUCCESSFUL
            )
        webhook_user_2 = WebhookEvent.objects.filter(webhook=self.webhook_2)
        self.assertEqual(await webhook_user_2.acount(), 2)
        webhook_user_1 = WebhookEvent.objects.filter(webhook=self.webhook)
        self.assertEqual(await webhook_user_1.acount(), 1)
        webhook_2_user_1 = WebhookEvent.objects.filter(webhook=webhook_2_1)
        self.assertEqual(await webhook_2_user_1.acount(), 1)

        # Confirm webhook versions.
        version_1_webhook = await webhook_user_1.afirst()
        webhook_version = version_1_webhook.content["webhook"]["version"]
        self.assertEqual(webhook_version, 1)

        version_2_webhook = await webhook_2_user_1.afirst()
        webhook_version = version_2_webhook.content["webhook"]["version"]
        self.assertEqual(webhook_version, 2)

        version_2_webhook = await webhook_user_2.afirst()
        webhook_version = version_2_webhook.content["webhook"]["version"]
        self.assertEqual(webhook_version, 2)

        # Confirm deprecation date webhooks according the version.
        v1_webhook_event = await WebhookEvent.objects.filter(
            webhook=self.webhook
        ).afirst()
        v2_webhook_event = await WebhookEvent.objects.filter(
            webhook=webhook_2_1
        ).afirst()
        self.assertEqual(
            v1_webhook_event.content["webhook"]["deprecation_date"],
            get_webhook_deprecation_date(settings.WEBHOOK_V1_DEPRECATION_DATE),
        )
        self.assertEqual(
            v2_webhook_event.content["webhook"]["deprecation_date"], None
        )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_recap_email_case_no_auto_subscription(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test verifies that if a new recap.email notification comes in
        and the user has auto-subscribe option disabled an Unsubscription
        DocketAlert is created, then send a first user-case email with a
        subscription link for the case.
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        # auto-subscription option disabled
        self.recipient_user.auto_subscribe = False
        await self.recipient_user.asave()
        await self.async_client.post(self.path, self.data, format="json")

        # Can we get the recap.email recipient properly?
        email_processing = EmailProcessingQueue.objects.all()
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.destination_emails,
            ["testing_1@recap.email"],
        )

        # A DocketAlert should be created when receiving the first notification
        # for this case with Unsubscription type, since user has the
        # auto-subscribe False.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.UNSUBSCRIPTION,
        )
        self.assertEqual(await docket_alert.acount(), 1)

        # A first user-case email should go out
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("[Sign-Up Needed]:", message.subject)

        # No webhook should be triggered
        webhook_triggered = WebhookEvent.objects.all()
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 0)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_recap_email_case_no_auto_subscription_prev_user(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test checks if a new recap.email (first time) notification
        comes in and user has auto-subscribe option disabled, an unsubscription
        DocketAlert is created then send a first user-case email with a
        subscription link, it also has to be sent an alert to the previous user
        subscribed to the case.
        """

        # Trigger a new recap.email notification from testing_2@recap.email
        # auto-subscription option enabled
        await self.async_client.post(self.path, self.data_3, format="json")

        # A DocketAlert email for testing_2@recap.email should go out
        self.assertEqual(await DocketAlert.objects.all().acount(), 1)
        message_sent = mail.outbox[0]
        self.assertIn("1 New Docket Entry for", message_sent.subject)
        self.assertEqual(message_sent.to, [self.recipient_user_2.user.email])

        # One webhook should be triggered for testing_2@recap.email
        webhook_triggered = WebhookEvent.objects.filter()
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 1)
        webhook_triggered_first = await webhook_triggered.afirst()
        self.assertEqual(
            webhook_triggered_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )

        # Trigger a new recap.email notification, same case, different document
        # from testing_1@recap.email, auto-subscription option disabled
        self.recipient_user.auto_subscribe = False
        await self.recipient_user.asave()
        await self.async_client.post(self.path, self.data, format="json")

        # A DocketAlert should be created when receiving the first notification
        # for this case with Unsubscription type, since user has the
        # auto-subscribe False.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        self.assertEqual(await recap_document.acount(), 2)
        self.assertEqual(await Docket.objects.acount(), 1)
        docket_alert_2 = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.UNSUBSCRIPTION,
        )
        self.assertEqual(await docket_alert_2.acount(), 1)

        # 2 more emails should go out, a first user-case email for
        # testing_1@recap.email and one alert for testing_2@recap.email
        self.assertEqual(len(mail.outbox), 3)
        message_sent = mail.outbox[1]
        self.assertNotIn("[Sign-Up Needed]", message_sent.subject)
        self.assertEqual(message_sent.to, [self.recipient_user_2.user.email])
        message_sent = mail.outbox[2]
        self.assertIn("[Sign-Up Needed]:", message_sent.subject)
        self.assertEqual(message_sent.to, [self.recipient_user.user.email])

        # One more webhook should be triggered, one for testing_2@recap.email
        # none for testing_1@recap.email
        webhooks_triggered = WebhookEvent.objects.filter()
        self.assertEqual(await webhooks_triggered.acount(), 2)
        async for webhook_sent in webhooks_triggered:
            self.assertEqual(
                webhook_sent.event_status, WEBHOOK_EVENT_STATUS.SUCCESSFUL
            )
        webhook_user_2 = WebhookEvent.objects.filter(webhook=self.webhook_2)
        self.assertEqual(await webhook_user_2.acount(), 2)
        webhook_user_1 = WebhookEvent.objects.filter(webhook=self.webhook)
        self.assertEqual(await webhook_user_1.acount(), 0)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(
                200,
                mock_bucket_open("nda_document.pdf", "rb", True),
            ),
            "OK",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "011112443447",
    )
    async def test_no_recap_email_user_found(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test verifies that if we receive a notification from a
        recap.email address that don't exist in DB, we send a notification to
        admins.
        """

        # Trigger a new recap.email notification from newuser_2@recap.email
        await self.async_client.post(
            self.path, self.data_no_user, format="json"
        )

        # Can we get the recap.email recipient properly?
        email_processing = EmailProcessingQueue.objects.all()
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.destination_emails,
            ["newuser_2@recap.email"],
        )

        # A @recap.email user not found notification should go out
        message_sent = mail.outbox[0]
        self.assertEqual(message_sent.subject, "@recap.email user not found")
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_receive_same_recap_email_notification_different_users(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test verifies that if we receive two notifications for the same
        case/document but different users. The first user has auto-subscribe
        option enabled. When the second notification is received only the
        second user should be notified.
        """

        # Trigger a new recap.email notification from testing_2@recap.email
        # auto-subscription option enabled
        await self.async_client.post(self.path, self.data_3, format="json")

        # Can we get the recap.email recipient properly?
        email_processing = EmailProcessingQueue.objects.all().order_by("pk")
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.destination_emails,
            ["testing_2@recap.email"],
        )

        # A DocketAlert email for testing_2@recap.email should go out
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        self.assertEqual(await recap_document.acount(), 1)
        message_sent_2 = mail.outbox[0]
        self.assertEqual(message_sent_2.to, [self.recipient_user_2.user.email])

        # Confirm EPQ values.
        self.assertEqual(await email_processing.acount(), 1)
        await email_processing_first.arefresh_from_db()
        self.assertEqual(
            email_processing_first.status, PROCESSING_STATUS.SUCCESSFUL
        )

        # Confirm RDs are correctly associated to the new EQP.
        self.assertEqual(
            [
                rd
                async for rd in email_processing_first.recap_documents.values_list(
                    "pk", flat=True
                )
            ],
            [
                rd
                async for rd in RECAPDocument.objects.all().values_list(
                    "pk", flat=True
                )
            ],
        )

        # A DocketAlert should be created when receiving the first notification
        # for this case and user (testing_2@recap.email)
        docket_alert_1 = DocketAlert.objects.filter(
            user=self.recipient_user_2.user,
            docket=docket,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(await docket_alert_1.acount(), 1)

        # Webhook should be triggered
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook_2)
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 1)
        webhook_triggered_first = await webhook_triggered.afirst()
        content = webhook_triggered_first.content
        # Compare the content of the webhook to the recap document
        pacer_doc_id = content["payload"]["results"][0]["recap_documents"][0][
            "pacer_doc_id"
        ]
        await recap_document_first.arefresh_from_db()
        self.assertEqual(recap_document_first.pacer_doc_id, pacer_doc_id)
        self.assertEqual(
            webhook_triggered_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )

        # Trigger a new recap.email notification, same case and same document
        # for testing_1@recap.email, auto-subscription option enabled
        await self.async_client.post(self.path, self.data_2, format="json")

        # No new recap document should be created.
        self.assertEqual(await recap_document.acount(), 1)
        self.assertEqual(await Docket.objects.all().acount(), 1)
        # A DocketAlert should be created when receiving the first notification
        # for this case for user (testing_1@recap.email)
        docket_alert_2 = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(await docket_alert_2.acount(), 1)

        # Confirm a new EQP is created.
        email_processing = EmailProcessingQueue.objects.all().order_by("pk")
        self.assertEqual(await email_processing.acount(), 2)
        email_processing_last = await email_processing.alast()
        self.assertEqual(
            email_processing_last.status, PROCESSING_STATUS.SUCCESSFUL
        )

        # Confirm RDs are correctly associated to the new EQP.
        self.assertEqual(
            [
                rd
                async for rd in email_processing_last.recap_documents.values_list(
                    "pk", flat=True
                )
            ],
            [
                rd
                async for rd in RECAPDocument.objects.all().values_list(
                    "pk", flat=True
                )
            ],
        )

        # Webhook for users that were subscribed previously shouldn't be
        # triggered again
        self.assertEqual(await webhook_triggered.acount(), 1)

        # Webhook for the new recap email user should be triggered
        webhook_triggered_2 = WebhookEvent.objects.filter(webhook=self.webhook)
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered_2.acount(), 1)
        webhook_triggered_2_first = await webhook_triggered_2.afirst()
        self.assertEqual(
            webhook_triggered_2_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )
        content = webhook_triggered_2_first.content
        # Compare the content of the webhook to the recap document
        pacer_doc_id = content["payload"]["results"][0]["recap_documents"][0][
            "pacer_doc_id"
        ]
        await recap_document_first.arefresh_from_db()
        self.assertEqual(recap_document_first.pacer_doc_id, pacer_doc_id)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_recap_email_subscribe_by_email_link(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test verifies if a recap.email user with the auto-subscribe
        option disabled can successfully subscribe to a case from the
        subscription link contained within the first user-case email.
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        # auto-subscription option disabled
        self.recipient_user.auto_subscribe = False
        await self.recipient_user.asave()
        await self.async_client.post(self.path, self.data, format="json")

        # A DocketAlert should be created when receiving the first notification
        # for this case with Unsubscription type, since user has the
        # auto-subscribe False.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.UNSUBSCRIPTION,
        )
        docket_alert_first = await docket_alert.afirst()
        self.assertEqual(await docket_alert.acount(), 1)

        # No webhook should be triggered for testing_1@recap.email
        webhook_triggered = WebhookEvent.objects.filter()
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 0)

        # Authenticate user to avoid the subscription confirmation form
        await self.async_client.alogin(
            username=self.recipient_user.user.username, password="password"
        )
        # Subscribe to the case from first user-case email subscription link
        await self.async_client.get(
            reverse(
                "toggle_docket_alert_confirmation",
                args=["subscribe", docket_alert_first.secret_key],
            )
        )
        docket_alert_subscription = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        # The DocketAlert should be toggled to Subscription type.
        self.assertEqual(await docket_alert.acount(), 0)
        self.assertEqual(await docket_alert_subscription.acount(), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_recap_email_unsubscribe_by_email_link(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test verifies if a recap.email user can successfully
        unsubscribe to a case from the unsubscription link.
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        # auto-subscription option enabled
        await self.async_client.post(self.path, self.data, format="json")

        # A DocketAlert should be created when receiving the first notification
        # for this case with Subscription type, since user has
        # auto-subscribe True.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
        )
        self.assertEqual(await docket_alert.acount(), 1)
        docket_alert_first = await docket_alert.afirst()
        self.assertEqual(
            docket_alert_first.alert_type, DocketAlert.SUBSCRIPTION
        )

        # A DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertEqual(message_sent.to, [self.recipient_user.user.email])

        # One webhook should be triggered for testing_1@recap.email
        webhook_triggered = WebhookEvent.objects.filter()
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 1)
        webhook_triggered_first = await webhook_triggered.afirst()
        self.assertEqual(
            webhook_triggered_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )

        # Authenticate user to avoid the unsubscription confirmation form
        await self.async_client.alogin(
            username=self.recipient_user.user.username, password="password"
        )
        # Unsubscribe from email link
        await self.async_client.get(
            reverse(
                "toggle_docket_alert_confirmation",
                args=["unsubscribe", docket_alert_first.secret_key],
            )
        )

        # The DocketAlert should be toggled to Unsubscription type.
        await docket_alert_first.arefresh_from_db()
        self.assertEqual(
            docket_alert_first.alert_type, DocketAlert.UNSUBSCRIPTION
        )

        # The unsubscription confirmation email should go out
        self.assertEqual(len(mail.outbox), 2)
        message_sent = mail.outbox[1]
        self.assertIn("[Unsubscribed]", message_sent.subject)

        # Trigger a new recap.email notification, same case, different document
        # from testing_1@recap.email
        await self.async_client.post(self.path, self.data_2, format="json")
        # No new Subscription should be created.
        self.assertEqual(await docket_alert.acount(), 1)
        # No new notification for the same case should go out
        self.assertEqual(len(mail.outbox), 2)

        # No more webhooks should be triggered
        webhook_triggered = WebhookEvent.objects.filter()
        self.assertEqual(await webhook_triggered.acount(), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_recap_email_alerts_integration(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test verifies if a user can successfully unsubscribe from a
        case using the email unsubscription link, the user won't longer receive
        more notifications for this case, we also send an unsubscription
        confirmation email to the user.
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        # auto-subscription option disabled
        self.recipient_user.auto_subscribe = False
        await self.recipient_user.asave()
        await self.async_client.post(self.path, self.data, format="json")

        # A DocketAlert should be created when receiving the first notification
        # for this case with Unsubscription type, since user has the
        # auto-subscribe False.
        email_processing = EmailProcessingQueue.objects.all().order_by("pk")
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
        )

        docket_alert_first = await docket_alert.afirst()
        # Confirm EPQ values.
        self.assertEqual(await email_processing.acount(), 1)
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.status, PROCESSING_STATUS.SUCCESSFUL
        )

        # Confirm RDs are correctly associated to the new EQP.
        self.assertEqual(
            [
                rd
                async for rd in email_processing_first.recap_documents.values_list(
                    "pk", flat=True
                )
            ],
            [
                rd
                async for rd in RECAPDocument.objects.all().values_list(
                    "pk", flat=True
                )
            ],
        )

        self.assertEqual(await docket_alert.acount(), 1)
        await docket_alert_first.arefresh_from_db()
        self.assertEqual(
            docket_alert_first.alert_type, DocketAlert.UNSUBSCRIPTION
        )

        # A first user-case email should go out
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertIn("[Sign-Up Needed]:", message_sent.subject)
        self.assertEqual(message_sent.to, [self.recipient_user.user.email])

        webhook_triggered = WebhookEvent.objects.all()
        # No webhook should be triggered.
        self.assertEqual(await webhook_triggered.acount(), 0)

        # Authenticate user to avoid the confirmation form
        await self.async_client.alogin(
            username=self.recipient_user.user.username, password="password"
        )
        # Subscribe to the case from first user-case email subscription link
        await self.async_client.get(
            reverse(
                "toggle_docket_alert_confirmation",
                args=["subscribe", docket_alert_first.secret_key],
            )
        )
        await docket_alert_first.arefresh_from_db()
        self.assertEqual(
            docket_alert_first.alert_type, DocketAlert.SUBSCRIPTION
        )

        # Trigger a new recap.email notification, same case, different document
        # from testing_1@recap.email, auto-subscription option enabled
        await self.async_client.post(self.path, self.data_2, format="json")
        # No new Subscription should be created.
        self.assertEqual(await docket_alert.acount(), 1)

        # A second notification for the same case should go out
        self.assertEqual(len(mail.outbox), 2)
        message_sent = mail.outbox[1]
        self.assertIn("1 New Docket Entry for", message_sent.subject)
        self.assertEqual(message_sent.to, [self.recipient_user.user.email])

        # Different recap documents created for the same Docket.
        self.assertEqual(await recap_document.acount(), 2)
        recap_document_first = await recap_document.afirst()
        recap_document_last = await recap_document.alast()
        self.assertNotEqual(recap_document_first.pk, recap_document_last.pk)
        self.assertNotEqual(
            recap_document_first.docket_entry.pk,
            recap_document_last.docket_entry.pk,
        )
        self.assertEqual(
            recap_document_first.docket_entry.docket.pk,
            recap_document_last.docket_entry.docket.pk,
        )

        # A webhook event should be triggered since user is now subscribed.
        self.assertEqual(await webhook_triggered.acount(), 1)
        webhook_triggered_first = await webhook_triggered.afirst()
        self.assertEqual(
            webhook_triggered_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )
        await self.async_client.get(
            reverse(
                "toggle_docket_alert_confirmation",
                args=["unsubscribe", docket_alert_first.secret_key],
            )
        )

        # The DocketAlert should be toggled to Unsubscription type.
        await docket_alert_first.arefresh_from_db()
        self.assertEqual(
            docket_alert_first.alert_type, DocketAlert.UNSUBSCRIPTION
        )

        # The unsubscription confirmation email should go out
        self.assertEqual(len(mail.outbox), 3)
        message_sent = mail.outbox[2]
        self.assertIn("[Unsubscribed]", message_sent.subject)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_docket_alert_toggle_confirmation_fails(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """This test verifies if the unsubscription/subscription fails if a bot
        tries to unsubscribe/subscribe from/to a docket alert.
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        # auto-subscription option enabled
        await self.async_client.post(self.path, self.data, format="json")

        # A DocketAlert should be created when receiving the first notification
        # for this case with Subscription type, since user has
        # auto-subscribe True.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
        )
        self.assertEqual(await docket_alert.acount(), 1)
        docket_alert_first = await docket_alert.afirst()
        self.assertEqual(
            docket_alert_first.alert_type, DocketAlert.SUBSCRIPTION
        )

        # Unauthenticated user tries to unsubscribe via GET and POST
        await self.async_client.get(
            reverse(
                "toggle_docket_alert_confirmation",
                args=["unsubscribe", docket_alert_first.secret_key],
            )
        )
        await self.async_client.post(
            reverse(
                "toggle_docket_alert_confirmation",
                args=["unsubscribe", docket_alert_first.secret_key],
            ),
            {},
        )
        # The DocketAlert should remain in Subscription type.
        await docket_alert_first.arefresh_from_db()
        self.assertEqual(
            docket_alert_first.alert_type, DocketAlert.SUBSCRIPTION
        )

        # Update the DocketAlert to Unsubscription type
        await docket_alert.aupdate(alert_type=DocketAlert.UNSUBSCRIPTION)
        # Unauthenticated user tries to subscribe via GET and POST
        await self.async_client.get(
            reverse(
                "toggle_docket_alert_confirmation",
                args=["subscribe", docket_alert_first.secret_key],
            )
        )
        await self.async_client.post(
            reverse(
                "toggle_docket_alert_confirmation",
                args=["subscribe", docket_alert_first.secret_key],
            ),
            {},
        )
        # The DocketAlert should remain in unsubscription type.
        await docket_alert_first.arefresh_from_db()
        self.assertEqual(
            docket_alert_first.alert_type, DocketAlert.UNSUBSCRIPTION
        )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b""),
            "OK",
        ),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    @mock.patch(
        "cl.recap.tasks.requests.get",
        side_effect=lambda *args, **kwargs: MockResponse(
            200, mock_bucket_open("nyed_123019137279.html", "r", True)
        ),
    )
    async def test_new_recap_email_with_attachments(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
        mock_att_response,
    ):
        """This test verifies that if a recap.email notification with
        attachments comes in we can get the main document and all its
        attachments. The docket alert and webhook should be sent with all the
        recap documents.
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        # auto-subscription option enabled
        await self.async_client.post(self.path, self.data_4, format="json")

        # Can we get the recap.email recipient properly?
        email_processing = EmailProcessingQueue.objects.all().order_by("pk")
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.destination_emails,
            ["testing_1@recap.email"],
        )

        # Confirm EPQ values.
        self.assertEqual(await email_processing.acount(), 1)
        self.assertEqual(
            email_processing_first.status, PROCESSING_STATUS.SUCCESSFUL
        )

        # Confirm RDs are correctly associated to the new EQP.
        self.assertEqual(
            [
                rd
                async for rd in email_processing_first.recap_documents.values_list(
                    "pk", flat=True
                )
            ],
            [
                rd
                async for rd in RECAPDocument.objects.all().values_list(
                    "pk", flat=True
                )
            ],
        )

        # A DocketAlert should be created when receiving the first notification
        # for this case with Subscription type, since user has
        # auto-subscribe True.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        self.assertEqual(await recap_document.acount(), 10)

        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(await docket_alert.acount(), 1)

        # A DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertEqual(message_sent.to, [self.recipient_user.user.email])

        # Webhook should be triggered
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 1)
        webhook_triggered_first = await webhook_triggered.afirst()
        self.assertEqual(
            webhook_triggered_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )
        content = webhook_triggered_first.content
        # Compare the content of the webhook to the recap document
        pacer_doc_id = content["payload"]["results"][0]["recap_documents"][0][
            "pacer_doc_id"
        ]
        recap_documents_webhook = content["payload"]["results"][0][
            "recap_documents"
        ]
        await recap_document_first.arefresh_from_db()
        self.assertEqual(recap_document_first.pacer_doc_id, pacer_doc_id)
        # Document available from magic link, not sealed.
        self.assertEqual(recap_document_first.is_sealed, False)
        # We should send 10 recap documents in this webhook example
        self.assertEqual(len(recap_documents_webhook), 10)
        # Compare content for the main document and the first attachment
        # Main document
        self.assertEqual(
            recap_documents_webhook[0]["description"],
            "Case Management Statement",
        )
        self.assertEqual(
            recap_documents_webhook[0]["pacer_doc_id"], "123019137279"
        )
        self.assertEqual(recap_documents_webhook[0]["document_number"], "16")
        self.assertEqual(recap_documents_webhook[0]["attachment_number"], None)

        # First attachment
        self.assertEqual(
            recap_documents_webhook[1]["description"],
            "Proposed Order Proposed Case Management Plan (as discussed in the letter)",
        )
        self.assertEqual(
            recap_documents_webhook[1]["pacer_doc_id"], "123019137280"
        )
        self.assertEqual(recap_documents_webhook[1]["document_number"], "16")
        self.assertEqual(recap_documents_webhook[1]["attachment_number"], 1)

        # Confirm documents are not sealed in the webhook payload
        is_sealed = content["payload"]["results"][0]["recap_documents"][0][
            "is_sealed"
        ]
        self.assertEqual(is_sealed, False)

        # Trigger the recap.email notification again for the same user, it
        # should be processed.
        await self.async_client.post(self.path, self.data_4, format="json")

        # No new recap documents should be added.
        self.assertEqual(await recap_document.acount(), 10)

        # No new docket alert or webhooks should be triggered.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(await webhook_triggered.acount(), 1)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        side_effect=lambda x: True,
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(
                200,
                mock_bucket_open(
                    "gov.uscourts.ca1.12-2209.00106475093.0.pdf", "rb", True
                ),
            ),
            "OK",
        ),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_extract_pdf_for_recap_email(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_docket_entry_sealed,
        mock_cookie,
        mock_download_pdf,
        mock_webhook_post,
    ):
        """This test checks if the content extraction of a PDF obtained from
        recap.email is successfully performed..
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data, format="json")

        recap_document = RECAPDocument.objects.all()
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.is_available, True)

        # Plain text is extracted properly.
        self.assertNotEqual(recap_document_first.plain_text, "")

        self.assertEqual(recap_document_first.needs_extraction, False)
        self.assertEqual(
            recap_document_first.ocr_status, RECAPDocument.OCR_UNNECESSARY
        )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b""),
            "OK",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "009033568259",
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_nda_recap_email(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pdf,
        mock_get_document_number_from_confirmation_page,
        mock_webhook_post,
    ):
        """This test verifies that if a new NDA recap.email notification comes
        in we can parse it properly.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data_5, format="json")

        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)

        # Compare the NDA docket and recap document metadata
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        self.assertEqual(await recap_document.acount(), 1)
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.pacer_doc_id, "009033568259")
        self.assertEqual(recap_document_first.document_number, "009033568259")
        docket = recap_document_first.docket_entry.docket
        self.assertEqual(
            docket.case_name, "Rosemarie Vargas v. Facebook, Inc."
        )
        self.assertEqual(docket.pacer_case_id, "334146")
        self.assertEqual(docket.docket_number, "21-16499")

    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b""),
            "OK",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "009033568259",
    )
    async def test_new_nda_recap_email_case_auto_subscription(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_webhook_post,
        mock_download_pdf,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test verifies that if a new nda recap.email notification comes
        in (first time) and the user has the auto-subscribe option enabled, a
        new DocketAlert subscription is created for that user-case pair and
        then receives the docket alert email for this case.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        # auto-subscription option enabled
        await self.async_client.post(self.path, self.data_5, format="json")

        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)

        # A DocketAlert should be created when receiving the first notification
        # for this case with Subscription type, since user has
        # auto-subscribe True.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(await docket_alert.acount(), 1)

        # A DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertEqual(message_sent.to, [self.recipient_user.user.email])

        # Webhook should be triggered
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 1)
        webhook_triggered_first = await webhook_triggered.afirst()
        self.assertEqual(
            webhook_triggered_first.event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )
        content = webhook_triggered_first.content
        # Compare the content of the webhook to the recap document
        pacer_doc_id = content["payload"]["results"][0]["recap_documents"][0][
            "pacer_doc_id"
        ]
        await recap_document_first.arefresh_from_db()
        self.assertEqual(recap_document_first.pacer_doc_id, pacer_doc_id)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b""),
            "OK",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "009033568259",
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_new_nda_recap_email_case_no_auto_subscription(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pdf,
        mock_get_document_number_from_confirmation_page,
        mock_webhook_post,
    ):
        """This test verifies that if a new nda recap.email notification comes
        in and the user has auto-subscribe option disabled an Unsubscription
        DocketAlert is created, then send a first user-case email with a
        subscription link for the case.
        """

        # Trigger a new recap.email notification from testing_1@recap.email
        # auto-subscription option disabled
        self.recipient_user.auto_subscribe = False
        await self.recipient_user.asave()
        await self.async_client.post(self.path, self.data_5, format="json")

        # Can we get the recap.email recipient properly?
        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)

        # A DocketAlert should be created when receiving the first notification
        # for this case with Unsubscription type, since user has the
        # auto-subscribe False.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.UNSUBSCRIPTION,
        )
        self.assertEqual(await docket_alert.acount(), 1)

        # A first user-case email should go out
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("[Sign-Up Needed]:", message.subject)

        # No webhook should be triggered
        webhook_triggered = WebhookEvent.objects.all()
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 0)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        side_effect=lambda x: True,
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b"Hello World"),
            "OK",
        ),
    )
    @mock.patch(
        "cl.recap.tasks.requests.get",
        side_effect=lambda *args, **kwargs: MockResponse(
            200, mock_bucket_open("jpml_85001321035.html", "r", True)
        ),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_multiple_docket_nef(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_cookie,
        mock_download_pdf,
        mock_att_response,
        mock_webhook_response,
    ):
        """This test verifies that if a new multi docket nef recap.email
        notification comes in we can parse it properly. Send docket alerts and
        webhooks for each case.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        # Multi Docket NEF.
        await self.async_client.post(
            self.path, self.data_multi_jpml, format="json"
        )

        email_processing = EmailProcessingQueue.objects.all()
        # Confirm EPQ values.
        self.assertEqual(await email_processing.acount(), 1)
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.status, PROCESSING_STATUS.SUCCESSFUL
        )

        # Confirm RDs are correctly associated to the new EQP.
        self.assertEqual(
            [
                rd
                async for rd in email_processing_first.recap_documents.values_list(
                    "pk", flat=True
                )
            ],
            [
                rd
                async for rd in RECAPDocument.objects.all().values_list(
                    "pk", flat=True
                )
            ],
        )

        # Compare the docket and recap document metadata
        dockets = Docket.objects.all()
        self.assertEqual(await dockets.acount(), 3)

        case_names = [docket.case_name async for docket in dockets]
        # Check that all the case names are different between them
        self.assertTrue(len(set(case_names)) == len(case_names))

        docket_numbers = [docket.docket_number async for docket in dockets]
        # Check that all the docket_numbers are different between them
        self.assertTrue(len(set(docket_numbers)) == len(docket_numbers))

        docket_entries = DocketEntry.objects.all()
        self.assertEqual(await docket_entries.acount(), 3)
        docket_entry_numbers = [
            docket_entry.entry_number async for docket_entry in docket_entries
        ]
        # Check that all the docket_entry_numbers are different between them
        self.assertTrue(
            len(set(docket_entry_numbers)) == len(docket_entry_numbers)
        )

        recap_documents = RECAPDocument.objects.all()
        self.assertEqual(await recap_documents.acount(), 6)

        async for rd in recap_documents:
            # Every RECAPDocument should have a file stored at this point.
            self.assertTrue(rd.filepath_local)
            if not rd.attachment_number:
                # Check that every main RECAPDocument has the main pacer_doc_id
                self.assertEqual(rd.pacer_doc_id, "85001321035")
            if rd.attachment_number == 1:
                # Check that every attachment RECAPDocument has the attachment
                # pacer_doc_id
                self.assertEqual(rd.pacer_doc_id, "85001321036")

        docket_alerts = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(await docket_alerts.acount(), 3)
        # 3 DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 3)

        # 3 Webhook events should be triggered
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        # Does the webhook was triggered?
        self.assertEqual(await webhook_triggered.acount(), 3)
        async for webhook_event in webhook_triggered:
            self.assertEqual(
                webhook_event.event_status, WEBHOOK_EVENT_STATUS.SUCCESSFUL
            )

        webhook_entry_numbers = [
            webhook.content["payload"]["results"][0]["entry_number"]
            async for webhook in webhook_triggered
        ]
        # Check that all the webhook entry numbers are different between them
        self.assertTrue(
            len(set(webhook_entry_numbers)) == len(webhook_entry_numbers)
        )

        webhook_document_numbers = [
            webhook.content["payload"]["results"][0]["recap_documents"][0][
                "document_number"
            ]
            async for webhook in webhook_triggered
        ]
        # Check that all the webhook_document_numbers are different between
        # them
        self.assertTrue(
            len(set(webhook_document_numbers)) == len(webhook_document_numbers)
        )

        webhook_att_document_numbers = [
            webhook.content["payload"]["results"][0]["recap_documents"][1][
                "document_number"
            ]
            async for webhook in webhook_triggered
        ]
        # Check that all the webhook_att_document_numbers are different between
        # them
        self.assertTrue(
            len(set(webhook_att_document_numbers))
            == len(webhook_att_document_numbers)
        )

        # Check that all the PQ objects created are marked as SUCCESSFUL and
        # filepath_local deleted.
        pqs = ProcessingQueue.objects.all()
        async for pq in pqs:
            self.assertEqual(pq.status, PROCESSING_STATUS.SUCCESSFUL)
            self.assertFalse(pq.filepath_local)

        # Trigger the recap.email notification again for the same user, it
        # should be processed.
        await self.async_client.post(
            self.path, self.data_multi_jpml, format="json"
        )

        # No new recap documents should be added.
        self.assertEqual(len(recap_documents), 6)

        # No new docket alert or webhooks should be triggered.
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(await webhook_triggered.acount(), 3)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    @mock.patch(
        "cl.recap.tasks.get_document_number_for_appellate",
        side_effect=lambda z, x, y: "011112443447",
    )
    @mock.patch(
        "cl.recap.tasks.is_pacer_doc_sealed",
        side_effect=lambda z, x: False,
    )
    async def test_recap_email_no_magic_number(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
        mock_get_document_number_appellate,
        mock_is_pacer_doc_sealed,
    ):
        """Can we add docket entries from a recap email notification that don't
        contain a valid magic number?
        """

        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            side_effect=lambda x, y: (self.no_magic_number_data, "HTML"),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            # auto-subscription option enabled
            await self.async_client.post(self.path, self.data, format="json")

        # Can we get the recap.email recipient properly?
        email_processing = EmailProcessingQueue.objects.all()
        email_processing_first = await email_processing.afirst()
        self.assertEqual(
            email_processing_first.destination_emails,
            ["testing_1@recap.email"],
        )

        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        self.assertEqual(await recap_document.acount(), 1)
        # A DocketAlert should be created when receiving the first notification
        # for this case with Subscription type, since user has
        # auto-subscribe True.
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        docket_alert = DocketAlert.objects.filter(
            user=self.recipient_user.user,
            docket=docket,
            alert_type=DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(await docket_alert.acount(), 1)
        # A DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)

        pq = ProcessingQueue.objects.all()
        self.assertEqual(await pq.acount(), 1)
        pq_first = await pq.afirst()
        self.assertEqual(
            pq_first.error_message,
            "No magic number available to download the document.",
        )

        # Mock returns the document is not sealed.
        await recap_document_first.arefresh_from_db()
        self.assertEqual(recap_document_first.is_sealed, False)
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        webhook_triggered_first = await webhook_triggered.afirst()
        content = webhook_triggered_first.content
        # Confirm document is not sealed in the webhook payload.
        is_sealed = content["payload"]["results"][0]["recap_documents"][0][
            "is_sealed"
        ]
        self.assertEqual(is_sealed, False)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            None,
            "Document not available from magic link.",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "",
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_mark_as_sealed_nda_document_not_available_from_magic_link(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pdf,
        mock_get_document_number_from_confirmation_page,
        mock_webhook_post,
    ):
        """This test checks if we can mark as sealed a NDA document when the
        download is not available through the magic link.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data_5, format="json")

        recap_document = RECAPDocument.objects.all()
        self.assertEqual(await recap_document.acount(), 1)

        # Confirm the document is marked as sealed.
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.is_sealed, True)
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        webhook_triggered_first = await webhook_triggered.afirst()
        content = webhook_triggered_first.content
        # Is the document sealed in the webhook payload?
        is_sealed = content["payload"]["results"][0]["recap_documents"][0][
            "is_sealed"
        ]
        self.assertEqual(is_sealed, True)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    @mock.patch(
        "cl.recap.tasks.requests.get",
        side_effect=lambda *args, **kwargs: MockResponse(
            200, mock_bucket_open("nyed_123019137279.html", "r", True)
        ),
    )
    async def test_mark_as_sealed_nef_documents_not_available_from_magic_link(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
        mock_att_response,
    ):
        """This test verifies if a recap.email notification with attachments
        comes in and the documents are not available from the magic link,
        documents are mark as sealed.
        """

        # Trigger a new recap.email notification
        await self.async_client.post(self.path, self.data_4, format="json")

        recap_document = RECAPDocument.objects.all()
        # Main document is marked as sealed.
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.is_sealed, True)
        self.assertEqual(await recap_document.acount(), 10)

        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        webhook_triggered_first = await webhook_triggered.afirst()
        content = webhook_triggered_first.content
        # Compare the content of the webhook to the recap document
        recap_documents_webhook = content["payload"]["results"][0][
            "recap_documents"
        ]
        # We should send 10 recap documents in this webhook example
        self.assertEqual(len(recap_documents_webhook), 10)
        # All the documents including the attachments should be sealed.
        for rd in recap_documents_webhook:
            self.assertEqual(rd["is_sealed"], True)

    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    @mock.patch(
        "cl.recap.tasks.get_document_number_for_appellate",
        side_effect=lambda z, x, y: "011112443447",
    )
    @mock.patch(
        "cl.recap.tasks.is_pacer_doc_sealed",
        side_effect=lambda z, x: True,
    )
    async def test_recap_email_no_magic_number_sealed_document(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_get_document_number_appellate,
        mock_webhook_post,
        mock_is_pacer_doc_sealed,
    ):
        """This test checks if a document without magic number that is not
        available on PACER is marked as sealed.
        """

        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            side_effect=lambda x, y: (self.no_magic_number_data, "HTML"),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            # auto-subscription option enabled
            await self.async_client.post(self.path, self.data, format="json")

        recap_document = RECAPDocument.objects.all()
        self.assertEqual(await recap_document.acount(), 1)

        # Document is marked as sealed.
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.is_sealed, True)
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        webhook_triggered_first = await webhook_triggered.afirst()
        content = webhook_triggered_first.content
        # Confirm the document is sealed in webhook payload.
        is_sealed = content["payload"]["results"][0]["recap_documents"][0][
            "is_sealed"
        ]
        self.assertEqual(is_sealed, True)

    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_recap_email_minute_entry(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_webhook_post,
    ):
        """Can we add docket entries from a minute entry recap email
        notification?
        """

        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            side_effect=lambda x, y: (self.minute_entry_data, "HTML"),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            # auto-subscription option enabled
            await self.async_client.post(self.path, self.data, format="json")

        # Compare docket entry data.
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry__docket"
        )
        self.assertEqual(await recap_document.acount(), 1)
        recap_document_first = await recap_document.afirst()
        docket = recap_document_first.docket_entry.docket
        self.assertEqual(docket.pacer_case_id, "12345")
        self.assertEqual(recap_document_first.pacer_doc_id, "")
        self.assertEqual(recap_document_first.docket_entry.entry_number, None)

        # A DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)

        # We can't set the seal status of a minute entry.
        self.assertEqual(recap_document_first.is_sealed, None)
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)
        webhook_triggered_first = await webhook_triggered.afirst()
        content = webhook_triggered_first.content
        is_sealed = content["payload"]["results"][0]["recap_documents"][0][
            "is_sealed"
        ]
        self.assertEqual(is_sealed, None)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        return_value=(None, "Failed to get docket entry"),
    )
    @mock.patch("cl.recap.tasks.add_docket_entries")
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_recap_email_sealed_entry_no_attachments(
        self,
        mock_webhook_post,
        mock_add_docket_entries,
        mock_download_pdf_by_magic_number,
        mock_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
    ):
        """This test checks if a docket entry without attachments that is
        sealed on PACER is ignored.
        """
        mock_docket_entry_sealed.return_value = True
        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=False,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[RECAPEmailDocketEntryDataFactory()],
                )
            ],
        )

        court = await sync_to_async(CourtFactory)(
            id="sealed", jurisdiction="FB"
        )
        notification_payload = {
            "court": court.id,
            "mail": self.data["mail"],
            "receipt": self.data["receipt"],
        }

        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            return_value=(email_data, "HTML"),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            # auto-subscription option enabled
            await self.async_client.post(
                self.path, notification_payload, format="json"
            )

        docket_entry = email_data["dockets"][0]["docket_entries"]
        mock_docket_entry_sealed.assert_called_once_with(
            court.pk,
            docket_entry[0]["pacer_case_id"],
            docket_entry[0]["pacer_doc_id"],
        )

        # the process_recap_email task returns before trying to add a new entry
        mock_add_docket_entries.assert_not_called()

        pq_query = ProcessingQueue.objects.filter(
            pacer_doc_id=docket_entry[0]["pacer_doc_id"],
            pacer_case_id=docket_entry[0]["pacer_case_id"],
        )
        self.assertEqual(await pq_query.acount(), 1)
        processing_queue = await pq_query.afirst()
        self.assertIn(
            "Failed to get docket entry", processing_queue.error_message
        )
        # check we don't trigger alerts for sealed docket entries
        self.assertEqual(len(mail.outbox), 0)

        epq_query = EmailProcessingQueue.objects.filter(court_id=court.pk)
        self.assertEqual(await pq_query.acount(), 1)
        email_processing_queue = await epq_query.afirst()
        self.assertEqual(
            "Could not retrieve Docket Entry",
            email_processing_queue.status_message,
        )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        return_value=(None, "Failed to get docket entry"),
    )
    @mock.patch("cl.recap.tasks.fetch_attachment_data")
    @mock.patch("cl.recap.tasks.add_docket_entries")
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_recap_email_sealed_entry_with_attachments(
        self,
        mock_webhook_post,
        mock_add_docket_entries,
        mock_fetch_attachment_data,
        mock_download_pdf_by_magic_number,
        mock_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
    ):
        """This test checks if a docket entry with attachments that is
        sealed on PACER is ignored.
        """
        mock_docket_entry_sealed.return_value = True

        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=True,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[RECAPEmailDocketEntryDataFactory()],
                )
            ],
        )

        court = await sync_to_async(CourtFactory)(
            id="sealed2", jurisdiction="FB"
        )
        notification_payload = {
            "court": court.id,
            "mail": self.data["mail"],
            "receipt": self.data["receipt"],
        }

        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            return_value=(email_data, "HTML"),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            # auto-subscription option enabled
            await self.async_client.post(
                self.path, notification_payload, format="json"
            )

        docket_entry = email_data["dockets"][0]["docket_entries"]
        mock_docket_entry_sealed.assert_called_once_with(
            court.pk,
            docket_entry[0]["pacer_case_id"],
            docket_entry[0]["pacer_doc_id"],
        )

        # the process_recap_email task returns before trying to add a new entry
        mock_add_docket_entries.assert_not_called()
        mock_fetch_attachment_data.assert_not_called()

        # check we didn't create a docket entry
        docket_entry_query = DocketEntry.objects.filter(
            docket__pacer_case_id=docket_entry[0]["pacer_case_id"],
            entry_number=docket_entry[0]["document_number"],
        )
        self.assertEqual(await docket_entry_query.acount(), 0)

        pq_query = ProcessingQueue.objects.filter(
            pacer_doc_id=docket_entry[0]["pacer_doc_id"],
            pacer_case_id=docket_entry[0]["pacer_case_id"],
        )
        self.assertEqual(await pq_query.acount(), 1)
        processing_queue = await pq_query.afirst()
        self.assertIn(
            "Failed to get docket entry", processing_queue.error_message
        )
        # check we don't trigger alerts for sealed docket entries
        self.assertEqual(len(mail.outbox), 0)

        epq_query = EmailProcessingQueue.objects.filter(court_id=court.pk)
        self.assertEqual(await pq_query.acount(), 1)
        email_processing_queue = await epq_query.afirst()
        self.assertEqual(
            "Could not retrieve Docket Entry",
            email_processing_queue.status_message,
        )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        return_value=(None, "Document not available from magic link."),
    )
    @mock.patch(
        "cl.recap.tasks.get_attachment_page_by_url",
        return_value="<html>Sealed document</html>",
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_recap_email_sealed_document_with_attachments(
        self,
        mock_webhook_post,
        mock_get_attachment_page_by_url,
        mock_download_pdf_by_magic_number,
        mock_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
    ):
        """This test checks whether a document with attachments that is sealed
        on PACER is properly ingested. If the attachment page is also
        unavailable, the attachments are not merged.
        """

        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=True,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[RECAPEmailDocketEntryDataFactory()],
                )
            ],
        )

        court = await sync_to_async(CourtFactory)(id="nyed", jurisdiction="FB")
        notification_payload = {
            "court": court.id,
            "mail": self.data["mail"],
            "receipt": self.data["receipt"],
        }

        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            return_value=(email_data, "HTML"),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, notification_payload, format="json"
            )

        docket_entry = email_data["dockets"][0]["docket_entries"]
        docket_entry_query = DocketEntry.objects.filter(
            docket__pacer_case_id=docket_entry[0]["pacer_case_id"],
            entry_number=docket_entry[0]["document_number"],
        )
        self.assertEqual(await docket_entry_query.acount(), 1)

        # Only the main document is merged.
        de = await docket_entry_query.afirst()
        self.assertEqual(await de.recap_documents.all().acount(), 1)

        # An alert containing the main document sealed is sent.
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        return_value=(None, "Document not available from magic link."),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    @mock.patch(
        "cl.recap.tasks.get_attachment_page_by_url",
        return_value="<html>Sealed document</html>",
    )
    async def test_recap_email_sealed_document_with_no_sealed_attachments(
        self,
        mock_get_attachment_page_by_url,
        mock_webhook_post,
        mock_download_pdf_by_magic_number,
        mock_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
    ):
        """This test checks whether a document with attachments that is sealed
        on PACER are properly ingested when the attachment page is available.
        """

        att_data = AppellateAttachmentPageFactory(
            attachments=[
                AppellateAttachmentFactory(
                    pacer_doc_id="04505578699", attachment_number=1
                ),
            ],
            pacer_doc_id="04505578698",
        )

        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=True,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(
                            pacer_doc_id="04505578698"
                        )
                    ],
                )
            ],
        )

        court = await sync_to_async(CourtFactory)(id="nyed", jurisdiction="FB")
        notification_payload = {
            "court": court.id,
            "mail": self.data["mail"],
            "receipt": self.data["receipt"],
        }

        with (
            mock.patch(
                "cl.recap.tasks.get_data_from_att_report",
                side_effect=lambda x, y: att_data,
            ),
            mock.patch(
                "cl.recap.tasks.open_and_validate_email_notification",
                return_value=(email_data, "HTML"),
            ),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, notification_payload, format="json"
            )

        docket_entry = email_data["dockets"][0]["docket_entries"]
        docket_entry_query = DocketEntry.objects.filter(
            docket__pacer_case_id=docket_entry[0]["pacer_case_id"],
            entry_number=docket_entry[0]["document_number"],
        )
        self.assertEqual(await docket_entry_query.acount(), 1)

        # The main sealed document and one attachment should be ingested.
        de = await docket_entry_query.afirst()
        self.assertEqual(await de.recap_documents.all().acount(), 2)

        # Check RDs merged.
        main_doc = await RECAPDocument.objects.filter(
            docket_entry=de, document_type=RECAPDocument.PACER_DOCUMENT
        ).afirst()
        self.assertEqual(main_doc.is_sealed, True)
        att_doc = RECAPDocument.objects.filter(
            docket_entry=de, document_type=RECAPDocument.ATTACHMENT
        )
        self.assertEqual(await att_doc.acount(), 1)

        # An alert is sent.
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (None, ""),
    )
    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_recap_email_minute_entry_multi_nef(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_download_pacer_pdf_by_rd,
        mock_webhook_post,
    ):
        """Can we add docket entries from a multi-nef minute entry recap email
        notification?
        """

        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            side_effect=lambda x, y: (
                self.multi_nef_minute_entry_data,
                "HTML",
            ),
        ):
            # Trigger a new nda recap.email notification from testing_1@recap.email
            # Multi Docket NEF.
            await self.async_client.post(self.path, self.data, format="json")

        # Compare docket entry data.
        dockets = Docket.objects.all()
        self.assertEqual(await dockets.acount(), 2)
        docket_entries = DocketEntry.objects.all()
        self.assertEqual(await docket_entries.acount(), 2)
        recap_documents = RECAPDocument.objects.all().prefetch_related(
            "docket_entry"
        )
        self.assertEqual(await recap_documents.acount(), 2)

        async for rd in recap_documents:
            self.assertEqual(rd.pacer_doc_id, "")
            self.assertEqual(rd.is_sealed, None)
            self.assertEqual(rd.document_number, "")
            self.assertEqual(rd.docket_entry.entry_number, None)

        # A DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 2)

    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    async def test_recap_email_avoid_fetching_short_doc_id_docs(
        self,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_docket_entry_sealed,
        mock_webhook_post,
    ):
        """Can we avoid fetching the PDF and attachment page for bankruptcy
        emails with a bad short pacer_doc_id while still merging the entries
        and sending alerts?
        """

        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=True,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(
                            pacer_doc_id="0340", document_number="1"
                        )
                    ],
                ),
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(
                            pacer_doc_id="0340", document_number="1"
                        )
                    ],
                ),
            ],
        )
        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            side_effect=lambda x, y: (
                email_data,
                "HTML",
            ),
        ):
            # Trigger a new nda recap.email notification from canb
            await self.async_client.post(self.path, self.data, format="json")

        # Confirm entries were properly merged.
        dockets = Docket.objects.all()
        self.assertEqual(await dockets.acount(), 2)
        docket_entries = DocketEntry.objects.all()
        # Two docket entries should be merged. One for each docket.
        self.assertEqual(await docket_entries.acount(), 2)
        recap_documents = RECAPDocument.objects.all().prefetch_related(
            "docket_entry"
        )
        # There are two RECAP documents, one for each docket.
        self.assertEqual(await recap_documents.acount(), 2)
        async for rd in recap_documents:
            # The RD shouldn't be sealed. Since the retrieval is aborted for this document.
            self.assertEqual(
                rd.is_sealed, None, msg="Document shouldn't be sealed."
            )
            # The pacer_doc_id is merged as is.
            self.assertEqual(rd.pacer_doc_id, "")
            # The remaining metadata should be in place.
            self.assertEqual(rd.document_number, "1")
            self.assertEqual(rd.docket_entry.entry_number, 1)

        # DocketAlerts should trigger normally.
        self.assertEqual(
            len(mail.outbox), 2, msg="Wrong number of alerts triggered."
        )

        # Only one PQ should be created, and it should be marked as failed with
        # a custom message for this case.
        pqs = ProcessingQueue.objects.all()
        self.assertEqual(await pqs.acount(), 1)
        epq = await pqs.afirst()
        self.assertEqual(epq.status, PROCESSING_STATUS.FAILED)
        self.assertEqual(
            epq.error_message,
            "Invalid short pacer_doc_id for bankruptcy court.",
        )

        # No FQs should be created for copying the PDF.
        fqs = PacerFetchQueue.objects.all()
        self.assertEqual(await fqs.acount(), 0)


class GetAndCopyRecapAttachments(TestCase):
    """Test the get_and_copy_recap_attachment_docs method"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.get(username="recap-email")
        cls.d_1 = Docket.objects.create(
            source=0, court_id="scotus", pacer_case_id="12345"
        )
        cls.d_2 = Docket.objects.create(
            source=0, court_id="scotus", pacer_case_id="12345-1"
        )
        cls.d_3 = Docket.objects.create(
            source=0, court_id="scotus", pacer_case_id="12345-2"
        )
        de_1_1 = DocketEntry.objects.create(docket=cls.d_1, entry_number=1)
        de_2_1 = DocketEntry.objects.create(docket=cls.d_2, entry_number=1)
        de_3_1 = DocketEntry.objects.create(docket=cls.d_3, entry_number=1)

        des = [de_1_1, de_2_1, de_3_1]
        cls.rds_att = []
        for de in des:
            # Create main RDs
            RECAPDocument.objects.create(
                docket_entry=de,
                document_number="1",
                pacer_doc_id="04505578698",
                document_type=RECAPDocument.PACER_DOCUMENT,
            )

            # Create two attachments for each RD.
            rd_att_1 = RECAPDocument.objects.create(
                docket_entry=de,
                pacer_doc_id="04505578699",
                document_number="1",
                attachment_number=1,
                document_type=RECAPDocument.ATTACHMENT,
            )
            rd_att_2 = RECAPDocument.objects.create(
                docket_entry=de,
                pacer_doc_id="04505578700",
                document_number="1",
                attachment_number=2,
                document_type=RECAPDocument.ATTACHMENT,
            )

            cls.rds_att.append(rd_att_1)
            cls.rds_att.append(rd_att_2)

    def test_copy_pdf_attachments_from_pqs(self):
        """This test verifies that we can properly copy a PDF attachment from a
        PQ object to its corresponding RECAPDocument.
        """

        rds = RECAPDocument.objects.all()
        self.assertEqual(len(rds), 9)

        pq_att1 = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id=self.d_1.pacer_case_id,
            pacer_doc_id="04505578699",
            status=PROCESSING_STATUS.ENQUEUED,
            upload_type=UPLOAD_TYPE.PDF,
        )
        att1_content = b"Hello World att 1"
        filename_att1 = "att_1.pdf"
        cf_1 = ContentFile(att1_content)
        pq_att1.filepath_local.save(filename_att1, cf_1)

        pq_att2 = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id=self.d_1.pacer_case_id,
            pacer_doc_id="04505578700",
            status=PROCESSING_STATUS.ENQUEUED,
            upload_type=UPLOAD_TYPE.PDF,
        )
        att2_content = b"Hello World att 2"
        filename_att2 = "att_2.pdf"
        cf_2 = ContentFile(att2_content)
        pq_att2.filepath_local.save(filename_att2, cf_2)

        get_and_copy_recap_attachment_docs(
            self,
            self.rds_att,
            "scotus",
            "magic1234",
            "12345",
            self.user.pk,
        )

        rds_all = RECAPDocument.objects.all()
        for rd in rds_all:
            if rd.attachment_number == 1:
                with rd.filepath_local.open(mode="rb") as local_path:
                    self.assertEqual(local_path.read(), b"Hello World att 1")
            elif rd.attachment_number == 2:
                with rd.filepath_local.open(mode="rb") as local_path:
                    self.assertEqual(local_path.read(), b"Hello World att 2")

        # After successfully copying the attachment document from the PQ object
        # check if the PQ object is marked as successful and the file is deleted
        pqs = ProcessingQueue.objects.all()
        for pq in pqs:
            if pq.status != PROCESSING_STATUS.FAILED:
                async_to_sync(mark_pq_successful)(pq)
            self.assertEqual(pq.status, PROCESSING_STATUS.SUCCESSFUL)
            self.assertFalse(pq.filepath_local)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        side_effect=lambda x: True,
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b"Hello World from magic"),
            "OK",
        ),
    )
    def test_assign_pdf_attachmments_from_magic(
        self,
        mock_cookie,
        mock_download,
    ):
        """This test verifies that we can properly save a PDF attachment from a
        magic link, store it in a PQ object and finally copy the PDF
        attachment from the PQ object to its corresponding RECAPDocument.
        """

        rds = RECAPDocument.objects.all()
        self.assertEqual(len(rds), 9)
        get_and_copy_recap_attachment_docs(
            self,
            self.rds_att,
            "scotus",
            "magic1234",
            "12345",
            self.user.pk,
        )
        rds_all = RECAPDocument.objects.all()
        for rd in rds_all:
            if rd.attachment_number == 1:
                with rd.filepath_local.open(mode="rb") as local_path:
                    self.assertEqual(
                        local_path.read(), b"Hello World from magic"
                    )
            elif rd.attachment_number == 2:
                with rd.filepath_local.open(mode="rb") as local_path:
                    self.assertEqual(
                        local_path.read(), b"Hello World from magic"
                    )

        # After successfully copying the attachment document from the PQ object
        # check if the PQ object is marked as successful and the file is deleted
        pqs = ProcessingQueue.objects.all()
        for pq in pqs:
            if pq.status != PROCESSING_STATUS.FAILED:
                async_to_sync(mark_pq_successful)(pq)
            self.assertEqual(pq.status, PROCESSING_STATUS.SUCCESSFUL)
            self.assertFalse(pq.filepath_local)


@mock.patch(
    "cl.recap.tasks.RecapEmailSESStorage.open",
    side_effect=mock_bucket_open,
)
@mock.patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
@mock.patch(
    "cl.recap.tasks.get_or_cache_pacer_cookies",
    side_effect=lambda x, y, z: ("Cookie", settings.EGRESS_PROXY_HOSTS[0]),
)
@mock.patch(
    "cl.recap.tasks.get_pacer_cookie_from_cache",
    side_effect=lambda x: "Cookie",
)
class GetDocumentNumberForAppellateDocuments(TestCase):
    """Test if we can get the PACER document number for appellate documents
    either from the PDF document or the download confirmation page."""

    @classmethod
    def setUpTestData(cls):
        cls.court_ca9 = CourtFactory(id="ca9", jurisdiction="F")
        cls.court_ca11 = CourtFactory(id="ca11", jurisdiction="F")
        cls.court_ca2 = CourtFactory(id="ca2", jurisdiction="F")
        cls.court_ca8 = CourtFactory(id="ca8", jurisdiction="F")
        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "recap" / "test_assets"
        with (
            open(
                test_dir / "recap_mail_custom_receipt_nda.json",
                encoding="utf-8",
            ) as nda_file,
            open(
                test_dir / "recap_mail_custom_receipt_nda_ca11.json",
                encoding="utf-8",
            ) as ca11_file,
            open(
                test_dir / "recap_mail_custom_receipt_nda_ca2.json",
                encoding="utf-8",
            ) as ca2_file,
            open(
                test_dir / "recap_mail_custom_receipt_nda_ca8.json",
                encoding="utf-8",
            ) as ca8_file,
        ):
            recap_mail_receipt_nda = json.load(nda_file)
            recap_mail_receipt_nda_ca11 = json.load(ca11_file)
            recap_mail_receipt_nda_ca2 = json.load(ca2_file)
            recap_mail_receipt_nda_ca8 = json.load(ca8_file)
        cls.data_ca9 = {
            "court": cls.court_ca9.id,
            "mail": recap_mail_receipt_nda["mail"],
            "receipt": recap_mail_receipt_nda["receipt"],
        }
        cls.data_ca11 = {
            "court": cls.court_ca11.id,
            "mail": recap_mail_receipt_nda_ca11["mail"],
            "receipt": recap_mail_receipt_nda_ca11["receipt"],
        }
        cls.data_ca2 = {
            "court": cls.court_ca2.id,
            "mail": recap_mail_receipt_nda_ca2["mail"],
            "receipt": recap_mail_receipt_nda_ca2["receipt"],
        }
        cls.data_ca8 = {
            "court": cls.court_ca8.id,
            "mail": recap_mail_receipt_nda_ca8["mail"],
            "receipt": recap_mail_receipt_nda_ca8["receipt"],
        }

    def setUp(self) -> None:
        self.async_client = AsyncAPIClient()
        self.user = User.objects.get(username="recap-email")
        token = f"Token {self.user.auth_token.key}"
        self.async_client.credentials(HTTP_AUTHORIZATION=token)
        self.path = "/api/rest/v3/recap-email/"

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(
                200,
                mock_bucket_open("nda_document.pdf", "rb", True),
            ),
            "OK",
        ),
    )
    async def test_nda_get_document_number_from_pdf(
        self,
        mock_bucket_open,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_cookies_cache,
        mock_download_pacer_pdf,
    ):
        """This test verifies if we can get the PACER document number for
        appellate documents from the PDF document.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data_ca9, format="json")

        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)

        # Compare the NDA docket and recap document metadata
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry"
        )
        self.assertEqual(await recap_document.acount(), 1)
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.is_available, True)
        self.assertEqual(recap_document_first.document_number, "138")
        self.assertEqual(recap_document_first.docket_entry.entry_number, 138)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(
                200,
                mock_bucket_open(
                    "gov.uscourts.ca8.17-2543.00803263743.0.pdf", "rb", True
                ),
            ),
            "OK",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "011112443447",
    )
    async def test_nda_get_document_number_from_confirmation_page(
        self,
        mock_bucket_open,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_cookies_cache,
        mock_download_pacer_pdf,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test verifies if we can get the PACER document number for
        appellate documents from the download confirmation page.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data_ca11, format="json")

        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)

        # Compare the NDA docket and recap document metadata
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry"
        )
        self.assertEqual(await recap_document.acount(), 1)
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.is_available, True)
        self.assertEqual(recap_document_first.document_number, "011012443447")
        self.assertEqual(
            recap_document_first.docket_entry.entry_number, 11012443447
        )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(
                200,
                mock_bucket_open(
                    "gov.uscourts.ca8.17-2543.00803263743.0.pdf", "rb", True
                ),
            ),
            "OK",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "148",
    )
    async def test_nda_get_document_number_fallback(
        self,
        mock_bucket_open,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_cookies_cache,
        mock_download_pacer_pdf,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test verifies if we can get the PACER document number for
        appellate documents from the download confirmation page if getting it
        from the PDF document fails.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data_ca2, format="json")

        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)

        # Compare the NDA docket and recap document metadata
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry"
        )
        self.assertEqual(await recap_document.acount(), 1)
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.is_available, True)
        self.assertEqual(recap_document_first.document_number, "148")
        self.assertEqual(recap_document_first.docket_entry.entry_number, 148)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b""),
            "OK",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "",
    )
    async def test_nda_not_document_number_available(
        self,
        mock_bucket_open,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_cookies_cache,
        mock_download_pacer_pdf,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test checks if we can't get the document number from the PDF
        document or the download confirmation page. The RECAP document is added
        with an empty document number.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data_ca8, format="json")

        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry"
        )
        self.assertEqual(await recap_document.acount(), 1)
        # Document number keeps blank.
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.document_number, "")
        self.assertEqual(recap_document_first.docket_entry.entry_number, None)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b""),
            "OK",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "011112443447",
    )
    async def test_receive_same_recap_email_nda_notification_different_users(
        self,
        mock_bucket_open,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_cookies_cache,
        mock_download_pacer_pdf,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test verifies that if we receive two notifications for the same
        case/document but different users the docket entry is not duplicated.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data_ca11, format="json")

        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)

        # Compare the NDA docket and recap document metadata
        recap_document = RECAPDocument.objects.all()
        docket_entry = DocketEntry.objects.all()
        self.assertEqual(await recap_document.acount(), 1)
        self.assertEqual(await docket_entry.acount(), 1)

        # Trigger a new nda recap.email notification for the same case/document
        await self.async_client.post(self.path, self.data_ca11, format="json")
        recap_document_2 = RECAPDocument.objects.all()
        docket_entry_2 = DocketEntry.objects.all()
        # No duplicated docket entries and recap documents
        self.assertEqual(await recap_document_2.acount(), 1)
        self.assertEqual(await docket_entry_2.acount(), 1)
        recap_document_first = await recap_document.afirst()
        recap_document_2_first = await recap_document_2.afirst()
        self.assertEqual(recap_document_first.pk, recap_document_2_first.pk)
        docket_entry_first = await docket_entry.afirst()
        docket_entry_2_first = await docket_entry_2.afirst()
        self.assertEqual(docket_entry_first.pk, docket_entry_2_first.pk)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            None,
            "Document not available from magic link.",
        ),
    )
    @mock.patch(
        "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
        side_effect=lambda z, x: "148",
    )
    async def test_nda_document_not_available_get_from_confirmation_page(
        self,
        mock_bucket_open,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_cookies_cache,
        mock_download_pacer_pdf,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test checks if the PDF document is not available the
        document number is obtained from download confirmation page.
        """

        # Trigger a new nda recap.email notification from testing_1@recap.email
        await self.async_client.post(self.path, self.data_ca2, format="json")

        email_processing = EmailProcessingQueue.objects.all()
        self.assertEqual(await email_processing.acount(), 1)
        recap_document = RECAPDocument.objects.all().prefetch_related(
            "docket_entry"
        )
        self.assertEqual(await recap_document.acount(), 1)

        # Compare the NDA docket and recap document metadata
        recap_document_first = await recap_document.afirst()
        self.assertEqual(recap_document_first.document_number, "148")
        self.assertEqual(recap_document_first.docket_entry.entry_number, 148)


def mock_method_set_rd_sealed_status(
    rd: RECAPDocument, magic_number: str | None, potentially_sealed: bool
) -> None:
    if rd.document_type == RECAPDocument.PACER_DOCUMENT:
        set_rd_sealed_status(rd, magic_number, potentially_sealed=True)
        return
    return set_rd_sealed_status(rd, magic_number, potentially_sealed)


@mock.patch("cl.recap.tasks.enqueue_docket_alert", return_value=True)
@mock.patch(
    "cl.recap.tasks.RecapEmailSESStorage.open",
    side_effect=mock_bucket_open,
)
@mock.patch(
    "cl.recap.tasks.get_or_cache_pacer_cookies",
    side_effect=lambda x, y, z: (None, None),
)
@mock.patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
@mock.patch(
    "cl.recap.tasks.is_docket_entry_sealed",
    return_value=False,
)
class RecapEmailContentReplication(TestCase):
    """Test recap email docket alerts"""

    @classmethod
    def setUpTestData(cls):
        cls.user_profile = UserProfileWithParentsFactory()
        cls.court_canb = CourtFactory(id="canb", jurisdiction="FB")

        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "recap" / "test_assets"
        with (
            open(
                test_dir / "recap_mail_custom_receipt_multi_nef_jpml.json",
                encoding="utf-8",
            ) as file_jpml,
        ):
            recap_mail_receipt_multi_nef_jpml = json.load(file_jpml)

        cls.data_multi_canb = {
            "court": cls.court_canb.id,
            "mail": recap_mail_receipt_multi_nef_jpml["mail"],
            "receipt": recap_mail_receipt_multi_nef_jpml["receipt"],
        }

        cls.att_data = AppellateAttachmentPageFactory(
            attachments=[
                AppellateAttachmentFactory(
                    pacer_doc_id="04505578699", attachment_number=1
                ),
            ],
            pacer_doc_id="04505578698",
            document_number="1",
        )
        cls.email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=True,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(
                            pacer_doc_id="04505578698",
                            pacer_case_id="1309088",
                            document_number="1",
                        )
                    ],
                )
            ],
        )

    def setUp(self) -> None:
        self.async_client = AsyncAPIClient()
        self.user = User.objects.get(username="recap-email")
        token = f"Token {self.user.auth_token.key}"
        self.async_client.credentials(HTTP_AUTHORIZATION=token)
        self.path = "/api/rest/v3/recap-email/"

        recipient_user = self.user_profile
        recipient_user.user.email = "testing_1@mail.com"
        recipient_user.user.password = make_password("password")
        recipient_user.user.save()
        recipient_user.recap_email = "testing_1@recap.email"
        recipient_user.auto_subscribe = True
        recipient_user.save()
        self.recipient_user = recipient_user

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        side_effect=lambda x: True,
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b"Hello World"),
            "OK",
        ),
    )
    @mock.patch(
        "cl.recap.tasks.requests.get",
        side_effect=lambda *args, **kwargs: MockResponse(200, b"Att content."),
    )
    async def test_nef_subdocket_replication_no_att(
        self,
        mock_att_request,
        mock_download_pdf,
        mock_cookie,
        mock_docket_entry_sealed,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_bucket_open,
        mock_enqueue_alert,
    ):
        """Confirm that the main PDF is properly replicated from a simple NEF
        notification to subdockets for notifications that don't contain attachments.
        """
        # Create two Subdockets and RDs no mentioned in the email notification.
        de_1 = await sync_to_async(DocketEntryFactory)(
            docket=await sync_to_async(DocketFactory)(
                court=self.court_canb,
                case_name="Subdocket 1",
                docket_number="1:20-cv-01296",
                pacer_case_id="1309089",
            ),
            entry_number=18,
        )
        await sync_to_async(RECAPDocumentFactory)(
            docket_entry=de_1,
            pacer_doc_id="85001321035",
            document_number="18",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=False,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(
                            pacer_doc_id="85001321035",
                            document_number="1",
                            pacer_case_id="1309088",
                        )
                    ],
                )
            ],
        )
        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            side_effect=lambda x, y: (
                email_data,
                "HTML",
            ),
        ):
            # Trigger a multi-nef recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        # 2 dockets, 1 mentioned in the notification and 1 that is not
        dockets = Docket.objects.all()
        self.assertEqual(
            await dockets.acount(), 2, msg="Wrong number of Dockets."
        )
        # 2 docket entries, 1 mentioned in the notification and 1 that is not
        docket_entries = DocketEntry.objects.all()
        self.assertEqual(
            await docket_entries.acount(),
            2,
            msg="Wrong number of DocketEntries.",
        )
        # 2 RDs.
        recap_documents = RECAPDocument.objects.all()
        self.assertEqual(
            await recap_documents.acount(),
            2,
            msg="Wrong number of RECAPDocuments.",
        )
        # Every RECAPDocument should have a file stored at this point.
        async for rd in recap_documents:
            with self.subTest(rd=rd):
                self.assertTrue(rd.filepath_local)
                self.assertTrue(rd.is_available)
                self.assertEqual(rd.pacer_doc_id, "85001321035")

        # 1 DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)

        all_pqs_created = ProcessingQueue.objects.all().order_by("pk")
        self.assertEqual(
            await all_pqs_created.acount(),
            2,
            msg="Wrong number of ProcessingQueues.",
        )

        # Additional notifications should not trigger content replication.
        with (
            mock.patch(
                "cl.recap.tasks.open_and_validate_email_notification",
                side_effect=lambda x, y: (
                    email_data,
                    "HTML",
                ),
            ),
            mock.patch(
                "cl.recap.tasks.replicate_recap_email_to_subdockets"
            ) as mock_replication,
        ):
            # Trigger a recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        # Subdockets replication shouldn't be called.
        mock_replication.assert_not_called()
        # No new recap documents should be added.
        self.assertEqual(
            await recap_documents.acount(),
            2,
            msg="Wrong number of RECAPDocuments.",
        )
        all_pqs_created = ProcessingQueue.objects.all().order_by("pk")
        self.assertEqual(
            await all_pqs_created.acount(),
            3,
            "Wrong number of main PQS created.",
        )
        async for pq in all_pqs_created:
            # Files are cleaned up from all PQs created after
            # successful processing.
            with self.subTest(pq=pq):
                self.assertFalse(pq.filepath_local)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        side_effect=lambda x: True,
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b"Hello World"),
            "OK",
        ),
    )
    @mock.patch(
        "cl.recap.tasks.requests.get",
        side_effect=lambda *args, **kwargs: MockResponse(200, b"Att content."),
    )
    async def test_multi_nef_subdocket_replication(
        self,
        mock_att_request,
        mock_download_pdf,
        mock_cookie,
        mock_docket_entry_sealed,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_bucket_open,
        mock_enqueue_alert,
    ):
        """Confirm the main PDF and the related attachment data and attachment
        PDF are properly replicated from a multi-nef notification to subdockets.
        """

        # Create two Subdockets and RDs no mentioned in the email notification.
        de_1 = await sync_to_async(DocketEntryFactory)(
            docket=await sync_to_async(DocketFactory)(
                court=self.court_canb,
                case_name="Subdocket 1",
                docket_number="1:20-cv-01296",
                pacer_case_id="1309089",
            ),
            entry_number=18,
        )
        await sync_to_async(RECAPDocumentFactory)(
            docket_entry=de_1,
            pacer_doc_id="85001321035",
            document_number="18",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        de_2 = await sync_to_async(DocketEntryFactory)(
            docket=await sync_to_async(DocketFactory)(
                court=self.court_canb,
                case_name="Subdocket 2",
                docket_number="1:20-cv-01296",
                pacer_case_id="1309090",
            ),
            entry_number=18,
        )
        await sync_to_async(RECAPDocumentFactory)(
            docket_entry=de_2,
            pacer_doc_id="85001321035",
            document_number="18",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=True,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(
                            pacer_doc_id="85001321035",
                            document_number="1",
                            pacer_case_id="1309088",
                        )
                    ],
                ),
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(
                            pacer_doc_id="85001321035",
                            document_number="2",
                            pacer_case_id="1309087",
                        )
                    ],
                ),
            ],
        )
        att_data = AppellateAttachmentPageFactory(
            attachments=[
                AppellateAttachmentFactory(
                    pacer_doc_id="85001321036", attachment_number=1
                ),
                AppellateAttachmentFactory(
                    pacer_doc_id="85001321037", attachment_number=2
                ),
            ],
            pacer_doc_id="85001321035",
            document_number="1",
        )

        with (
            mock.patch(
                "cl.recap.tasks.open_and_validate_email_notification",
                side_effect=lambda x, y: (
                    email_data,
                    "HTML",
                ),
            ),
            mock.patch(
                "cl.recap.tasks.get_data_from_att_report",
                side_effect=lambda x, y: att_data,
            ),
        ):
            # Trigger a multi-nef recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        # 4 dockets, two mentioned in the notification and two that are not
        dockets = Docket.objects.all()
        self.assertEqual(
            await dockets.acount(), 4, msg="Wrong number of Dockets."
        )
        # 4 docket entries, two mentioned in the notification and two that are not
        docket_entries = DocketEntry.objects.all()
        self.assertEqual(
            await docket_entries.acount(),
            4,
            msg="Wrong number of DocketEntries.",
        )
        # 8 RDs in total, 4 mentioned in the notification and 4 that are not.
        recap_documents = RECAPDocument.objects.all()
        self.assertEqual(
            await recap_documents.acount(),
            12,
            msg="Wrong number of RECAPDocuments.",
        )
        # 4 Main RDs.
        main_recap_documents = RECAPDocument.objects.filter(
            document_type=RECAPDocument.PACER_DOCUMENT
        )
        self.assertEqual(
            await main_recap_documents.acount(),
            4,
            msg="Wrong number of main RECAPDocuments.",
        )
        # 4 Attachment RDs.
        att_recap_documents = RECAPDocument.objects.filter(
            document_type=RECAPDocument.ATTACHMENT
        )
        self.assertEqual(
            await att_recap_documents.acount(),
            8,
            msg="Wrong number of attachment RECAPDocuments.",
        )

        all_pqs_created = ProcessingQueue.objects.all().order_by("pk")
        self.assertEqual(
            await all_pqs_created.acount(),
            13,
            msg="Wrong number of ProcessingQueues.",
        )

        # 7 PQs related to the main document:
        # One for storing the main PDF from the notification.
        # Two for storing the attachment page from the notification.
        # Two for replicating the main PDF to two subdockets.
        # Two for replicating the attachment page to two subdockets.
        main_pqs_created = ProcessingQueue.objects.filter(
            pacer_doc_id="85001321035"
        )
        self.assertEqual(
            await main_pqs_created.acount(),
            7,
            msg="Wrong number of ProcessingQueues.",
        )

        # 3 PQs related to PDF attachments:
        # One for storing the att PDF from the notification.
        # Two for replicating the att PDF to two subdockets.
        att_pqs_created = ProcessingQueue.objects.filter(
            pacer_doc_id="85001321036"
        )
        self.assertEqual(
            await att_pqs_created.acount(),
            3,
            msg="Wrong number of ProcessingQueues.",
        )
        async for rd in recap_documents:
            with self.subTest(rd=rd):
                # Every RECAPDocument should have a file stored at this point.
                self.assertTrue(rd.filepath_local)
                self.assertTrue(rd.is_available)
                if not rd.attachment_number:
                    # Check that every main RECAPDocument has the main pacer_doc_id
                    self.assertEqual(rd.pacer_doc_id, "85001321035")
                if rd.attachment_number == 1:
                    # Check that every attachment RECAPDocument has the attachment
                    # pacer_doc_id
                    self.assertEqual(rd.pacer_doc_id, "85001321036")

        # 2 DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 2)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        side_effect=lambda x: True,
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b"Hello World"),
            "OK",
        ),
    )
    @mock.patch(
        "cl.recap.tasks.requests.get",
        side_effect=lambda *args, **kwargs: MockResponse(200, b"Att content."),
    )
    async def test_avoid_triggering_replication_for_minute_entries(
        self,
        mock_att_request,
        mock_download_pdf,
        mock_cookie,
        mock_docket_entry_sealed,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_bucket_open,
        mock_enqueue_alert,
    ):
        """Confirm that the replicate_recap_email_to_subdockets method is not
        called for email notifications with minute entries.
        """

        minute_entry_data = RECAPEmailDocketEntryDataFactory(
            pacer_magic_num=None,
            document_number=None,
            document_url=None,
            pacer_doc_id=None,
            pacer_seq_no=None,
            pacer_case_id="12345",
        )

        minute_entry_data = RECAPEmailNotificationDataFactory(
            contains_attachments=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[minute_entry_data],
                )
            ],
        )

        with (
            mock.patch(
                "cl.recap.tasks.open_and_validate_email_notification",
                side_effect=lambda x, y: (
                    minute_entry_data,
                    "HTML",
                ),
            ),
            mock.patch(
                "cl.recap.tasks.replicate_recap_email_to_subdockets"
            ) as mock_replication,
        ):
            # Trigger a minute-entry recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        # Subdockets replication shouldn't be called.
        mock_replication.assert_not_called()

        dockets = Docket.objects.all()
        self.assertEqual(
            await dockets.acount(), 1, msg="Wrong number of Dockets."
        )
        # 1 docket entry
        docket_entries = DocketEntry.objects.all()
        self.assertEqual(
            await docket_entries.acount(),
            1,
            msg="Wrong number of DocketEntries.",
        )
        # 1 RD.
        recap_documents = RECAPDocument.objects.all()
        self.assertEqual(
            await recap_documents.acount(),
            1,
            msg="Wrong number of RECAPDocuments.",
        )
        # 1 DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        return_value=(None, "Document not available from magic link."),
    )
    @mock.patch(
        "cl.recap.tasks.get_attachment_page_by_url",
        return_value="<html>Sealed document</html>",
    )
    async def test_avoid_replication_seal_document_and_sealed_attachments(
        self,
        mock_get_attachment_page_by_url,
        mock_download_pdf_by_magic_number,
        mock_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
    ):
        """This test checks whether a document with attachments that is sealed
        and the attachment page is also unavailable no replication is triggered.
        """

        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=True,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[RECAPEmailDocketEntryDataFactory()],
                )
            ],
        )
        with (
            mock.patch(
                "cl.recap.tasks.open_and_validate_email_notification",
                return_value=(email_data, "HTML"),
            ),
            mock.patch(
                "cl.recap.tasks.replicate_recap_email_to_subdockets"
            ) as mock_replication,
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        # Subdockets replication shouldn't be called.
        mock_replication.assert_not_called()

        docket_entry = email_data["dockets"][0]["docket_entries"]
        docket_entry_query = DocketEntry.objects.filter(
            docket__pacer_case_id=docket_entry[0]["pacer_case_id"],
            entry_number=docket_entry[0]["document_number"],
        )
        self.assertEqual(await docket_entry_query.acount(), 1)

        # Only the main document is merged.
        de = await docket_entry_query.afirst()
        self.assertEqual(await de.recap_documents.all().acount(), 1)

        recap_documents = RECAPDocument.objects.all()
        self.assertEqual(
            await recap_documents.acount(),
            1,
            msg="Wrong number of RECAPDocuments.",
        )

        # An alert containing the main document sealed is sent.
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b"Hello World"),
            "OK",
        ),
    )
    @mock.patch(
        "cl.recap.tasks.get_attachment_page_by_url",
        return_value="<html>Sealed document</html>",
    )
    @mock.patch(
        "cl.recap.tasks.set_rd_sealed_status",
        side_effect=mock_method_set_rd_sealed_status,
    )
    async def test_replication_sealed_document_with_no_sealed_attachments(
        self,
        mock_set_rd_sealed_status,
        mock_get_attachment_page_by_url,
        mock_download_pdf_by_magic_number,
        mock_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
    ):
        """This test checks whether a document with attachments that is sealed
        on PACER are properly ingested when the attachment page is available.
        """

        de_1 = await sync_to_async(DocketEntryFactory)(
            docket=await sync_to_async(DocketFactory)(
                court=self.court_canb,
                case_name="Subdocket 1",
                docket_number="1:20-cv-01296",
                pacer_case_id="1309089",
            ),
            entry_number=1,
        )
        await sync_to_async(RECAPDocumentFactory)(
            docket_entry=de_1,
            pacer_doc_id="04505578698",
            document_number="1",
            is_sealed=True,
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        with (
            mock.patch(
                "cl.recap.tasks.get_data_from_att_report",
                side_effect=lambda x, y: self.att_data,
            ),
            mock.patch(
                "cl.recap.tasks.open_and_validate_email_notification",
                return_value=(self.email_data, "HTML"),
            ),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        dockets = Docket.objects.all()
        self.assertEqual(
            await dockets.acount(), 2, msg="Wrong number of Dockets."
        )

        docket_entry_query = DocketEntry.objects.all()
        self.assertEqual(
            await docket_entry_query.acount(),
            2,
            msg="Wrong number of Docket entries.",
        )

        # The main sealed document and one attachment should be ingested.
        all_rds = RECAPDocument.objects.all()
        self.assertEqual(await all_rds.acount(), 4)

        # Check RDs merged.
        main_rds = RECAPDocument.objects.filter(
            document_type=RECAPDocument.PACER_DOCUMENT
        )
        async for rd in main_rds:
            with self.subTest(rd=rd):
                self.assertEqual(
                    rd.is_sealed, True, msg="Document is not sealed."
                )

        att_doc = RECAPDocument.objects.filter(
            document_type=RECAPDocument.ATTACHMENT
        )
        self.assertEqual(
            await att_doc.acount(), 2, msg="Wrong number of Attachments."
        )
        async for att_rd in att_doc:
            with self.subTest(att_rd=att_rd):
                self.assertTrue(att_rd.filepath_local)
                self.assertTrue(att_rd.is_available)

        # An alert is sent.
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        return_value=(None, "Document not available from magic link."),
    )
    @mock.patch(
        "cl.recap.tasks.get_attachment_page_by_url",
        return_value="<html>Sealed document</html>",
    )
    async def test_replication_seal_document_att_page_available_sealed_attachments(
        self,
        mock_get_attachment_page_by_url,
        mock_download_pdf_by_magic_number,
        mock_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
    ):
        """This test checks whether a document with attachments that is sealed
        and the attachment page is also unavailable no replication is triggered.
        """

        de_1 = await sync_to_async(DocketEntryFactory)(
            docket=await sync_to_async(DocketFactory)(
                court=self.court_canb,
                case_name="Subdocket 1",
                docket_number="1:20-cv-01296",
                pacer_case_id="1309089",
            ),
            entry_number=1,
        )
        await sync_to_async(RECAPDocumentFactory)(
            docket_entry=de_1,
            pacer_doc_id="04505578698",
            document_number="1",
            is_sealed=True,
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        with (
            mock.patch(
                "cl.recap.tasks.get_data_from_att_report",
                side_effect=lambda x, y: self.att_data,
            ),
            mock.patch(
                "cl.recap.tasks.open_and_validate_email_notification",
                return_value=(self.email_data, "HTML"),
            ),
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        dockets = Docket.objects.all()
        self.assertEqual(
            await dockets.acount(), 2, msg="Wrong number of Dockets."
        )

        docket_entry_query = DocketEntry.objects.all()
        self.assertEqual(
            await docket_entry_query.acount(),
            2,
            msg="Wrong number of Docket entries.",
        )

        # The main sealed document and one attachment should be ingested.
        all_rds = RECAPDocument.objects.all()
        self.assertEqual(await all_rds.acount(), 4)

        # Check RDs merged.
        main_rds = RECAPDocument.objects.filter(
            document_type=RECAPDocument.PACER_DOCUMENT
        )
        async for rd in main_rds:
            with self.subTest(rd=rd):
                self.assertEqual(
                    rd.is_sealed, True, msg="Main documents are not sealed."
                )

        att_docs = RECAPDocument.objects.filter(
            document_type=RECAPDocument.ATTACHMENT
        )
        self.assertEqual(
            await att_docs.acount(), 2, msg="Wrong number of Attachments."
        )

        att_email = await att_docs.exclude(docket_entry=de_1).afirst()
        att_replicated = await att_docs.filter(docket_entry=de_1).afirst()
        self.assertTrue(att_email.is_sealed)
        self.assertFalse(att_replicated.is_sealed)

        # An alert is sent.
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        return_value=(None, "Failed to get docket entry"),
    )
    @mock.patch("cl.recap.tasks.fetch_attachment_data")
    @mock.patch("cl.recap.tasks.add_docket_entries")
    async def test_avoid_replication_for_sealed_entry_with_attachments(
        self,
        mock_add_docket_entries,
        mock_fetch_attachment_data,
        mock_download_pdf_by_magic_number,
        mock_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
    ):
        """This test checks if a docket entry is sealed on PACER subdockets
        replication is not triggered.
        """
        mock_docket_entry_sealed.return_value = True
        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=True,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[RECAPEmailDocketEntryDataFactory()],
                )
            ],
        )
        with (
            mock.patch(
                "cl.recap.tasks.open_and_validate_email_notification",
                return_value=(email_data, "HTML"),
            ),
            mock.patch(
                "cl.recap.tasks.replicate_recap_email_to_subdockets"
            ) as mock_replication,
        ):
            # Trigger a new recap.email notification from testing_1@recap.email
            # auto-subscription option enabled
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        # Subdockets replication shouldn't be called.
        mock_replication.assert_not_called()

        # the process_recap_email task returns before trying to add a new entry
        mock_add_docket_entries.assert_not_called()
        mock_fetch_attachment_data.assert_not_called()

        # check we didn't create a docket entry
        docket_entry_query = DocketEntry.objects.all()
        self.assertEqual(await docket_entry_query.acount(), 0)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        side_effect=lambda x: True,
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d, e: (
            MockResponse(200, b"Hello World"),
            "OK",
        ),
    )
    @mock.patch(
        "cl.recap.tasks.requests.get",
        side_effect=lambda *args, **kwargs: MockResponse(200, b"Att content."),
    )
    async def test_recap_email_avoid_replication_on_pdf_available(
        self,
        mock_att_request,
        mock_download_pdf,
        mock_cookie,
        mock_docket_entry_sealed,
        mock_pacer_court_accessible,
        mock_cookies,
        mock_bucket_open,
        mock_enqueue_alert,
    ):
        """Confirm that replication for RDs where the PDF is already available
        is omitted.
        """
        # Create two Subdockets and RDs no mentioned in the email notification.
        de_1 = await sync_to_async(DocketEntryFactory)(
            docket=await sync_to_async(DocketFactory)(
                court=self.court_canb,
                case_name="Subdocket 1",
                docket_number="1:20-cv-01296",
                pacer_case_id="1309089",
            ),
            entry_number=18,
        )
        # Make PDF available.
        await sync_to_async(RECAPDocumentFactory)(
            docket_entry=de_1,
            pacer_doc_id="85001321035",
            document_number="18",
            document_type=RECAPDocument.PACER_DOCUMENT,
            is_available=True,
            filepath_local=SimpleUploadedFile(
                "file.txt", b"file content more content"
            ),
        )

        email_data = RECAPEmailNotificationDataFactory(
            contains_attachments=False,
            appellate=False,
            dockets=[
                RECAPEmailDocketDataFactory(
                    docket_entries=[
                        RECAPEmailDocketEntryDataFactory(
                            pacer_doc_id="85001321035",
                            document_number="1",
                            pacer_case_id="1309088",
                        )
                    ],
                )
            ],
        )
        with mock.patch(
            "cl.recap.tasks.open_and_validate_email_notification",
            side_effect=lambda x, y: (
                email_data,
                "HTML",
            ),
        ):
            # Trigger a multi-nef recap.email notification from testing_1@recap.email
            await self.async_client.post(
                self.path, self.data_multi_canb, format="json"
            )

        # 2 RDs.
        recap_documents = RECAPDocument.objects.all()
        self.assertEqual(
            await recap_documents.acount(),
            2,
            msg="Wrong number of RECAPDocuments.",
        )
        # Every RECAPDocument should have a file stored at this point.
        async for rd in recap_documents:
            with self.subTest(rd=rd):
                self.assertTrue(rd.filepath_local)
                self.assertTrue(rd.is_available)
                self.assertEqual(rd.pacer_doc_id, "85001321035")

        # 1 DocketAlert email for the recap.email user should go out
        self.assertEqual(len(mail.outbox), 1)

        # Only one PQ for email PDF. No replication PQ is created.
        all_pqs_created = ProcessingQueue.objects.all().order_by("pk")
        self.assertEqual(
            await all_pqs_created.acount(),
            1,
            msg="Wrong number of ProcessingQueues.",
        )
