import json
import os
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from unittest import mock
from unittest.mock import ANY

import time_machine
from asgiref.sync import async_to_sync, sync_to_async
from dateutil.tz import tzutc
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.urls import reverse
from django.utils.timezone import now
from juriscraper.pacer import PacerRssFeed
from requests import ConnectionError

from cl.alerts.factories import DocketAlertFactory
from cl.alerts.models import DocketAlert
from cl.api.factories import (
    WEBHOOK_EVENT_STATUS,
    WebhookEventFactory,
    WebhookFactory,
)
from cl.api.management.commands.cl_retry_webhooks import (
    DAYS_TO_DELETE,
    HOURS_WEBHOOKS_CUT_OFF,
    execute_additional_tasks,
    retry_webhook_events,
)
from cl.api.models import Webhook, WebhookEvent, WebhookEventType
from cl.api.utils import get_next_webhook_retry_date
from cl.lib.pacer import is_pacer_court_accessible, lookup_and_save
from cl.lib.recap_utils import needs_ocr
from cl.lib.redis_utils import get_redis_interface
from cl.lib.storage import clobbering_get_name
from cl.lib.test_helpers import generate_docket_target_sources
from cl.people_db.models import (
    Attorney,
    AttorneyOrganizationAssociation,
    CriminalComplaint,
    CriminalCount,
    Party,
    PartyType,
    Role,
)
from cl.recap.api_serializers import PacerFetchQueueSerializer
from cl.recap.factories import (
    AppellateAttachmentFactory,
    AppellateAttachmentPageFactory,
    DocketDataFactory,
    DocketEntriesDataFactory,
    DocketEntryDataFactory,
    FjcIntegratedDatabaseFactory,
    MinuteDocketEntryDataFactory,
    PacerFetchQueueFactory,
    ProcessingQueueFactory,
    RECAPEmailDocketDataFactory,
    RECAPEmailDocketEntryDataFactory,
    RECAPEmailNotificationDataFactory,
)
from cl.recap.management.commands.import_idb import Command
from cl.recap.management.commands.remove_appellate_entries_with_long_numbers import (
    clean_up_duplicate_appellate_entries,
)
from cl.recap.management.commands.reprocess_recap_dockets import (
    extract_unextracted_rds_and_add_to_solr,
)
from cl.recap.mergers import (
    add_attorney,
    add_docket_entries,
    add_parties_and_attorneys,
    find_docket_object,
    get_order_of_docket,
    normalize_long_description,
    update_case_names,
    update_docket_metadata,
)
from cl.recap.models import (
    PROCESSING_STATUS,
    REQUEST_TYPE,
    UPLOAD_TYPE,
    EmailProcessingQueue,
    FjcIntegratedDatabase,
    PacerFetchQueue,
    ProcessingQueue,
)
from cl.recap.tasks import (
    create_or_merge_from_idb_chunk,
    do_pacer_fetch,
    fetch_pacer_doc_by_rd,
    get_and_copy_recap_attachment_docs,
    process_recap_acms_appellate_attachment,
    process_recap_acms_docket,
    process_recap_appellate_attachment,
    process_recap_appellate_docket,
    process_recap_attachment,
    process_recap_claims_register,
    process_recap_docket,
    process_recap_pdf,
    process_recap_zip,
)
from cl.recap_rss.tasks import merge_rss_feed_contents
from cl.scrapers.factories import PACERFreeDocumentRowFactory
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.models import (
    Court,
    Docket,
    DocketEntry,
    OriginatingCourtInformation,
    RECAPDocument,
)
from cl.tests import fakes
from cl.tests.cases import SimpleTestCase, TestCase
from cl.tests.utils import (
    AsyncAPIClient,
    MockACMSAttachmentPage,
    MockACMSDocketReport,
    MockResponse,
)
from cl.users.factories import (
    UserProfileWithParentsFactory,
    UserWithChildProfileFactory,
)


@mock.patch("cl.recap.views.process_recap_upload")
class RecapUploadsTest(TestCase):
    """Test the rest endpoint, but exclude the processing tasks."""

    @classmethod
    def setUpTestData(cls):
        CourtFactory(id="canb", jurisdiction="FB")
        cls.court = CourtFactory.create(jurisdiction="FD", in_use=True)
        cls.court_appellate = CourtFactory(
            id="ca9", jurisdiction="F", in_use=True
        )
        cls.ca2 = CourtFactory(id="ca2", jurisdiction="F", in_use=True)
        cls.att_data = AppellateAttachmentPageFactory(
            attachments=[
                AppellateAttachmentFactory(
                    pacer_doc_id="04505578698", attachment_number=1
                ),
                AppellateAttachmentFactory(
                    pacer_doc_id="04505578699", attachment_number=2
                ),
            ],
            pacer_doc_id="04505578698",
            pacer_case_id="104490",
        )
        cls.de_data = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    pacer_doc_id="04505578698",
                    document_number=1,
                )
            ],
        )

    def setUp(self) -> None:
        self.async_client = AsyncAPIClient()
        self.user = User.objects.get(username="recap")
        token = f"Token {self.user.auth_token.key}"
        self.async_client.credentials(HTTP_AUTHORIZATION=token)
        self.path = reverse("processingqueue-list", kwargs={"version": "v3"})
        self.f = SimpleUploadedFile("file.txt", b"file content more content")
        self.data = {
            "court": self.court.id,
            "pacer_case_id": "asdf",
            "pacer_doc_id": 24,
            "document_number": 1,
            "filepath_local": self.f,
            "upload_type": UPLOAD_TYPE.PDF,
        }

    async def test_uploading_a_pdf(self, mock):
        """Can we upload a document and have it be saved correctly?"""
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        self.assertEqual(j["court"], self.court.id)
        self.assertEqual(j["document_number"], 1)
        self.assertEqual(j["pacer_case_id"], "asdf")
        mock.assert_called()

    async def test_uploading_a_zip(self, mock):
        """Can we upload a zip?"""
        self.data.update({"upload_type": UPLOAD_TYPE.DOCUMENT_ZIP})
        del self.data["pacer_doc_id"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        mock.assert_called()

    async def test_uploading_a_docket(self, mock):
        """Can we upload a docket and have it be saved correctly?

        Note that this works fine even though we're not actually uploading a
        docket due to the mock.
        """
        self.data.update(
            {"upload_type": UPLOAD_TYPE.DOCKET, "document_number": ""}
        )
        del self.data["pacer_doc_id"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        path = reverse(
            "processingqueue-detail", kwargs={"version": "v3", "pk": j["id"]}
        )
        r = await self.async_client.get(path)
        self.assertEqual(r.status_code, HTTPStatus.OK)

    async def test_uploading_a_claims_registry_page(self, mock):
        """Can we upload claims registry data?"""
        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.CLAIMS_REGISTER,
                "document_number": "",
                "pacer_doc_id": "",
                "court": "canb",
            }
        )
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        mock.assert_called()

    async def test_uploading_an_attachment_page(self, mock):
        """Can we upload an attachment page and have it be saved correctly?"""
        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.ATTACHMENT_PAGE,
                "document_number": "",
            }
        )
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        path = reverse(
            "processingqueue-detail", kwargs={"version": "v3", "pk": j["id"]}
        )
        r = await self.async_client.get(path)
        self.assertEqual(r.status_code, HTTPStatus.OK)

    async def test_uploading_an_acms_attachment_page(self, mock):
        """Can we upload an ACMS attachment page and have it be saved correctly?"""
        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.ACMS_ATTACHMENT_PAGE,
                "document_number": "",
            }
        )
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        path = reverse(
            "processingqueue-detail", kwargs={"version": "v3", "pk": j["id"]}
        )
        r = await self.async_client.get(path)
        self.assertEqual(r.status_code, HTTPStatus.OK)

    async def test_numbers_in_docket_uploads_fail(self, mock):
        """Are invalid uploads denied?

        For example, if you're uploading a Docket, you shouldn't be providing a
        document number.
        """
        self.data["upload_type"] = UPLOAD_TYPE.DOCKET
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_district_court_in_appellate_upload_fails(self, mock):
        """If you send a district court to an appellate endpoint, does it
        fail?
        """
        self.data.update({"upload_type": UPLOAD_TYPE.APPELLATE_DOCKET})
        del self.data["pacer_doc_id"]
        del self.data["document_number"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_appellate_court_in_district_upload_fails(self, mock):
        """If you send appellate court info to a distric court, does it
        fail?
        """
        self.data.update(
            {"upload_type": UPLOAD_TYPE.DOCKET, "court": "scotus"}
        )
        del self.data["pacer_doc_id"]
        del self.data["document_number"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_string_for_document_number_fails(self, mock):
        self.data["document_number"] = "asdf"  # Not an int.
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_no_numbers_in_docket_uploads_work(self, mock):
        self.data["upload_type"] = UPLOAD_TYPE.DOCKET
        del self.data["pacer_doc_id"]
        del self.data["document_number"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

    async def test_pdf_without_pacer_case_id_works(self, mock):
        """Do we allow PDFs lacking a pacer_case_id value?"""
        del self.data["pacer_case_id"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

    async def test_uploading_non_ascii(self, mock):
        """Can we handle it if a client sends non-ascii strings?"""
        self.data["pacer_case_id"] = "☠☠☠"
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)
        mock.assert_called()

    async def test_disallowed_court(self, mock):
        """Do posts fail if a bad court is given?"""
        self.data["court"] = "ala"
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_fails_no_document(self, mock):
        """Do posts fail if the lack an attachment?"""
        del self.data["filepath_local"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_user_associated_properly(self, mock):
        """Does the user get associated after the upload?"""
        r = await self.async_client.post(self.path, self.data)
        j = json.loads(r.content)
        processing_request = await ProcessingQueue.objects.aget(pk=j["id"])
        self.assertEqual(self.user.pk, processing_request.uploader_id)
        mock.assert_called()

    async def test_ensure_no_users_in_response(self, mock):
        """Is all user information excluded from the processing queue?"""
        r = await self.async_client.post(self.path, self.data)
        j = json.loads(r.content)
        for bad_key in ["uploader", "user"]:
            with self.assertRaises(KeyError):
                # noinspection PyStatementEffect
                j[bad_key]
        mock.assert_called()

    async def test_uploading_a_case_query_page(self, mock):
        """Can we upload a docket iquery page and have it be saved correctly?

        Note that this works fine even though we're not actually uploading a
        docket due to the mock.
        """
        self.data.update(
            {"upload_type": UPLOAD_TYPE.CASE_QUERY_PAGE, "document_number": ""}
        )
        del self.data["pacer_doc_id"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        path = reverse(
            "processingqueue-detail", kwargs={"version": "v3", "pk": j["id"]}
        )
        r = await self.async_client.get(path)
        self.assertEqual(r.status_code, HTTPStatus.OK)

    async def test_uploading_an_appellate_case_query_page(self, mock):
        """Can we upload an appellate case query and have it be saved correctly?

        Note that this works fine even though we're not actually uploading a
        case query page due to the mock.
        """
        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.APPELLATE_CASE_QUERY_PAGE,
                "court": self.court_appellate.id,
            }
        )
        del self.data["pacer_doc_id"]
        del self.data["document_number"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        path = reverse(
            "processingqueue-detail", kwargs={"version": "v3", "pk": j["id"]}
        )
        r = await self.async_client.get(path)
        self.assertEqual(r.status_code, HTTPStatus.OK)

    async def test_uploading_an_appellate_attachment_page(self, mock):
        """Can we upload an appellate attachment page and have it be saved
        correctly?

        Note that this works fine even though we're not actually uploading a
        docket due to the mock.
        """

        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.APPELLATE_ATTACHMENT_PAGE,
                "court": self.court_appellate.id,
            }
        )
        del self.data["pacer_doc_id"]
        del self.data["document_number"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        path = reverse(
            "processingqueue-detail", kwargs={"version": "v3", "pk": j["id"]}
        )
        r = await self.async_client.get(path)
        self.assertEqual(r.status_code, HTTPStatus.OK)

    def test_processing_an_appellate_attachment_page(self, mock_upload):
        """Can we process an appellate attachment and transform the main recap
        document to an attachment correctly?

        Note that this works fine even though we're not actually uploading a
        docket due to the mock.
        """

        d = DocketFactory(
            source=Docket.RECAP,
            court=self.court_appellate,
            pacer_case_id="104490",
        )
        async_to_sync(add_docket_entries)(d, self.de_data["docket_entries"])
        pq = ProcessingQueue.objects.create(
            court=self.court_appellate,
            uploader=self.user,
            pacer_case_id="104490",
            upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE,
            filepath_local=self.f,
        )
        recap_documents = RECAPDocument.objects.all().order_by("date_created")

        # After adding 1 docket entry, it should only exist its main RD.
        self.assertEqual(recap_documents.count(), 1)
        main_rd = recap_documents[0]

        with mock.patch(
            "cl.recap.tasks.get_data_from_appellate_att_report",
            side_effect=lambda x, y: self.att_data,
        ):
            # Process the appellate attachment page containing 2 attachments.
            async_to_sync(process_recap_appellate_attachment)(pq.pk)

        # After adding attachments, it should only exist 2 RD attachments.
        self.assertEqual(recap_documents.count(), 2)

        # Confirm that the main RD is transformed into an attachment.
        main_attachment = RECAPDocument.objects.filter(pk=main_rd.pk)
        self.assertEqual(
            main_attachment[0].document_type, RECAPDocument.ATTACHMENT
        )
        self.assertEqual(
            main_attachment[0].description,
            self.att_data["attachments"][0]["description"],
        )

        pq_1 = ProcessingQueue.objects.create(
            court=self.court_appellate,
            uploader=self.user,
            pacer_case_id="104490",
            upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE,
            filepath_local=self.f,
        )
        with mock.patch(
            "cl.recap.tasks.get_data_from_appellate_att_report",
            side_effect=lambda x, y: self.att_data,
        ):
            async_to_sync(process_recap_appellate_attachment)(pq_1.pk)

        # Process the attachment page again, no new attachments should be added
        self.assertEqual(recap_documents.count(), 2)
        self.assertEqual(
            main_attachment[0].document_type, RECAPDocument.ATTACHMENT
        )
        self.assertEqual(
            main_attachment[0].description,
            self.att_data["attachments"][0]["description"],
        )

    def test_reprocess_appellate_docket_after_adding_attachments(
        self, mock_upload
    ):
        """Can we reprocess an appellate docket page after adding attachments
        and avoid creating the main recap document again?
        """

        d = DocketFactory(
            source=Docket.RECAP,
            court=self.court_appellate,
            pacer_case_id="104490",
        )
        # Merge docket entries
        async_to_sync(add_docket_entries)(d, self.de_data["docket_entries"])

        pq = ProcessingQueue.objects.create(
            court=self.court_appellate,
            uploader=self.user,
            pacer_case_id="104490",
            upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE,
            filepath_local=self.f,
        )

        recap_documents = RECAPDocument.objects.all().order_by("date_created")
        self.assertEqual(recap_documents.count(), 1)

        main_rd = recap_documents[0]

        with mock.patch(
            "cl.recap.tasks.get_data_from_appellate_att_report",
            side_effect=lambda x, y: self.att_data,
        ):
            async_to_sync(process_recap_appellate_attachment)(pq.pk)

        # Confirm attachments were added correctly.
        self.assertEqual(recap_documents.count(), 2)
        main_attachment = RECAPDocument.objects.filter(pk=main_rd.pk)
        self.assertEqual(
            main_attachment[0].document_type, RECAPDocument.ATTACHMENT
        )
        self.assertEqual(
            main_attachment[0].description,
            self.att_data["attachments"][0]["description"],
        )

        # Merge docket entries data again
        async_to_sync(add_docket_entries)(d, self.de_data["docket_entries"])

        # No new main recap document should be created
        self.assertEqual(recap_documents.count(), 2)
        self.assertEqual(
            main_attachment[0].document_type, RECAPDocument.ATTACHMENT
        )
        self.assertEqual(
            main_attachment[0].description,
            self.att_data["attachments"][0]["description"],
        )

    async def test_uploading_a_case_query_result_page(self, mock):
        """Can we upload a case query result page and have it be saved
        correctly?

        Note that this works fine even though we're not actually uploading a
        base case query advanced page due to the mock.
        """

        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.CASE_QUERY_RESULT_PAGE,
            }
        )
        del self.data["pacer_doc_id"]
        del self.data["pacer_case_id"]
        del self.data["document_number"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        path = reverse(
            "processingqueue-detail", kwargs={"version": "v3", "pk": j["id"]}
        )
        r = await self.async_client.get(path)
        self.assertEqual(r.status_code, HTTPStatus.OK)

    async def test_uploading_an_appellate_case_query_result_page(self, mock):
        """Can we upload an appellate case query result page and have it be
        saved correctly?

        Note that this works fine even though we're not actually uploading a
        case query page due to the mock.
        """
        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.APPELLATE_CASE_QUERY_RESULT_PAGE,
                "court": self.court_appellate.id,
            }
        )
        del self.data["pacer_case_id"]
        del self.data["pacer_doc_id"]
        del self.data["document_number"]
        r = await self.async_client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTPStatus.CREATED)

        j = json.loads(r.content)
        path = reverse(
            "processingqueue-detail", kwargs={"version": "v3", "pk": j["id"]}
        )
        r = await self.async_client.get(path)
        self.assertEqual(r.status_code, HTTPStatus.OK)

    async def test_recap_upload_validate_pacer_case_id(self, mock):
        """Can we properly validate the pacer_case_id doesn't contain a dash -?"""
        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.DOCKET,
                "document_number": "",
                "pacer_case_id": "12-2334",
            }
        )
        del self.data["pacer_doc_id"]
        r = await self.async_client.post(self.path, self.data)
        j = json.loads(r.content)
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
        self.assertIn(
            "PACER case ID can not contain a single (-); that looks like a docket number.",
            j["non_field_errors"][0],
        )

    async def test_recap_upload_validate_acms_pacer_case_id(self, mock):
        """Can we properly validate a pacer_case_id that is a GUIDs.?"""
        self.data.update(
            {
                "upload_type": UPLOAD_TYPE.ACMS_DOCKET_JSON,
                "document_number": "",
                "pacer_case_id": "34cacf7f-52d5-4d1f-b4f0-0542b429f674",
            }
        )
        del self.data["pacer_doc_id"]
        r = await self.async_client.post(self.path, self.data)
        j = json.loads(r.content)

        self.assertEqual(r.status_code, HTTPStatus.CREATED)

    def test_processing_an_acms_docket(self, mock_upload):
        """Can we process an ACMS docket report?

        Note that this works fine even though we're not actually uploading a
        docket due to the mock.
        """

        pq = ProcessingQueue.objects.create(
            court=self.ca2,
            uploader=self.user,
            pacer_case_id="9f5ae37f-c44e-4194-b075-3f8f028559c4",
            upload_type=UPLOAD_TYPE.ACMS_DOCKET_JSON,
            filepath_local=self.f,
        )
        with mock.patch(
            "cl.recap.tasks.ACMSDocketReport", MockACMSDocketReport
        ):
            # Process the ACMS docket report.
            async_to_sync(process_recap_acms_docket)(pq.pk)

        docket = Docket.objects.get(
            pacer_case_id="9f5ae37f-c44e-4194-b075-3f8f028559c4"
        )
        docket_entries = DocketEntry.objects.filter(docket=docket).order_by(
            "date_created"
        )

        # Confirm Docket entry and RECAPDocument is properly created.
        self.assertEqual(docket_entries.count(), 2)
        recap_documents = RECAPDocument.objects.all().order_by("date_created")
        self.assertEqual(recap_documents.count(), 2)
        self.assertEqual(
            recap_documents[0].pacer_doc_id,
            "46de54cd-3561-ee11-be6e-001dd804e087",
        )
        self.assertEqual(
            recap_documents[1].pacer_doc_id,
            "0d24550b-3761-ee11-be6e-001dd804e087",
        )

        # Confirm the naive date_filed is not converted.
        de_1 = DocketEntry.objects.get(docket__court=self.ca2, entry_number=1)
        self.assertEqual(de_1.date_filed, date(2023, 10, 2))
        self.assertEqual(de_1.time_filed, time(11, 17, 0))

        de_2 = DocketEntry.objects.get(docket__court=self.ca2, entry_number=2)
        self.assertEqual(de_2.date_filed, date(2023, 10, 2))
        self.assertEqual(de_2.time_filed, time(11, 20, 0))

    def test_processing_an_acms_attachment_page(self, mock_upload):
        d = DocketFactory(
            source=Docket.RECAP,
            court=self.ca2,
            pacer_case_id="9f5ae37f-c44e-4194-b075-3f8f028559c4",
        )
        de_data = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    pacer_doc_id="7fae3c58-1ced-ee11-904c-001dd83058b7",
                    document_number=22,
                )
            ],
        )
        async_to_sync(add_docket_entries)(d, de_data["docket_entries"])

        pq = ProcessingQueue.objects.create(
            court=self.ca2,
            uploader=self.user,
            pacer_case_id="9f5ae37f-c44e-4194-b075-3f8f028559c4",
            upload_type=UPLOAD_TYPE.ACMS_ATTACHMENT_PAGE,
            filepath_local=self.f,
        )

        recap_documents = RECAPDocument.objects.all().order_by("date_created")
        main_rd = recap_documents[0]

        # After adding 1 docket entry, it should only exist its main RD.
        self.assertEqual(recap_documents.count(), 1)
        with mock.patch(
            "cl.recap.tasks.ACMSAttachmentPage", MockACMSAttachmentPage
        ):
            # Process the acms attachment page containing 3 attachments.
            async_to_sync(process_recap_acms_appellate_attachment)(pq.pk)

        # After adding attachments, it should only exist 3 RD attachments.
        self.assertEqual(recap_documents.count(), 3)

        # Confirm that the main RD is transformed into an attachment.
        main_attachment = RECAPDocument.objects.filter(pk=main_rd.pk)
        self.assertEqual(
            main_attachment[0].document_type, RECAPDocument.ATTACHMENT
        )

        # Process the attachment page again, no new attachments should be added
        pq_1 = ProcessingQueue.objects.create(
            court=self.ca2,
            uploader=self.user,
            pacer_case_id="9f5ae37f-c44e-4194-b075-3f8f028559c4",
            upload_type=UPLOAD_TYPE.ACMS_ATTACHMENT_PAGE,
            filepath_local=self.f,
        )
        with mock.patch(
            "cl.recap.tasks.ACMSAttachmentPage", MockACMSAttachmentPage
        ):
            # Process the acms attachment page containing 3 attachments.
            async_to_sync(process_recap_acms_appellate_attachment)(pq_1.pk)

        self.assertEqual(recap_documents.count(), 3)
        self.assertEqual(
            main_attachment[0].document_type, RECAPDocument.ATTACHMENT
        )


@mock.patch("cl.recap.tasks.DocketReport", new=fakes.FakeDocketReport)
@mock.patch(
    "cl.recap.tasks.PossibleCaseNumberApi",
    new=fakes.FakePossibleCaseNumberApi,
)
@mock.patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
@mock.patch(
    "cl.recap.tasks.get_pacer_cookie_from_cache",
    side_effect=lambda x: True,
)
class RecapDocketFetchApiTest(TestCase):
    """Tests for the RECAP docket Fetch API

    The general approach here is to use mocks to separate out the serialization
    and API tests from the processing logic tests.
    """

    COURT = "scotus"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_profile = UserProfileWithParentsFactory()
        cls.docket = DocketFactory(
            source=Docket.RECAP,
            court_id=cls.COURT,
            pacer_case_id="104490",
            docket_number=fakes.DOCKET_NUMBER,
            case_name=fakes.CASE_NAME,
        )
        cls.docket_alert = DocketAlertFactory(
            docket=cls.docket, user=cls.user_profile.user
        )

    def setUp(self) -> None:
        self.user = User.objects.get(username="recap")

    def test_fetch_docket_by_docket_number(
        self, mock_court_accessible, mock_cookies
    ) -> None:
        """Can we do a simple fetch of a docket from PACER?"""
        fq = PacerFetchQueue.objects.create(
            user=self.user,
            request_type=REQUEST_TYPE.DOCKET,
            court_id=self.COURT,
            docket_number=fakes.DOCKET_NUMBER,
        )
        result = do_pacer_fetch(fq)
        # Wait for the chain to complete
        result.get()

        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.SUCCESSFUL)
        rds = RECAPDocument.objects.all()
        self.assertEqual(rds.count(), 1)

    def test_fetch_docket_by_pacer_case_id(
        self, mock_court_accessible, mock_cookies
    ) -> None:
        fq = PacerFetchQueue.objects.create(
            user=self.user,
            request_type=REQUEST_TYPE.DOCKET,
            court_id=self.COURT,
            pacer_case_id="104490",
        )
        result = do_pacer_fetch(fq)
        result.get()
        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.SUCCESSFUL)
        rds = RECAPDocument.objects.all()
        self.assertEqual(rds.count(), 1)

    def test_fetch_docket_by_docket_id(
        self, mock_court_accessible, mock_cookies
    ) -> None:
        fq = PacerFetchQueue.objects.create(
            user=self.user,
            request_type=REQUEST_TYPE.DOCKET,
            docket_id=self.docket.pk,
        )
        result = do_pacer_fetch(fq)
        result.get()
        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.SUCCESSFUL)
        rds = RECAPDocument.objects.all()
        self.assertEqual(rds.count(), 1)

    def test_fetch_docket_send_alert(
        self, mock_court_accessible, mock_cookies
    ) -> None:
        """
        Does a docket alert is triggered when fetching a docket from PACER?
        """
        fq = PacerFetchQueue.objects.create(
            user=self.user,
            request_type=REQUEST_TYPE.DOCKET,
            court_id=self.COURT,
            docket_number=fakes.DOCKET_NUMBER,
        )
        result = do_pacer_fetch(fq)
        # Wait for the chain to complete
        result.get()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(fakes.CASE_NAME, mail.outbox[0].subject)


@mock.patch("cl.recap.api_serializers.get_or_cache_pacer_cookies")
class RecapFetchApiSerializationTestCase(SimpleTestCase):
    @classmethod
    def setUp(cls) -> None:
        cls.user = UserWithChildProfileFactory.create()
        cls.fetch_attributes = {
            "user": cls.user,
            "docket_id": 1,
            "request_type": REQUEST_TYPE.DOCKET,
            "pacer_username": "johncofey",
            "pacer_password": "mrjangles",
        }
        cls.request = RequestFactory().request()
        cls.request.user = cls.user
        cls.court = CourtFactory(id="canb", jurisdiction="FB", in_use=True)

    def test_simple_request_serialization(self, mock) -> None:
        """Can we serialize a simple request?"""
        serialized_fq = PacerFetchQueueSerializer(
            data=self.fetch_attributes,
            context={"request": self.request},
        )
        self.assertTrue(
            serialized_fq.is_valid(),
            msg=f"Serializer did not validate. {serialized_fq.errors=}",
        )

        serialized_fq.save()

    def test_recap_fetch_validate_pacer_case_id(self, mock):
        """Can we properly validate the pacer_case_id doesn't contain a dash -?"""
        self.fetch_attributes.update(
            {"pacer_case_id": "12-2334", "court": "canb"}
        )
        del self.fetch_attributes["docket_id"]
        serialized_fq = PacerFetchQueueSerializer(
            data=self.fetch_attributes,
            context={"request": self.request},
        )
        serialized_fq.is_valid()
        self.assertIn(
            serialized_fq.errors["non_field_errors"][0],
            "PACER case ID can not contain a single (-); that looks like a docket number.",
        )

    def test_key_serialization_with_client_code(self, mock) -> None:
        """Does the API have the fields we expect?"""
        self.fetch_attributes["client_code"] = "pauledgecomb"

        serialized_fq = PacerFetchQueueSerializer(
            data=self.fetch_attributes,
            context={"request": self.request},
        )
        self.assertTrue(
            serialized_fq.is_valid(),
            msg=f"Serializer did not validate. {serialized_fq.errors=}",
        )
        serialized_fq.save()

        # Did the client code, user, and password get sent to the login function?
        mock.assert_called_with(
            self.user.pk,
            client_code=ANY,
            password=ANY,
            username=ANY,
        )

        self.assertCountEqual(
            serialized_fq.data.keys(),
            [
                "id",
                "court",
                "docket",
                "recap_document",
                "date_created",
                "date_modified",
                "date_completed",
                "status",
                "message",
                "pacer_case_id",
                "docket_number",
                "show_parties_and_counsel",
                "show_terminated_parties",
                "show_list_of_member_cases",
                "request_type",
                "de_date_start",
                "de_date_end",
                "de_number_start",
                "de_number_end",
            ],
        )


@mock.patch(
    "cl.corpus_importer.tasks.FreeOpinionReport",
    new=fakes.FakeFreeOpinionReport,
)
@mock.patch(
    "cl.recap.tasks.get_pacer_cookie_from_cache",
    return_value={"cookie": "foo"},
)
@mock.patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
class RecapPdfFetchApiTest(TestCase):
    """Can we fetch PDFs properly?"""

    fixtures = ["recap_docs.json"]

    def setUp(self) -> None:
        self.fq = PacerFetchQueue.objects.create(
            user=User.objects.get(username="recap"),
            request_type=REQUEST_TYPE.PDF,
            recap_document_id=1,
        )
        self.rd = self.fq.recap_document

    def tearDown(self) -> None:
        RECAPDocument.objects.update(is_available=True)
        self.rd.refresh_from_db()

    @mock.patch(
        "cl.lib.storage.get_name_by_incrementing",
        side_effect=clobbering_get_name,
    )
    def test_fetch_unavailable_pdf(
        self, mock_get_cookie, mock_get_name, mock_court_accessible
    ):
        """Can we do a simple fetch of a PDF from PACER?"""
        self.rd.is_available = False
        self.rd.save()

        self.assertFalse(self.rd.is_available)
        result = do_pacer_fetch(self.fq)
        result.get()
        self.fq.refresh_from_db()
        self.rd.refresh_from_db()
        self.assertEqual(self.fq.status, PROCESSING_STATUS.SUCCESSFUL)
        self.assertTrue(self.rd.is_available)

    def test_fetch_available_pdf(self, mock_get_cookie, mock_court_accessible):
        orig_date_modified = self.rd.date_modified

        response = fetch_pacer_doc_by_rd(self.rd.pk, self.fq.pk)
        self.assertIsNone(
            response,
            "Did not get None from fetch, indicating that the fetch did "
            "something, but it shouldn't have done anything when the doc is "
            "available.",
        )

        self.fq.refresh_from_db()
        self.rd.refresh_from_db()
        self.assertEqual(self.fq.status, PROCESSING_STATUS.SUCCESSFUL)
        self.assertEqual(
            orig_date_modified,
            self.rd.date_modified,
            msg="rd updated even though it was available.",
        )


@mock.patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
class RecapAttPageFetchApiTest(TestCase):
    fixtures = ["recap_docs.json"]

    def setUp(self) -> None:
        self.fq = PacerFetchQueue.objects.create(
            user=User.objects.get(username="recap"),
            request_type=REQUEST_TYPE.ATTACHMENT_PAGE,
            recap_document_id=1,
        )
        self.rd = self.fq.recap_document
        self.rd.pacer_doc_id = "17711118263"
        self.rd.save()

    def test_fetch_attachment_page_no_pacer_doc_id(
        self, mock_court_accessible
    ) -> None:
        """Can we do a simple fetch of an attachment page from PACER?"""
        self.rd.pacer_doc_id = ""
        self.rd.save()

        result = do_pacer_fetch(self.fq)
        result.get()

        self.fq.refresh_from_db()
        self.assertEqual(self.fq.status, PROCESSING_STATUS.NEEDS_INFO)

    def test_fetch_att_page_no_cookies(self, mock_court_accessible) -> None:
        result = do_pacer_fetch(self.fq)
        result.get()

        self.fq.refresh_from_db()
        self.assertEqual(self.fq.status, PROCESSING_STATUS.FAILED)
        self.assertIn("Unable to find cached cookies", self.fq.message)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        return_value={"pacer_cookie": "foo"},
    )
    @mock.patch(
        "cl.corpus_importer.tasks.AttachmentPage",
        new=fakes.FakeAttachmentPage,
    )
    @mock.patch(
        "cl.recap.mergers.AttachmentPage", new=fakes.FakeAttachmentPage
    )
    def test_fetch_att_page_all_systems_go(
        self, mock_get_cookies, mock_court_accessible
    ):
        result = do_pacer_fetch(self.fq)
        result.get()

        self.fq.refresh_from_db()
        self.assertEqual(self.fq.status, PROCESSING_STATUS.SUCCESSFUL)
        self.assertIn("Successfully completed fetch", self.fq.message)


class ProcessingQueueApiFilterTest(TestCase):
    def setUp(self) -> None:
        self.async_client = AsyncAPIClient()
        self.user = User.objects.get(username="recap")
        token = f"Token {self.user.auth_token.key}"
        self.async_client.credentials(HTTP_AUTHORIZATION=token)
        self.path = reverse("processingqueue-list", kwargs={"version": "v3"})
        # Set up for making PQ objects.
        filename = "file.pdf"
        file_content = b"file content more content"
        f = SimpleUploadedFile(filename, file_content)
        self.params = {
            "court_id": "scotus",
            "uploader": self.user,
            "pacer_case_id": "asdf",
            "pacer_doc_id": "asdf",
            "document_number": "1",
            "filepath_local": f,
            "status": PROCESSING_STATUS.ENQUEUED,
            "upload_type": UPLOAD_TYPE.PDF,
        }

    async def test_pq_filters(self) -> None:
        """Can we filter with the status and upload_type filters?"""
        # Create two PQ objects with different values.
        await ProcessingQueue.objects.acreate(**self.params)
        self.params["status"] = PROCESSING_STATUS.FAILED
        self.params["upload_type"] = UPLOAD_TYPE.ATTACHMENT_PAGE
        await ProcessingQueue.objects.acreate(**self.params)

        # Then try filtering.
        total_number_results = 2
        r = await self.async_client.get(self.path)
        j = json.loads(r.content)
        self.assertEqual(j["count"], total_number_results)

        total_awaiting_processing = 1
        r = await self.async_client.get(
            self.path, {"status": PROCESSING_STATUS.ENQUEUED}
        )
        j = json.loads(r.content)
        self.assertEqual(j["count"], total_awaiting_processing)

        total_pdfs = 1
        r = await self.async_client.get(
            self.path, {"upload_type": UPLOAD_TYPE.PDF}
        )
        j = json.loads(r.content)
        self.assertEqual(j["count"], total_pdfs)


def mock_bucket_open(message_id, r, read_file=False):
    """This function mocks bucket.open() method in order to call a
    recap.email notification fixture.
    """
    test_dir = Path(settings.INSTALL_ROOT) / "cl" / "recap" / "test_assets"
    if read_file:
        with open(test_dir / message_id, "rb") as file:
            return file.read()
    recap_mail_example = open(test_dir / message_id, "rb")
    return recap_mail_example


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
    @mock.patch(
        "cl.recap.tasks.get_or_cache_pacer_cookies",
        side_effect=lambda x, y, z: None,
    )
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


class DebugRecapUploadtest(TestCase):
    """Test uploads with debug set to True. Do these uploads avoid causing
    problems?
    """

    def setUp(self) -> None:
        self.user = User.objects.get(username="recap")
        self.pdf = SimpleUploadedFile("file.pdf", b"file content more content")
        test_dir = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets"
        )
        self.d_filename = "cand.html"
        d_path = os.path.join(test_dir, self.d_filename)
        with open(d_path, "rb") as f:
            self.docket = SimpleUploadedFile(self.d_filename, f.read())

        self.att_filename = "dcd_04505578698.html"
        att_path = os.path.join(test_dir, self.att_filename)
        with open(att_path, "rb") as f:
            self.att = SimpleUploadedFile(self.att_filename, f.read())

    def tearDown(self) -> None:
        ProcessingQueue.objects.all().delete()
        Docket.objects.all().delete()
        DocketEntry.objects.all().delete()
        RECAPDocument.objects.all().delete()

    @mock.patch("cl.recap.tasks.extract_recap_pdf_base")
    @mock.patch(
        "cl.lib.storage.get_name_by_incrementing",
        side_effect=clobbering_get_name,
    )
    def test_debug_does_not_create_rd(self, mock_extract, mock_get_name):
        """If debug is passed, do we avoid creating recap documents?"""
        docket = Docket.objects.create(
            source=0, court_id="scotus", pacer_case_id="asdf"
        )
        DocketEntry.objects.create(docket=docket, entry_number=1)
        pq = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id="asdf",
            pacer_doc_id="asdf",
            document_number="1",
            filepath_local=self.pdf,
            upload_type=UPLOAD_TYPE.PDF,
            debug=True,
        )
        async_to_sync(process_recap_pdf)(pq.pk)
        self.assertEqual(RECAPDocument.objects.count(), 0)
        mock_extract.assert_not_called()

    @mock.patch("cl.recap.mergers.add_attorney")
    def test_debug_does_not_create_docket(self, add_atty_mock):
        """If debug is passed, do we avoid creating a docket?"""
        pq = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id="asdf",
            filepath_local=self.docket,
            upload_type=UPLOAD_TYPE.DOCKET,
            debug=True,
        )
        async_to_sync(process_recap_docket)(pq.pk)
        self.assertEqual(Docket.objects.count(), 0)
        self.assertEqual(DocketEntry.objects.count(), 0)
        self.assertEqual(RECAPDocument.objects.count(), 0)

    @mock.patch("cl.recap.tasks.add_items_to_solr")
    def test_debug_does_not_create_recap_documents(self, mock):
        """If debug is passed, do we avoid creating recap documents?"""
        d = Docket.objects.create(
            source=0, court_id="scotus", pacer_case_id="asdf"
        )
        de = DocketEntry.objects.create(docket=d, entry_number=1)
        RECAPDocument.objects.create(
            docket_entry=de,
            document_number="1",
            pacer_doc_id="04505578698",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        pq = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE,
            filepath_local=self.att,
            debug=True,
        )
        async_to_sync(process_recap_attachment)(pq.pk)
        self.assertEqual(Docket.objects.count(), 1)
        self.assertEqual(DocketEntry.objects.count(), 1)
        self.assertEqual(RECAPDocument.objects.count(), 1)
        mock.assert_not_called()


class RecapPdfTaskTest(TestCase):
    def setUp(self) -> None:
        user = User.objects.get(username="recap")
        self.filename = "file.pdf"
        self.file_content = b"file content more content"
        f = SimpleUploadedFile(self.filename, self.file_content)
        sha1 = "dcfdea519bef494e9672b94a4a03a49d591e3762"  # <-- SHA1 for above
        with mock.patch(
            "cl.lib.storage.get_name_by_incrementing",
            side_effect=clobbering_get_name,
        ):
            self.pq = ProcessingQueue.objects.create(
                court_id="scotus",
                uploader=user,
                pacer_case_id="asdf",
                pacer_doc_id="asdf",
                document_number="1",
                filepath_local=f,
                upload_type=UPLOAD_TYPE.PDF,
            )
        self.docket = Docket.objects.create(
            source=Docket.DEFAULT, court_id="scotus", pacer_case_id="asdf"
        )
        self.de = DocketEntry.objects.create(
            docket=self.docket, entry_number=1
        )
        self.rd = RECAPDocument.objects.create(
            docket_entry=self.de,
            document_type=RECAPDocument.PACER_DOCUMENT,
            document_number=1,
            pacer_doc_id="asdf",
            sha1=sha1,
        )

        file_content_ocr = mock_bucket_open("ocr_pdf_test.pdf", "rb", True)
        self.filename_ocr = "file_ocr.pdf"
        self.file_content_ocr = file_content_ocr

    def tearDown(self) -> None:
        self.pq.filepath_local.delete()
        self.pq.delete()
        try:
            self.docket.delete()  # This cascades to self.de and self.rd
        except (Docket.DoesNotExist, AssertionError, ValueError):
            pass

    def test_pq_has_default_status(self) -> None:
        self.assertTrue(self.pq.status == PROCESSING_STATUS.ENQUEUED)

    @mock.patch("cl.recap.tasks.extract_recap_pdf_base")
    def test_recap_document_already_exists(self, mock_extract):
        """We already have everything"""
        # Update self.rd so it looks like it is already all good.
        self.rd.is_available = True
        cf = ContentFile(self.file_content)
        self.rd.filepath_local.save(self.filename, cf)

        rd = async_to_sync(process_recap_pdf)(self.pq.pk)

        # Did we avoid creating new objects?
        self.assertEqual(rd, self.rd)
        self.assertEqual(rd.docket_entry, self.de)
        self.assertEqual(rd.docket_entry.docket, self.docket)

        # Did we update pq appropriately?
        self.pq.refresh_from_db()
        self.assertEqual(self.pq.status, PROCESSING_STATUS.SUCCESSFUL)
        self.assertEqual(
            self.pq.error_message, "Successful upload! Nice work."
        )
        self.assertFalse(self.pq.filepath_local)
        self.assertEqual(self.pq.docket_id, self.docket.pk)
        self.assertEqual(self.pq.docket_entry_id, self.de.pk)
        self.assertEqual(self.pq.recap_document_id, self.rd.pk)

        # Did we correctly avoid running document extraction?
        mock_extract.assert_not_called()

    def test_only_the_docket_already_exists(self) -> None:
        """Never seen this docket entry before?

        Alas, we fail. In theory, this shouldn't happen.
        """
        self.de.delete()
        rd = async_to_sync(process_recap_pdf)(self.pq.pk)
        self.assertIsNone(rd)
        self.pq.refresh_from_db()
        # Confirm PQ values.
        self.assertEqual(self.pq.status, PROCESSING_STATUS.FAILED)
        self.assertIn("Unable to find docket entry", self.pq.error_message)
        self.assertEqual(self.pq.docket_id, None)
        self.assertEqual(self.pq.docket_entry_id, None)
        self.assertEqual(self.pq.recap_document_id, None)

    @mock.patch("cl.recap.tasks.extract_recap_pdf.si")
    def test_docket_and_docket_entry_already_exist(self, mock_extract):
        """What happens if we have everything but the PDF?

        This is the good case. We simply create a new item.
        """
        self.rd.delete()
        rd = async_to_sync(process_recap_pdf)(self.pq.pk)
        self.assertTrue(rd.is_available)
        self.assertTrue(rd.sha1)
        self.assertTrue(rd.filepath_local)
        self.assertIn("gov.uscourts.scotus.asdf.1.0", rd.filepath_local.name)

        mock_extract.assert_called_once()

        self.pq.refresh_from_db()
        self.assertEqual(self.pq.status, PROCESSING_STATUS.SUCCESSFUL)
        self.assertEqual(
            self.pq.error_message, "Successful upload! Nice work."
        )
        self.assertFalse(self.pq.filepath_local)

    def test_nothing_already_exists(self) -> None:
        """If a PDF is uploaded but there's no recap document and no docket do
        we fail?

        In practice, this shouldn't happen.
        """
        self.docket.delete()
        rd = async_to_sync(process_recap_pdf)(self.pq.pk)
        self.assertIsNone(rd)
        self.pq.refresh_from_db()
        # Confirm PQ values.
        self.assertEqual(self.pq.status, PROCESSING_STATUS.FAILED)
        self.assertIn("Unable to find docket", self.pq.error_message)
        self.assertEqual(self.pq.docket_id, None)
        self.assertEqual(self.pq.docket_entry_id, None)
        self.assertEqual(self.pq.recap_document_id, None)

    def test_ocr_extraction_recap_document(self):
        """Can we extract a recap document via OCR?"""
        cf = ContentFile(self.file_content_ocr)
        self.pq.filepath_local.save(self.filename_ocr, cf)
        rd = async_to_sync(process_recap_pdf)(self.pq.pk)
        recap_document = RECAPDocument.objects.get(pk=rd.pk)
        self.assertEqual(needs_ocr(recap_document.plain_text), False)
        self.assertEqual(recap_document.ocr_status, RECAPDocument.OCR_COMPLETE)


class RecapZipTaskTest(TestCase):
    """Do we do good things when people send us zips?"""

    test_dir = os.path.join(
        settings.INSTALL_ROOT, "cl", "recap", "test_assets"
    )

    def setUp(self) -> None:
        self.docket = Docket.objects.create(
            source=Docket.DEFAULT, court_id="scotus", pacer_case_id="asdf"
        )
        self.de = DocketEntry.objects.create(
            docket=self.docket, entry_number=12
        )
        doc12_sha1 = "130c52020a3d3ce7f0dbd46361b242493abf8b43"
        self.doc12 = RECAPDocument.objects.create(
            docket_entry=self.de,
            document_type=RECAPDocument.PACER_DOCUMENT,
            document_number=12,
            pacer_doc_id="asdf",
            sha1=doc12_sha1,
        )
        doc12_att1_sha1 = "0ce3a2df4f429f94a8f579eac4d47ba42dd66eac"
        self.doc12_att1 = RECAPDocument.objects.create(
            docket_entry=self.de,
            document_type=RECAPDocument.ATTACHMENT,
            document_number=12,
            attachment_number=1,
            pacer_doc_id="asdf",
            sha1=doc12_att1_sha1,
        )
        self.docs = [self.doc12, self.doc12_att1]

    @classmethod
    def setUpTestData(cls) -> None:
        filename = "1-20-cv-10189-FDS.zip"
        user = User.objects.get(username="recap")

        cls.pq = ProcessingQueueFactory.create(
            court_id="scotus",
            uploader=user,
            pacer_case_id="asdf",
            filepath_local__from_path=os.path.join(cls.test_dir, filename),
            filepath_local__filename="some.zip",
            upload_type=UPLOAD_TYPE.DOCUMENT_ZIP,
        )

    def tearDown(self) -> None:
        Docket.objects.all().delete()
        ProcessingQueue.objects.all().delete()

    @mock.patch("cl.recap.tasks.extract_recap_pdf.si")
    def test_simple_zip_upload(self, mock_extract):
        """Do we unpack the zip and process it's contents properly?"""
        # The original pq should be marked as complete with a good message.
        pq = ProcessingQueue.objects.get(id=self.pq.id)
        print(pq.__dict__)
        results = async_to_sync(process_recap_zip)(pq.pk)
        pq.refresh_from_db()
        self.assertEqual(
            pq.status,
            PROCESSING_STATUS.SUCCESSFUL,
            msg=f"Status should be {PROCESSING_STATUS.SUCCESSFUL}",
        )
        self.assertTrue(
            pq.error_message.startswith(
                "Successfully created ProcessingQueue objects: "
            ),
        )

        # A new pq should be created for each document
        expected_new_pq_count = 2
        actual_new_pq_count = len(results["new_pqs"])
        self.assertEqual(
            expected_new_pq_count,
            actual_new_pq_count,
            msg="Should have %s pq items in the DB, two from inside the zip, "
            "and one for the zip itself. Instead got %s."
            % (expected_new_pq_count, actual_new_pq_count),
        )

        # Wait for all the tasks to finish
        for task in results["tasks"]:
            task.wait(timeout=5, interval=0.25)

        # Are the PDF PQ's marked as successful?
        for new_pq in results["new_pqs"]:
            new_pq = ProcessingQueue.objects.get(pk=new_pq)
            self.assertEqual(new_pq.status, PROCESSING_STATUS.SUCCESSFUL)

        # Are the documents marked as available?
        for doc in self.docs:
            doc.refresh_from_db()
            self.assertTrue(
                doc.is_available,
                msg="Doc %s was not marked as available. This may mean that "
                "it was not processed properly by the PDF processor.",
            )

        # Was the mock called once per PDF in the zip?
        expected_call_count = len(results["new_pqs"])
        self.assertEqual(mock_extract.call_count, expected_call_count)


class RecapAddAttorneyTest(TestCase):
    def setUp(self) -> None:
        self.atty_org_name = "Lane Powell LLC"
        self.atty_phone = "907-276-2631"
        self.atty_email = "jamiesonb@lanepowell.com"
        self.atty_name = "Brewster H. Jamieson"
        self.atty = {
            "contact": "{org_name}\n"
            "301 W. Nothern Lights Blvd., Suite 301\n"
            "Anchorage, AK 99503-2648\n"
            "{phone}\n"
            "Fax: 907-276-2631\n"
            "Email: {email}\n".format(
                org_name=self.atty_org_name,
                phone=self.atty_phone,
                email=self.atty_email,
            ),
            "name": self.atty_name,
            "roles": [
                {"role": Role.ATTORNEY_LEAD, "date_action": None},
                {"role": Role.ATTORNEY_TO_BE_NOTICED, "date_action": None},
            ],
        }
        self.d = Docket.objects.create(
            source=0,
            court_id="scotus",
            pacer_case_id="asdf",
            date_filed=date(2017, 1, 1),
        )
        self.p = Party.objects.create(name="John Wesley Powell")

    def test_new_atty_to_db(self) -> None:
        """Can we add a new atty to the DB when none exist?"""
        a_pk = add_attorney(self.atty, self.p, self.d)
        a = Attorney.objects.get(pk=a_pk)
        self.assertEqual(a.contact_raw, self.atty["contact"])
        self.assertEqual(a.name, self.atty["name"])
        self.assertTrue(
            AttorneyOrganizationAssociation.objects.filter(
                attorney=a,
                attorney_organization__name=self.atty_org_name,
                docket=self.d,
            ).exists(),
            msg="Unable to find attorney organization association.",
        )
        self.assertEqual(a.email, self.atty_email)
        self.assertEqual(a.roles.all().count(), 2)

    def test_no_contact_info(self) -> None:
        """Do things work properly when we lack contact information?"""
        self.atty["contact"] = ""
        a_pk = add_attorney(self.atty, self.p, self.d)
        a = Attorney.objects.get(pk=a_pk)
        # No org info added because none provided:
        self.assertEqual(a.organizations.all().count(), 0)
        # But roles still get done.
        self.assertEqual(a.roles.all().count(), 2)

    def test_no_contact_info_another_already_exists(self) -> None:
        """If we lack contact info, and such a atty already exists (without
        contact info), do we properly consider them different people?
        """
        new_a = Attorney.objects.create(name=self.atty_name)
        self.atty["contact"] = ""
        a_pk = add_attorney(self.atty, self.p, self.d)
        a = Attorney.objects.get(pk=a_pk)
        self.assertNotEqual(a.pk, new_a.pk)

    def test_existing_roles_get_overwritten(self) -> None:
        """Do existing roles get overwritten with latest data?"""
        new_a = Attorney.objects.create(
            name=self.atty_name, email=self.atty_email
        )
        r = Role.objects.create(
            attorney=new_a, party=self.p, docket=self.d, role=Role.DISBARRED
        )
        a_pk = add_attorney(self.atty, self.p, self.d)
        a = Attorney.objects.get(pk=a_pk)
        self.assertEqual(new_a.pk, a.pk)
        roles = a.roles.all()
        self.assertEqual(roles.count(), 2)
        self.assertNotIn(r, roles)


class DocketCaseNameUpdateTest(SimpleTestCase):
    """Do we properly handle the nine cases of incoming case name
    information?
    """

    def setUp(self) -> None:
        self.d = Docket()
        self.v_case_name = "x v. y"
        self.new_case_name = "x v. z"
        self.uct = "Unknown Case Title"

    def test_case_name_updates(self) -> None:
        # Do we update if new is different and old has a value?
        self.d.case_name = self.v_case_name
        d = update_case_names(self.d, self.new_case_name)
        self.assertEqual(d.case_name, self.new_case_name)

        # Do we update if new has a value and old is UCT
        self.d.case_name = self.uct
        d = update_case_names(self.d, self.new_case_name)
        self.assertEqual(d.case_name, self.new_case_name)

        # new_v_old_blank_updates
        self.d.case_name = ""
        d = update_case_names(self.d, self.new_case_name)
        self.assertEqual(d.case_name, self.new_case_name)

        # new_uct_old_v_no_update
        self.d.case_name = self.v_case_name
        d = update_case_names(self.d, self.uct)
        self.assertEqual(d.case_name, self.v_case_name)

        # new_uct_old_uct_no_update
        self.d.case_name = self.uct
        d = update_case_names(self.d, self.uct)
        self.assertEqual(d.case_name, self.uct)

        # new_uct_old_blank_updates
        self.d.case_name = ""
        d = update_case_names(self.d, self.uct)
        self.assertEqual(d.case_name, self.uct)

        # new_blank_old_v_no_update
        self.d.case_name = self.v_case_name
        d = update_case_names(self.d, "")
        self.assertEqual(d.case_name, self.v_case_name)

        # new_blank_old_uct_no_update
        self.d.case_name = self.uct
        d = update_case_names(self.d, "")
        self.assertEqual(d.case_name, self.uct)

        # new_blank_old_blank_no_update
        self.d.case_name = ""
        d = update_case_names(self.d, "")
        self.assertEqual(d.case_name, "")


class TerminatedEntitiesTest(TestCase):
    """Do we handle things properly when new and old data have terminated
    entities (attorneys & parties)?

    There are four possibilities we need to handle properly:

     1. The scraped data has terminated entities (easy: update all
        existing and delete anything that's not touched).
     2. The scraped data lacks terminated entities and the current
        data lacks them too (easy: update as above).
     3. The scraped data lacks terminated entities and the current
        data has them (hard: update whatever is in common, keep
        terminated entities, disassociate the rest).

    """

    def setUp(self) -> None:
        # Docket: self.d has...
        #   Party: self.p via PartyType, which has...
        #     Attorney self.a via Role, and...
        #     Attorney self.extraneous_a2 via Role.
        #   Party: self.extraneous_p via PartyType, which has...
        #     Attorney: self.extraneous_a via Role.

        self.d = Docket.objects.create(
            source=0,
            court_id="scotus",
            pacer_case_id="asdf",
            date_filed=date(2017, 1, 1),
        )

        # One valid party and attorney.
        self.p = Party.objects.create(name="John Wesley Powell")
        PartyType.objects.create(docket=self.d, party=self.p, name="defendant")
        self.a = Attorney.objects.create(name="Roosevelt")
        Role.objects.create(
            docket=self.d,
            party=self.p,
            attorney=self.a,
            role=Role.ATTORNEY_LEAD,
        )

        # These guys should get disassociated whenever the new data comes in.
        self.extraneous_p = Party.objects.create(name="US Gubment")
        PartyType.objects.create(
            docket=self.d, party=self.extraneous_p, name="special intervenor"
        )
        self.extraneous_a = Attorney.objects.create(name="Matthew Lesko")
        Role.objects.create(
            docket=self.d,
            party=self.extraneous_p,
            attorney=self.extraneous_a,
            role=Role.ATTORNEY_LEAD,
        )

        # Extraneous attorney on a valid party. Should always be disassociated.
        # Typo:
        self.extraneous_a2 = Attorney.objects.create(name="Mathew Lesko")
        Role.objects.create(
            docket=self.d,
            party=self.p,
            attorney=self.extraneous_a2,
            role=Role.ATTORNEY_TO_BE_NOTICED,
        )

        self.new_powell_data = {
            "extra_info": "",
            "name": "John Wesley Powell",
            "type": "defendant",
            "attorneys": [
                {
                    "contact": "",
                    "name": "Roosevelt",
                    "roles": ["LEAD ATTORNEY"],
                }
            ],
            "date_terminated": None,
        }
        self.new_mccarthy_data = {
            "extra_info": "",
            "name": "Joseph McCarthy",
            "type": "commie",
            "attorneys": [],
            "date_terminated": date(1957, 5, 2),  # Historically accurate
        }
        self.new_party_data = [self.new_powell_data, self.new_mccarthy_data]

    def test_new_has_terminated_entities(self) -> None:
        """Do we update all existing data when scraped data has terminated
        entities?
        """
        add_parties_and_attorneys(self.d, self.new_party_data)
        # Docket should have two parties, Powell and McCarthy. This
        # implies that extraneous_p has been removed.
        self.assertEqual(self.d.parties.count(), 2)

        # Powell has an attorney. The rest are extraneous or don't have attys.
        role_count = Role.objects.filter(docket=self.d).count()
        self.assertEqual(role_count, 1)

    def test_new_lacks_terminated_entities_old_lacks_too(self) -> None:
        """Do we update all existing data when there aren't terminated entities
        at play?
        """
        self.new_mccarthy_data["date_terminated"] = None
        add_parties_and_attorneys(self.d, self.new_party_data)

        # Docket should have two parties, Powell and McCarthy. This
        # implies that extraneous_p has been removed.
        self.assertEqual(self.d.parties.count(), 2)

        # Powell has an attorney. The rest are extraneous or don't have attys.
        role_count = Role.objects.filter(docket=self.d).count()
        self.assertEqual(role_count, 1)

    def test_new_lacks_terminated_entities_old_has_them(self) -> None:
        """Do we update things properly when old has terminated parties, but
        new lacks them?

        Do we disassociate extraneous parties that aren't in the new data and
        aren't terminated?
        """
        # Add terminated attorney that's not in the new data.
        term_a = Attorney.objects.create(name="Robert Mueller")
        Role.objects.create(
            docket=self.d,
            attorney=term_a,
            party=self.p,
            role=Role.TERMINATED,
            date_action=date(2018, 3, 16),
        )

        # Add a terminated party that's not in the new data.
        term_p = Party.objects.create(name="Zainab Ahmad")
        PartyType.objects.create(
            docket=self.d,
            party=term_p,
            name="plaintiff",
            date_terminated=date(2018, 11, 4),
        )

        # Remove termination data from the new.
        self.new_mccarthy_data["date_terminated"] = None

        add_parties_and_attorneys(self.d, self.new_party_data)

        # Docket should have three parties, Powell and McCarthy from the new
        # data, and Ahmad from the old. This implies that extraneous_p has been
        # removed and that terminated parties have not.
        self.assertEqual(self.d.parties.count(), 3)

        # Powell now has has two attorneys, Robert Mueller and self.a. The rest
        # are extraneous or don't have attys.
        role_count = Role.objects.filter(docket=self.d).count()
        self.assertEqual(role_count, 2)

    def test_no_parties(self) -> None:
        """Do we keep the old parties when the new case has none?"""
        count_before = self.d.parties.count()
        add_parties_and_attorneys(self.d, [])
        self.assertEqual(self.d.parties.count(), count_before)


class RecapMinuteEntriesTest(TestCase):
    """Can we ingest minute and numberless entries properly?"""

    @staticmethod
    def make_path(filename):
        return os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets", filename
        )

    def make_pq(self, filename="azd.html", upload_type=UPLOAD_TYPE.DOCKET):
        """Make a simple pq object for processing"""
        path = self.make_path(filename)
        with open(path, "rb") as f:
            f = SimpleUploadedFile(filename, f.read())
        return ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id="asdf",
            filepath_local=f,
            upload_type=upload_type,
        )

    def setUp(self) -> None:
        self.user = User.objects.get(username="recap")

    def tearDown(self) -> None:
        pqs = ProcessingQueue.objects.all()
        for pq in pqs:
            pq.filepath_local.delete()
            pq.delete()
        Docket.objects.all().delete()

    def test_all_entries_ingested_without_duplicates(self) -> None:
        """Are all of the docket entries ingested?"""
        expected_entry_count = 23

        pq = self.make_pq()
        returned_data = async_to_sync(process_recap_docket)(pq.pk)
        d1 = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d1.docket_entries.count(), expected_entry_count)

        pq = self.make_pq()
        returned_data = async_to_sync(process_recap_docket)(pq.pk)
        d2 = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d1.pk, d2.pk)
        self.assertEqual(d2.docket_entries.count(), expected_entry_count)

    def test_multiple_numberless_entries_multiple_times(self) -> None:
        """Do we get the right number of entries when we add multiple
        numberless entries multiple times?
        """
        expected_entry_count = 25
        pq = self.make_pq("azd_multiple_unnumbered.html")
        returned_data = async_to_sync(process_recap_docket)(pq.pk)
        d1 = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d1.docket_entries.count(), expected_entry_count)

        pq = self.make_pq("azd_multiple_unnumbered.html")
        returned_data = async_to_sync(process_recap_docket)(pq.pk)
        d2 = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d1.pk, d2.pk)
        self.assertEqual(d2.docket_entries.count(), expected_entry_count)

    def test_appellate_cases_ok(self) -> None:
        """Do appellate cases get ordered/handled properly?"""
        expected_entry_count = 16
        pq = self.make_pq("ca1.html", upload_type=UPLOAD_TYPE.APPELLATE_DOCKET)
        returned_data = async_to_sync(process_recap_appellate_docket)(pq.pk)
        d1 = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d1.docket_entries.count(), expected_entry_count)

    def test_rss_feed_ingestion(self) -> None:
        """Can we ingest RSS feeds without creating duplicates?"""
        court_id = "scotus"
        rss_feed = PacerRssFeed(court_id)
        rss_feed.is_bankruptcy = True  # Needed because we say SCOTUS above.
        with open(self.make_path("rss_sample_unnumbered_mdb.xml"), "rb") as f:
            text = f.read().decode()
        rss_feed._parse_text(text)
        docket = rss_feed.data[0]
        d = async_to_sync(find_docket_object)(
            court_id, docket["pacer_case_id"], docket["docket_number"]
        )
        async_to_sync(update_docket_metadata)(d, docket)
        d.save()

        expected_count = 1
        async_to_sync(add_docket_entries)(d, docket["docket_entries"])
        self.assertEqual(d.docket_entries.count(), expected_count)
        async_to_sync(add_docket_entries)(d, docket["docket_entries"])
        self.assertEqual(d.docket_entries.count(), expected_count)

    def test_dhr_merges_separate_docket_entries(self) -> None:
        """Does the docket history report merge separate minute entries if
        one entry has a short description, and the other has a long
        description?
        """
        # Create two unnumbered docket entries, one with a short description
        # and one with a long description. Then see what happens when you try
        # to add a DHR result (it should merge them).
        short_desc = "Entry one short description"
        long_desc = "Entry one long desc"
        date_filed = date(2014, 11, 16)
        d = Docket.objects.create(source=0, court_id="scotus")
        de1 = DocketEntry.objects.create(
            docket=d,
            entry_number=None,
            description=long_desc,
            date_filed=date_filed,
        )
        RECAPDocument.objects.create(
            docket_entry=de1,
            document_number="",
            description="",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        de2 = DocketEntry.objects.create(
            docket=d, entry_number=None, description="", date_filed=date_filed
        )
        RECAPDocument.objects.create(
            docket_entry=de2,
            document_number="",
            description=short_desc,
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        # Add a docket entry that spans the two above. Same date, same short
        # and long description. This should trigger a merge.
        async_to_sync(add_docket_entries)(
            d,
            [
                {
                    "date_filed": date_filed,
                    "description": long_desc,
                    "document_number": None,
                    "pacer_doc_id": None,
                    "pacer_seq_no": None,
                    "short_description": short_desc,
                }
            ],
        )
        expected_item_count = 1
        self.assertEqual(d.docket_entries.count(), expected_item_count)

    @mock.patch("cl.recap_rss.tasks.enqueue_docket_alert")
    def test_appellate_rss_feed_ingestion(self, mock_enqueue_de) -> None:
        """Can we ingest Appellate RSS feeds?"""

        court_ca10 = CourtFactory(id="ca10", jurisdiction="F")
        rss_feed = PacerRssFeed(court_ca10.pk)
        with open(self.make_path("rss_ca10.xml"), "rb") as f:
            text = f.read().decode()
        rss_feed._parse_text(text)
        merge_rss_feed_contents(rss_feed.data, court_ca10.pk)

        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 3)
        for docket in dockets:
            self.assertEqual(docket.docket_entries.count(), 1)

    @mock.patch("cl.recap_rss.tasks.enqueue_docket_alert")
    def test_appellate_merge_rss_feed_with_case_id(
        self, mock_enqueue_de
    ) -> None:
        """Can we merge an Appellate RSS feeds into an existing docket with
        pacer_case_id?
        """
        court_ca10 = CourtFactory(id="ca10", jurisdiction="F")
        docket = DocketFactory(
            case_name="Navarette v. Horton, et al",
            docket_number="22-2127",
            court=court_ca10,
            source=Docket.RECAP,
            pacer_case_id="12524",
        )

        self.assertEqual(docket.docket_entries.count(), 0)
        rss_feed = PacerRssFeed(court_ca10.pk)
        with open(self.make_path("rss_ca10.xml"), "rb") as f:
            text = f.read().decode()
        rss_feed._parse_text(text)
        merge_rss_feed_contents(rss_feed.data, court_ca10.pk)
        docket.refresh_from_db()
        self.assertEqual(docket.docket_entries.count(), 1)
        self.assertEqual(docket.pacer_case_id, "12524")
        self.assertEqual(docket.docket_number, "22-2127")

    @mock.patch("cl.recap_rss.tasks.enqueue_docket_alert")
    def test_appellate_merge_rss_feed_no_case_id(
        self, mock_enqueue_de
    ) -> None:
        """Can we merge an Appellate RSS feeds into a docket with no
        pacer_case_id?
        """
        court_ca10 = CourtFactory(id="ca10", jurisdiction="F")
        docket = DocketFactory(
            case_name="Navarette v. Horton, et al",
            docket_number="22-2127",
            court=court_ca10,
            source=Docket.RECAP,
            pacer_case_id=None,
        )

        self.assertEqual(docket.docket_entries.count(), 0)
        rss_feed = PacerRssFeed(court_ca10.pk)
        with open(self.make_path("rss_ca10.xml"), "rb") as f:
            text = f.read().decode()
        rss_feed._parse_text(text)
        merge_rss_feed_contents(rss_feed.data, court_ca10.pk)
        docket.refresh_from_db()
        self.assertEqual(docket.docket_entries.count(), 1)
        self.assertEqual(docket.pacer_case_id, "")
        self.assertEqual(docket.docket_number, "22-2127")

    @mock.patch("cl.recap_rss.tasks.enqueue_docket_alert")
    def test_retain_existing_values_in_absent_rss_fields(
        self, mock_enqueue_de
    ) -> None:
        """Confirm that when 'assigned_to_str' and 'referred_to_str' fields
        are not present in an RSS Feed, pre-existing values in these fields are
        retained and not cleared.
        """
        court_ca10 = CourtFactory(id="ca10", jurisdiction="F")
        docket = DocketFactory(
            case_name="Navarette v. Horton, et al",
            docket_number="22-2127",
            court=court_ca10,
            source=Docket.RECAP,
            pacer_case_id=None,
            assigned_to_str="John Marshall",
            referred_to_str="Sophia Clinton",
        )

        self.assertEqual(docket.docket_entries.count(), 0)
        rss_feed = PacerRssFeed(court_ca10.pk)
        with open(self.make_path("rss_ca10.xml"), "rb") as f:
            text = f.read().decode()
        rss_feed._parse_text(text)
        merge_rss_feed_contents(rss_feed.data, court_ca10.pk)
        docket.refresh_from_db()
        self.assertEqual(docket.docket_entries.count(), 1)
        self.assertEqual(docket.assigned_to_str, "John Marshall")
        self.assertEqual(docket.referred_to_str, "Sophia Clinton")


class DescriptionCleanupTest(SimpleTestCase):
    def test_cleanup(self) -> None:
        # has_entered_date_at_end
        desc = "test (Entered: 01/01/2000)"
        docket_entry = {"description": desc}
        normalize_long_description(docket_entry)
        self.assertEqual(docket_entry["description"], "test")

        # has_entered_date_in_middle
        desc = "test (Entered: 01/01/2000) test"
        docket_entry = {"description": desc}
        normalize_long_description(docket_entry)
        self.assertEqual(docket_entry["description"], desc)

        # has_entered_date_in_middle_and_end
        desc = "test (Entered: 01/01/2000) and stuff (Entered: 01/01/2000)"
        docket_entry = {"description": desc}
        normalize_long_description(docket_entry)
        self.assertEqual(
            docket_entry["description"], "test (Entered: 01/01/2000) and stuff"
        )

        # has_no_entered_date
        desc = "test stuff"
        docket_entry = {"description": "test stuff"}
        normalize_long_description(docket_entry)
        self.assertEqual(docket_entry["description"], desc)

        # no_description
        docket_entry = {}
        normalize_long_description(docket_entry)
        self.assertEqual(docket_entry, {})

        # removing_brackets
        docket_entry = {"description": "test [10] stuff"}
        normalize_long_description(docket_entry)
        self.assertEqual(docket_entry["description"], "test 10 stuff")

        # only_remove_brackets_on_numbers
        desc = "test [asdf 10] stuff"
        docket_entry = {"description": desc}
        normalize_long_description(docket_entry)
        self.assertEqual(docket_entry["description"], desc)


class RecapDocketTaskTest(TestCase):

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="scotus", jurisdiction="F")

    def setUp(self) -> None:
        self.user = User.objects.get(username="recap")
        self.filename = "cand.html"
        path = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets", self.filename
        )
        with open(path, "rb") as f:
            f = SimpleUploadedFile(self.filename, f.read())
        self.pq = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id="asdf",
            filepath_local=f,
            upload_type=UPLOAD_TYPE.DOCKET,
        )

    def tearDown(self) -> None:
        self.pq.filepath_local.delete()
        self.pq.delete()
        Docket.objects.all().delete()

    def test_parsing_docket_does_not_exist(self) -> None:
        """Can we parse an HTML docket we have never seen before?"""
        returned_data = async_to_sync(process_recap_docket)(self.pq.pk)
        d = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d.source, Docket.RECAP)
        self.assertTrue(d.case_name)
        self.assertEqual(d.jury_demand, "None")
        # Confirm docket_id is associated to the PQ
        self.pq.refresh_from_db()
        self.assertEqual(self.pq.docket_id, d.pk)

    def test_parsing_docket_already_exists(self) -> None:
        """Can we parse an HTML docket for a docket we have in the DB?"""
        existing_d = Docket.objects.create(
            source=Docket.DEFAULT, pacer_case_id="asdf", court_id="scotus"
        )
        returned_data = async_to_sync(process_recap_docket)(self.pq.pk)
        d = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d.source, Docket.RECAP_AND_SCRAPER)
        self.assertTrue(d.case_name)
        self.assertEqual(existing_d.pacer_case_id, d.pacer_case_id)
        # Confirm docket_id is associated to the PQ
        self.pq.refresh_from_db()
        self.assertEqual(self.pq.docket_id, existing_d.pk)

    def test_add_recap_source(self) -> None:
        """Is the RECAP source properly added to a docket originally added from
        a different source?
        """

        non_recap_sources = generate_docket_target_sources(
            Docket.NON_RECAP_SOURCES(), Docket.RECAP
        )
        self.assertEqual(
            len(non_recap_sources),
            len(Docket.NON_RECAP_SOURCES()),
            msg="Was a new non-recap source added?",
        )
        docket = DocketFactory.create(
            source=Docket.DEFAULT, pacer_case_id="asdf", court_id=self.court.pk
        )

        def add_recap_source_and_save(docket_instance):
            docket_instance.add_recap_source()
            docket_instance.save()

        pacer_free_doc_row = PACERFreeDocumentRowFactory(
            court_id=self.court.pk, pacer_case_id=docket.pacer_case_id
        )
        pacer_free_doc_row.court = self.court
        delattr(pacer_free_doc_row, "id")
        tests = {
            "add_recap_source_test": lambda x: add_recap_source_and_save(x),
            "lookup_and_save_test": lambda x: lookup_and_save(
                pacer_free_doc_row
            ),
        }
        for test, method in tests.items():
            for source, expected_source in non_recap_sources.items():
                with self.subTest(
                    f"Testing {test} source {source} assigment.",
                    source=source,
                    expected_source=expected_source,
                ):
                    Docket.objects.filter(pk=docket.pk).update(
                        source=getattr(Docket, source)
                    )
                    docket.refresh_from_db()
                    method(docket)
                    docket.refresh_from_db()
                    self.assertEqual(
                        docket.source,
                        getattr(Docket, expected_source),
                        msg="The source does not match.",
                    )

    def test_add_idb_anon_2020_source(self) -> None:
        """Is the IDB and ANON_2020 source properly added to a docket
        originally added from a different source?
        """

        non_idb_sources = generate_docket_target_sources(
            Docket.NON_IDB_SOURCES(), Docket.IDB
        )

        non_anon_2020_sources = generate_docket_target_sources(
            Docket.NON_ANON_2020_SOURCES(), Docket.ANON_2020
        )

        self.assertEqual(
            len(non_idb_sources),
            len(Docket.NON_IDB_SOURCES()),
            msg="Was a new non-recap source added?",
        )

        self.assertEqual(
            len(non_anon_2020_sources),
            len(Docket.NON_ANON_2020_SOURCES()),
            msg="Was a new non-recap source added?",
        )

        docket = DocketFactory.create(
            source=Docket.DEFAULT, pacer_case_id="asdf", court_id=self.court.pk
        )

        def add_idb_source_and_save(docket_instance):
            docket_instance.add_idb_source()
            docket_instance.save()

        def add_anon_2020_source_and_save(docket_instance):
            docket_instance.add_anon_2020_source()
            docket_instance.save()

        pacer_free_doc_row = PACERFreeDocumentRowFactory(
            court_id=self.court.pk, pacer_case_id=docket.pacer_case_id
        )
        pacer_free_doc_row.court = self.court
        delattr(pacer_free_doc_row, "id")
        tests = {
            "add_idb_source_test": (
                non_idb_sources,
                lambda x: add_idb_source_and_save(x),
            ),
            "add_anon_2020_source_test": (
                non_anon_2020_sources,
                lambda x: add_anon_2020_source_and_save(x),
            ),
        }
        for test, test_assets in tests.items():
            for source, expected_source in test_assets[0].items():
                with self.subTest(
                    f"Testing {test} source {source} assigment.",
                    source=source,
                    expected_source=expected_source,
                ):
                    assign_source_method = test_assets[1]
                    Docket.objects.filter(pk=docket.pk).update(
                        source=getattr(Docket, source)
                    )
                    docket.refresh_from_db()
                    assign_source_method(docket)
                    docket.refresh_from_db()
                    self.assertEqual(
                        docket.source,
                        getattr(Docket, expected_source),
                        msg="The source does not match.",
                    )

    def test_docket_and_de_already_exist(self) -> None:
        """Can we parse if the docket and the docket entry already exist?"""
        existing_d = Docket.objects.create(
            source=Docket.DEFAULT, pacer_case_id="asdf", court_id="scotus"
        )
        existing_de = DocketEntry.objects.create(
            docket=existing_d, entry_number="1", date_filed=date(2008, 1, 1)
        )
        returned_data = async_to_sync(process_recap_docket)(self.pq.pk)
        d = Docket.objects.get(pk=returned_data["docket_pk"])
        de = d.docket_entries.get(pk=existing_de.pk)
        self.assertNotEqual(
            existing_de.description,
            de.description,
            msg="Description field did not get updated during import.",
        )
        self.assertTrue(
            de.recap_documents.filter(is_available=False).exists(),
            msg="Recap document didn't get created properly.",
        )
        self.assertTrue(
            d.docket_entries.filter(entry_number="2").exists(),
            msg="New docket entry didn't get created.",
        )

    @mock.patch(
        "cl.lib.storage.get_name_by_incrementing",
        side_effect=clobbering_get_name,
    )
    def test_orphan_documents_are_added(self, mock) -> None:
        """If there's a pq that exists but previously wasn't processed, do we
        clean it up after we finish adding the docket?
        """
        pq = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id="asdf",
            pacer_doc_id="03504231050",
            document_number="1",
            filepath_local=SimpleUploadedFile(
                "file.pdf", b"file content more content"
            ),
            upload_type=UPLOAD_TYPE.PDF,
            status=PROCESSING_STATUS.FAILED,
        )
        async_to_sync(process_recap_docket)(self.pq.pk)
        pq.refresh_from_db()
        self.assertEqual(pq.status, PROCESSING_STATUS.SUCCESSFUL)

    def test_avoid_overwriting_nature_of_suit_in_free_opinions(self) -> None:
        """Test avoid updating the nature_of_suit from FreeOpinionReport if
        the docket already has a nature_of_suit set, since this value doesn't
        change. See issue #3878.
        """

        test_cases = [
            ("810 copyright", "copyright"),
            ("", "social welfare"),
            ("", ""),
        ]
        d = DocketFactory.create(
            source=Docket.DEFAULT,
            pacer_case_id="12345",
            court_id=self.court.pk,
        )
        for initial_nature_of_suit, nature_of_suit_from_row in test_cases:
            with self.subTest(
                initial_nature_of_suit=initial_nature_of_suit,
                nature_of_suit_from_row=nature_of_suit_from_row,
            ):
                # Update Docket with or without nature_of_suit
                Docket.objects.filter(pk=d.pk).update(
                    nature_of_suit=initial_nature_of_suit
                )
                d.refresh_from_db()
                pacer_free_doc_row = PACERFreeDocumentRowFactory(
                    court_id=self.court.pk,
                    pacer_case_id=d.pacer_case_id,
                    nature_of_suit=nature_of_suit_from_row,
                )
                pacer_free_doc_row.court = self.court
                delattr(pacer_free_doc_row, "id")
                lookup_and_save(pacer_free_doc_row)
                d.refresh_from_db()
                self.assertEqual(
                    d.nature_of_suit,
                    (
                        nature_of_suit_from_row
                        if not initial_nature_of_suit
                        else initial_nature_of_suit
                    ),
                    msg="The nature_of_suit does not match.",
                )
        d.delete()

    def test_avoid_overwriting_nature_of_suit_in_update_docket_metadata(
        self,
    ) -> None:
        """Test avoid updating the nature_of_suit from update_docket_metadata
         if the docket already has a nature_of_suit set, since this value doesn't
        change. See issue #3878.
        """

        test_cases = [
            ("810 copyright", "copyright"),
            ("", "social welfare"),
            ("", ""),
        ]
        d = DocketFactory.create(
            source=Docket.DEFAULT,
            pacer_case_id="12345",
            court_id=self.court.pk,
        )
        for initial_nature_of_suit, incoming_nature_of_suit in test_cases:
            with self.subTest(
                initial_nature_of_suit=initial_nature_of_suit,
                incoming_nature_of_suit=incoming_nature_of_suit,
            ):
                # Update Docket with or without nature_of_suit
                Docket.objects.filter(pk=d.pk).update(
                    nature_of_suit=initial_nature_of_suit
                )
                docket_data = {
                    "case_name": d.case_name,
                    "docket_number": d.docket_number,
                    "nature_of_suit": incoming_nature_of_suit,
                }
                d.refresh_from_db()
                async_to_sync(update_docket_metadata)(d, docket_data)
                d.save()
                d.refresh_from_db()
                self.assertEqual(
                    d.nature_of_suit,
                    (
                        incoming_nature_of_suit
                        if not initial_nature_of_suit
                        else initial_nature_of_suit
                    ),
                    msg="The nature_of_suit does not match.",
                )
        d.delete()


@mock.patch("cl.recap.tasks.add_items_to_solr")
class RecapDocketAttachmentTaskTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        CourtFactory(id="cand", jurisdiction="FD")

    def setUp(self) -> None:
        self.user = User.objects.get(username="recap")
        self.filename = "cand_7.html"
        path = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets", self.filename
        )
        with open(path, "rb") as f:
            f = SimpleUploadedFile(self.filename, f.read())
        self.pq = ProcessingQueue.objects.create(
            court_id="cand",
            uploader=self.user,
            pacer_case_id="417880",
            filepath_local=f,
            upload_type=UPLOAD_TYPE.DOCKET,
        )

    def tearDown(self) -> None:
        self.pq.filepath_local.delete()
        self.pq.delete()
        Docket.objects.all().delete()
        RECAPDocument.objects.filter(
            document_type=RECAPDocument.ATTACHMENT,
        ).delete()

    def test_attachments_get_created(self, mock):
        """Do attachments get created if we have a RECAPDocument to match
        on?"""
        async_to_sync(process_recap_docket)(self.pq.pk)
        num_attachments_to_create = 3
        self.assertEqual(
            RECAPDocument.objects.filter(
                document_type=RECAPDocument.ATTACHMENT
            ).count(),
            num_attachments_to_create,
        )
        self.pq.refresh_from_db()
        self.assertEqual(self.pq.status, PROCESSING_STATUS.SUCCESSFUL)


class ClaimsRegistryTaskTest(TestCase):
    """Can we handle claims registry uploads?"""

    @classmethod
    def setUpTestData(cls):
        CourtFactory(id="canb", jurisdiction="FB")

    def setUp(self) -> None:
        self.user = User.objects.get(username="recap")
        self.filename = "claims_registry_njb.html"
        path = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets", self.filename
        )
        with open(path, "rb") as f:
            f = SimpleUploadedFile(self.filename, f.read())
        self.pq = ProcessingQueue.objects.create(
            court_id="canb",
            uploader=self.user,
            pacer_case_id="asdf",
            filepath_local=f,
            upload_type=UPLOAD_TYPE.CLAIMS_REGISTER,
        )

    def tearDown(self) -> None:
        self.pq.filepath_local.delete()
        self.pq.delete()
        Docket.objects.all().delete()

    def test_parsing_docket_does_not_exist(self) -> None:
        """Can we parse the claims registry when the docket doesn't exist?"""
        returned_data = async_to_sync(process_recap_claims_register)(
            self.pq.pk
        )
        d = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d.source, Docket.RECAP)
        self.assertTrue(d.case_name)
        expected_claims_count = 7
        self.assertEqual(d.claims.count(), expected_claims_count)

    def test_parsing_bad_data(self) -> None:
        """Can we handle it when there's no data to parse?"""
        filename = "claims_registry_empty.html"
        path = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets", filename
        )
        with open(path, "rb") as f:
            f = SimpleUploadedFile(filename, f.read())
        self.pq.filepath_local = f
        self.pq.save()

        returned_data = async_to_sync(process_recap_claims_register)(
            self.pq.pk
        )
        self.assertIsNone(returned_data)
        self.pq.refresh_from_db()
        self.assertTrue(self.pq.status, PROCESSING_STATUS.INVALID_CONTENT)


class RecapDocketAppellateTaskTest(TestCase):
    fixtures = ["hawaii_court.json"]

    def setUp(self) -> None:
        self.user = User.objects.get(username="recap")
        self.filename = "ca9.html"
        path = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets", self.filename
        )
        with open(path, "rb") as f:
            f = SimpleUploadedFile(self.filename, f.read())
        self.pq = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id="asdf",
            filepath_local=f,
            upload_type=UPLOAD_TYPE.APPELLATE_DOCKET,
        )

    def tearDown(self) -> None:
        self.pq.filepath_local.delete()
        self.pq.delete()
        Docket.objects.all().delete()
        OriginatingCourtInformation.objects.all().delete()

    def test_parsing_appellate_docket(self) -> None:
        """Can we parse an HTML docket we have never seen before?"""
        returned_data = async_to_sync(process_recap_appellate_docket)(
            self.pq.pk
        )
        d = Docket.objects.get(pk=returned_data["docket_pk"])
        self.assertEqual(d.source, Docket.RECAP)
        self.assertTrue(d.case_name)
        self.assertEqual(d.appeal_from_id, "hid")
        self.assertIn("Hawaii", d.appeal_from_str)

        # Test the originating court information
        og_info = d.originating_court_information
        self.assertTrue(og_info)
        self.assertIn("Gloria", og_info.court_reporter)
        self.assertEqual(og_info.date_judgment, date(2017, 3, 29))
        self.assertEqual(og_info.docket_number, "1:17-cv-00050")


class RecapCriminalDataUploadTaskTest(TestCase):
    """Can we handle it properly when criminal data is uploaded as part of
    a docket?
    """

    def setUp(self) -> None:
        self.user = User.objects.get(username="recap")
        self.filename = "cand_criminal.html"
        path = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets", self.filename
        )
        with open(path, "rb") as f:
            f = SimpleUploadedFile(self.filename, f.read())
        self.pq = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=self.user,
            pacer_case_id="asdf",
            filepath_local=f,
            upload_type=UPLOAD_TYPE.DOCKET,
        )

    def tearDown(self) -> None:
        self.pq.filepath_local.delete()
        self.pq.delete()
        Docket.objects.all().delete()

    def test_criminal_data_gets_created(self) -> None:
        """Does the criminal data appear in the DB properly when we process
        the docket?
        """
        async_to_sync(process_recap_docket)(self.pq.pk)
        expected_criminal_count_count = 1
        self.assertEqual(
            expected_criminal_count_count, CriminalCount.objects.count()
        )
        expected_criminal_complaint_count = 1
        self.assertEqual(
            expected_criminal_complaint_count,
            CriminalComplaint.objects.count(),
        )


@mock.patch("cl.recap.tasks.add_items_to_solr")
class RecapAttachmentPageTaskTest(TestCase):
    def setUp(self) -> None:
        user = User.objects.get(username="recap")
        self.filename = "cand.html"
        test_dir = os.path.join(
            settings.INSTALL_ROOT, "cl", "recap", "test_assets"
        )
        self.att_filename = "dcd_04505578698.html"
        att_path = os.path.join(test_dir, self.att_filename)
        with open(att_path, "rb") as f:
            self.att = SimpleUploadedFile(self.att_filename, f.read())
        self.d = Docket.objects.create(
            source=0, court_id="scotus", pacer_case_id="asdf"
        )
        self.de = DocketEntry.objects.create(docket=self.d, entry_number=1)
        RECAPDocument.objects.create(
            docket_entry=self.de,
            document_number="1",
            pacer_doc_id="04505578698",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        self.pq = ProcessingQueue.objects.create(
            court_id="scotus",
            uploader=user,
            upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE,
            filepath_local=self.att,
        )

    def tearDown(self) -> None:
        RECAPDocument.objects.filter(
            document_type=RECAPDocument.ATTACHMENT,
        ).delete()

    def test_attachments_get_created(self, mock):
        """Do attachments get created if we have a RECAPDocument to match
        on?"""
        async_to_sync(process_recap_attachment)(self.pq.pk)
        num_attachments_to_create = 3
        self.assertEqual(
            RECAPDocument.objects.filter(
                document_type=RECAPDocument.ATTACHMENT
            ).count(),
            num_attachments_to_create,
        )
        self.pq.refresh_from_db()
        self.assertEqual(self.pq.status, PROCESSING_STATUS.SUCCESSFUL)
        # Confirm docket_id and docket_entry_id are associated to the PQ
        self.assertEqual(self.pq.docket_id, self.d.pk)
        self.assertEqual(self.pq.docket_entry_id, self.de.pk)

    def test_no_rd_match(self, mock):
        """If there's no RECAPDocument to match on, do we fail gracefully?"""
        RECAPDocument.objects.all().delete()
        pq_status, msg, items = async_to_sync(process_recap_attachment)(
            self.pq.pk
        )
        self.assertEqual(
            msg, "Could not find docket to associate with attachment metadata"
        )
        self.pq.refresh_from_db()
        self.assertEqual(self.pq.status, PROCESSING_STATUS.FAILED)


class RecapUploadAuthenticationTest(TestCase):
    def setUp(self) -> None:
        self.async_client = AsyncAPIClient()
        self.path = reverse("processingqueue-list", kwargs={"version": "v3"})

    async def test_authentication(self) -> None:
        """Does POSTing and GETting fail when we send the wrong credentials?"""
        self.async_client.credentials(
            HTTP_AUTHORIZATION="Token asdf"
        )  # Junk token.
        r = await self.async_client.post(self.path)
        self.assertEqual(r.status_code, HTTPStatus.UNAUTHORIZED)

        r = await self.async_client.get(self.path)
        self.assertEqual(r.status_code, HTTPStatus.UNAUTHORIZED)

    async def test_no_credentials(self) -> None:
        """Does POSTing and GETting fail if we lack credentials?"""
        self.async_client.credentials()
        r = await self.async_client.post(self.path)
        self.assertEqual(r.status_code, HTTPStatus.UNAUTHORIZED)

        r = await self.async_client.get(self.path)
        self.assertEqual(r.status_code, HTTPStatus.UNAUTHORIZED)


class IdbImportTest(SimpleTestCase):
    """Assorted tests for the IDB importer."""

    cmd = Command()

    def test_csv_parsing(self) -> None:
        # https://www.ietf.org/rfc/rfc4180.txt
        qa = (
            # Satisfies RFC 4180 rules 1 & 2 (simple values)
            ("asdf\tasdf", {"1": "asdf", "2": "asdf"}),
            # RFC 4180 rule 5 (quotes around value)
            (
                'asdf\t"toyrus"\tasdf',
                {"1": "asdf", "2": "toyrus", "3": "asdf"},
            ),
            # RFC 4180 rule 6 (tab in the value)
            (
                'asdf\t"\ttoyrus"\tasdf',
                {"1": "asdf", "2": "toyrus", "3": "asdf"},
            ),
            # More tabs in the value.
            (
                'asdf\t"\tto\tyrus"\tasdf',
                {"1": "asdf", "2": "toyrus", "3": "asdf"},
            ),
            # MOAR tabs in the value.
            (
                'asdf\t"\tto\tyrus\t"\tasdf',
                {"1": "asdf", "2": "toyrus", "3": "asdf"},
            ),
            # RFC 4180 rule 7 (double quotes in the value)
            (
                'asdf\t"M/V ""Pheonix"""\tasdf',
                {"1": "asdf", "2": 'M/V "Pheonix"', "3": "asdf"},
            ),
        )
        for qa in qa:
            print(f"Testing CSV parser on: {qa[0]}")
            self.assertEqual(
                self.cmd.make_csv_row_dict(qa[0], ["1", "2", "3"]), qa[1]
            )


class IdbMergeTest(TestCase):
    """Can we successfully do heuristic matching"""

    @classmethod
    def setUpTestData(cls):
        cls.court = Court.objects.get(id="scotus")
        cls.docket_1 = DocketFactory(
            case_name="BARTON v. State Board for Rodgers Educator Certification",
            docket_number_core="0600078",
            docket_number="No. 06-11-00078-CV",
            court=cls.court,
        )
        cls.docket_2 = DocketFactory(
            case_name="Young v. State",
            docket_number_core="7101462",
            docket_number="No. 07-11-1462-CR",
            court=cls.court,
        )
        cls.fcj_1 = FjcIntegratedDatabaseFactory(
            district=cls.court,
            jurisdiction=3,
            nature_of_suit=440,
            docket_number="0600078",
        )
        cls.fcj_2 = FjcIntegratedDatabaseFactory(
            district=cls.court,
            jurisdiction=3,
            nature_of_suit=440,
            docket_number="7101462",
        )

    def tearDown(self) -> None:
        FjcIntegratedDatabase.objects.all().delete()

    def test_merge_from_idb_chunk(self) -> None:
        """Can we successfully merge a chunk of IDB data?"""

        self.assertEqual(Docket.objects.count(), 2)
        self.assertEqual(
            Docket.objects.get(id=self.docket_1.id).nature_of_suit, ""
        )
        create_or_merge_from_idb_chunk([self.fcj_1.id])
        self.assertEqual(Docket.objects.count(), 2)
        self.assertEqual(
            Docket.objects.get(id=self.docket_1.id).nature_of_suit,
            "440 Civil rights other",
        )

    def test_create_from_idb_chunk(self) -> None:
        # Can we ignore dockets with CR in them that otherwise match?
        self.assertEqual(Docket.objects.count(), 2)
        create_or_merge_from_idb_chunk([self.fcj_2.id])
        self.assertEqual(Docket.objects.count(), 3)


@mock.patch("cl.recap.tasks.enqueue_docket_alert", return_value=True)
@mock.patch(
    "cl.recap.tasks.RecapEmailSESStorage.open",
    side_effect=mock_bucket_open,
)
@mock.patch(
    "cl.recap.tasks.get_or_cache_pacer_cookies",
    side_effect=lambda x, y, z: None,
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
        cls.court_nyed = CourtFactory(id="nyed", jurisdiction="FB")
        cls.court_jpml = CourtFactory(id="jpml", jurisdiction="FS")
        cls.webhook = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        cls.webhook_2 = WebhookFactory(
            user=cls.user_profile_2.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=True,
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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

        # Two more webhooks should be triggered, one for testing_2@recap.email
        # and one for testing_1@recap.email
        webhooks_triggered = WebhookEvent.objects.filter()
        self.assertEqual(await webhooks_triggered.acount(), 3)

        async for webhook_sent in webhooks_triggered:
            self.assertEqual(
                webhook_sent.event_status, WEBHOOK_EVENT_STATUS.SUCCESSFUL
            )
        webhook_user_2 = WebhookEvent.objects.filter(webhook=self.webhook_2)
        self.assertEqual(await webhook_user_2.acount(), 2)
        webhook_user_1 = WebhookEvent.objects.filter(webhook=self.webhook)
        self.assertEqual(await webhook_user_1.acount(), 1)

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
    async def test_recap_email_sealed_entry_no_attachments(
        self,
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
    @mock.patch("cl.recap.tasks.get_and_merge_rd_attachments")
    @mock.patch("cl.recap.tasks.add_docket_entries")
    async def test_recap_email_sealed_entry_with_attachments(
        self,
        mock_add_docket_entries,
        mock_merge_rd_attachments,
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
        mock_merge_rd_attachments.assert_not_called()

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
        side_effect=lambda z, x, c, v, b, d: (None, ""),
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
            self.assertEqual(pq.status, PROCESSING_STATUS.SUCCESSFUL)
            self.assertFalse(pq.filepath_local)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        side_effect=lambda x: True,
    )
    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d: (
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
            self.assertEqual(pq.status, PROCESSING_STATUS.SUCCESSFUL)
            self.assertFalse(pq.filepath_local)


class TestRecapDocumentsExtractContentCommand(TestCase):
    """Test extraction for missed recap documents that need content
    extraction.
    """

    def setUp(self) -> None:
        d = Docket.objects.create(
            source=0, court_id="scotus", pacer_case_id="asdf"
        )
        self.de = DocketEntry.objects.create(docket=d, entry_number=1)
        self.user = User.objects.get(username="recap")
        file_content = mock_bucket_open(
            "gov.uscourts.ca1.12-2209.00106475093.0.pdf", "rb", True
        )
        self.filename = "file_2.pdf"
        self.file_content = file_content

    def test_extract_missed_recap_documents(self):
        """Can we extract only recap documents that need content extraction?"""

        # RD is_available and has a valid PDF, needs extraction.
        rd = RECAPDocument.objects.create(
            docket_entry=self.de,
            document_number="1",
            pacer_doc_id="04505578698",
            document_type=RECAPDocument.PACER_DOCUMENT,
            is_available=True,
        )
        cf = ContentFile(self.file_content)
        rd.filepath_local.save(self.filename, cf)

        # RD is_available, has a valid PDF, only document header extracted,
        # needs extraction using OCR.
        rd_2 = RECAPDocument.objects.create(
            docket_entry=self.de,
            document_number="2",
            pacer_doc_id="04505578698",
            document_type=RECAPDocument.PACER_DOCUMENT,
            is_available=True,
            plain_text="Appellate Case: 21-1298     Document: 42     Page: 1    Date Filed: 08/31/2022",
            ocr_status=RECAPDocument.OCR_NEEDED,
        )
        cf = ContentFile(self.file_content)
        rd_2.filepath_local.save(self.filename, cf)

        # RD doesn't have a valid PDF. Don't need extraction.
        RECAPDocument.objects.create(
            docket_entry=self.de,
            document_number="3",
            pacer_doc_id="04505578699",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        self.assertEqual(RECAPDocument.objects.count(), 3)
        rd_needs_extraction = [
            x.pk
            for x in RECAPDocument.objects.all()
            if x.needs_extraction and needs_ocr(x.plain_text)
        ]
        self.assertEqual(len(rd_needs_extraction), 2)

        extract_unextracted_rds_and_add_to_solr("celery")

        rd_needs_extraction_after = [
            x.pk
            for x in RECAPDocument.objects.all()
            if x.needs_extraction and needs_ocr(x.plain_text)
        ]
        self.assertEqual(len(rd_needs_extraction_after), 0)

    @mock.patch(
        "django.db.models.fields.files.FieldFile.open",
        side_effect=lambda mode: exec("raise FileNotFoundError"),
    )
    def test_clean_up_recap_document_file(self, mock_open):
        """Can we clean up the recap document file-related fields after a
        failed extraction due to a missing file in storage?"""

        # RD is_available and has a valid PDF, needs extraction.
        date_upload = datetime.now(timezone.utc)
        RECAPDocument.objects.create(
            docket_entry=self.de,
            document_number="1",
            sha1="asdfasdfasdfasdfasdfasddf",
            pacer_doc_id="04505578698",
            document_type=RECAPDocument.PACER_DOCUMENT,
            is_available=True,
            date_upload=date_upload,
            file_size=320,
            page_count=10,
        )
        cf = ContentFile(self.file_content)
        rd = RECAPDocument.objects.all()
        rd[0].filepath_local.save(self.filename, cf)

        self.assertEqual(rd[0].is_available, True)
        self.assertEqual(rd[0].file_size, 320)
        self.assertEqual(rd[0].sha1, "asdfasdfasdfasdfasdfasddf")
        self.assertEqual(rd[0].date_upload, date_upload)

        extract_unextracted_rds_and_add_to_solr("celery")
        # File related fields should be cleaned up after the failed extraction.
        self.assertEqual(rd[0].is_available, False)
        self.assertEqual(rd[0].file_size, None)
        self.assertEqual(rd[0].sha1, "")
        self.assertEqual(rd[0].date_upload, None)


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
    side_effect=lambda x, y, z: "Cookie",
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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
        side_effect=lambda z, x, c, v, b, d: (
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


@mock.patch("cl.lib.pacer.socket.gethostbyname", return_value="127.0.0.1")
class CheckCourtConnectivityTest(TestCase):
    """Test the is_pacer_court_accessible method."""

    def setUp(self) -> None:
        self.court_id = "alnb"
        self.r = get_redis_interface("CACHE")
        key = self.r.keys(f"status:pacer:court.{self.court_id}:ip.127.0.0.1")
        if key:
            self.r.delete(*key)

    @mock.patch(
        "cl.lib.pacer.check_pacer_court_connectivity",
        side_effect=lambda x: {
            "connection_ok": True,
            "status_code": 200,
            "date_time": datetime.now(timezone.utc),
        },
    )
    def test_is_pacer_court_accessible_pass(
        self, mock_get_ip, mock_check_court
    ):
        court_status = is_pacer_court_accessible(self.court_id)
        self.assertEqual(court_status, True)

    @mock.patch(
        "cl.lib.pacer.check_pacer_court_connectivity",
        side_effect=lambda x: {
            "connection_ok": False,
            "status_code": 403,
            "date_time": datetime.now(timezone.utc),
        },
    )
    def test_is_pacer_court_accessible_fails(
        self, mock_get_ip, mock_check_court
    ):
        court_status = is_pacer_court_accessible(self.court_id)
        self.assertEqual(court_status, False)


@mock.patch("cl.recap.tasks.enqueue_docket_alert", return_value=True)
@mock.patch(
    "cl.recap.tasks.RecapEmailSESStorage.open",
    side_effect=mock_bucket_open,
)
@mock.patch(
    "cl.recap.tasks.get_or_cache_pacer_cookies",
    side_effect=lambda x, y, z: None,
)
@mock.patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
@mock.patch(
    "cl.corpus_importer.tasks.get_document_number_from_confirmation_page",
    side_effect=lambda z, x: "011112443447",
)
@mock.patch(
    "cl.recap.tasks.is_docket_entry_sealed",
    return_value=False,
)
class WebhooksRetries(TestCase):
    """Test WebhookEvents retries"""

    @classmethod
    def setUpTestData(cls):
        cls.user_profile = UserProfileWithParentsFactory()
        cls.user_profile_2 = UserProfileWithParentsFactory()
        cls.court_nda = CourtFactory(id="ca9", jurisdiction="F")
        cls.court_nyed = CourtFactory(id="nyed", jurisdiction="FB")
        cls.webhook = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        cls.webhook_disabled = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=False,
        )
        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "recap" / "test_assets"
        with (
            open(
                test_dir / "recap_mail_custom_receipt_4.json",
                encoding="utf-8",
            ) as file_4,
            open(
                test_dir / "recap_mail_custom_receipt_nda.json",
                encoding="utf-8",
            ) as file_5,
        ):
            recap_mail_receipt_4 = json.load(file_4)
            recap_mail_receipt_nda = json.load(file_5)

        cls.data_nef_att = {
            "court": cls.court_nyed.id,
            "mail": recap_mail_receipt_4["mail"],
            "receipt": recap_mail_receipt_4["receipt"],
        }
        cls.data_nda = {
            "court": cls.court_nda.id,
            "mail": recap_mail_receipt_nda["mail"],
            "receipt": recap_mail_receipt_nda["receipt"],
        }

        cls.file_stream = ContentFile("OK")
        cls.file_stream_error = ContentFile("ERROR")

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

        self.r = get_redis_interface("CACHE")

    @classmethod
    def restart_webhook_executed(cls):
        r = get_redis_interface("CACHE")
        key = r.keys("daemon:webhooks:executed")
        if key:
            r.delete(*key)

    def test_get_next_webhook_retry_date(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """Verifies if the WebhookEvent next retry date is computed properly
        based on the exponential backoff retry policy defined in cl.api.utils
        get_next_webhook_retry_date.
        """

        fake_now = now()
        # Run tests for each possible try counter and expected elapsed time
        # (try_counter, elapsed_time_minutes)
        elapsed_times = [
            (1, 3),
            (2, 12),
            (3, 39),
            (4, 120),
            (5, 363),
            (6, 1092),
            (7, 3279),
        ]
        next_fake_time = fake_now
        for count, elapsed in elapsed_times:
            with time_machine.travel(next_fake_time, tick=False):
                retry_counter = count - 1
                expected_next_retry_date = fake_now + timedelta(
                    minutes=elapsed
                )
                next_retry_date = get_next_webhook_retry_date(retry_counter)
                self.assertEqual(next_retry_date, expected_next_retry_date)
                next_fake_time = next_retry_date

    def test_retry_webhook_disabled(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test checks if WebhookEvent that its parent Webhook is disabled
        it won't be retried.
        """
        fake_now = now()
        webhook_e1 = WebhookEventFactory(
            webhook=self.webhook_disabled,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            # Try to retry on the exact time, 3 minutes later.
            next_retry_date = fake_now + timedelta(minutes=3)
            with time_machine.travel(next_retry_date, tick=False):
                with mock.patch("cl.api.webhooks.send_webhook_event"):
                    # webhook_e1 shouldn't be retried since its parent webhook
                    # is disabled.
                    retried_webhooks = retry_webhook_events()
                    self.assertEqual(retried_webhooks, 0)

    def test_retry_webhook_events(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test checks if only a WebhookEvent in ENQUEUED_RETRY status and
        if its next_retry_date is equal to or lower than now can be retried.
        """
        fake_now = now()
        webhook_e1 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        webhook_e1_debug = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            next_retry_date=fake_now + timedelta(minutes=3),
            debug=True,
        )
        webhook_e2 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_2'}",
            event_status=WEBHOOK_EVENT_STATUS.SUCCESSFUL,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        webhook_e3 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_3'}",
            event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        webhook_e4 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_4'}",
            event_status=WEBHOOK_EVENT_STATUS.FAILED,
            next_retry_date=fake_now + timedelta(minutes=3),
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, raw=self.file_stream
            ),
        ):
            next_retry_date = fake_now + timedelta(minutes=1)
            with time_machine.travel(next_retry_date, tick=False):
                with mock.patch(
                    "cl.api.management.commands.cl_retry_webhooks.send_webhook_event"
                ):
                    webhooks_to_retry = retry_webhook_events()
                    # No webhooks events should be retried since it's no time.
                    self.assertEqual(webhooks_to_retry, 0)

            # Try to retry on the exact time, 3 minutes later.
            next_retry_date = fake_now + timedelta(minutes=3)
            with time_machine.travel(next_retry_date, tick=False):
                with mock.patch(
                    "cl.api.management.commands.cl_retry_webhooks.send_webhook_event"
                ):
                    # Only webhook_e1 should be retried.
                    webhooks_to_retry = retry_webhook_events()
                    self.assertEqual(webhooks_to_retry, 1)

            # Try to retry 5 minutes later.
            next_retry_date = fake_now + timedelta(minutes=5)
            with time_machine.travel(next_retry_date, tick=False):
                with mock.patch(
                    "cl.api.management.commands.cl_retry_webhooks.send_webhook_event"
                ):
                    # Only webhook_e1 should be retried.
                    webhooks_to_retry = retry_webhook_events()
                    self.assertEqual(webhooks_to_retry, 1)

            # Try to retry 10 hours later.
            next_retry_date = fake_now + timedelta(hours=10)
            with time_machine.travel(next_retry_date, tick=False):
                with mock.patch(
                    "cl.api.management.commands.cl_retry_webhooks.send_webhook_event"
                ):
                    webhooks_to_retry = retry_webhook_events()
                    self.assertEqual(webhooks_to_retry, 1)

            webhook_e1_compare = WebhookEvent.objects.filter(pk=webhook_e1.id)
            # Retry without mocking send_webhook_event
            next_retry_date = fake_now + timedelta(minutes=10)
            with time_machine.travel(next_retry_date, tick=False):
                webhooks_to_retry = retry_webhook_events()
                self.assertEqual(webhooks_to_retry, 1)
                self.assertEqual(
                    webhook_e1_compare[0].event_status,
                    WEBHOOK_EVENT_STATUS.SUCCESSFUL,
                )
                self.assertEqual(webhook_e1_compare[0].status_code, 200)

    def test_webhook_response_status_codes(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """This test checks if a WebhookEvent is properly considered for retry
        or marked as successful based on the received HTTP status code.
        """

        fake_now = now()
        webhook_e1 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        status_codes_tests = [
            (100, WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY),
            (200, WEBHOOK_EVENT_STATUS.SUCCESSFUL),
            (300, WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY),
            (400, WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY),
            (500, WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY),
        ]
        webhook_e1_compare = WebhookEvent.objects.filter(pk=webhook_e1.id)
        for status_code, expected_event_status in status_codes_tests:
            with mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    status_code, raw=self.file_stream
                ),
            ):
                next_retry_date = fake_now + timedelta(minutes=3)
                with time_machine.travel(next_retry_date, tick=False):
                    webhooks_to_retry = retry_webhook_events()
                    self.assertEqual(webhooks_to_retry, 1)
                    self.assertEqual(
                        webhook_e1_compare[0].event_status,
                        expected_event_status,
                    )
                    # Restore webhook event to test the remaining options
                    webhook_e1_compare.update(
                        next_retry_date=webhook_e1.next_retry_date,
                        event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                    )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d: (None, ""),
    )
    async def test_update_webhook_after_http_error(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
        mock_download_pacer_pdf_by_rd,
    ):
        """This test verifies if a WebhookEvent is properly enqueued for retry
        after receiving an HttpResponse with a failure status code.
        """
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                500,
                raw=self.file_stream_error,
                reason="500 Server Error",
                url="https://example.com",
            ),
        ):
            fake_now_0 = now()
            with time_machine.travel(fake_now_0, tick=False):
                # Trigger a new recap.email notification from testing_1@recap.email
                # auto-subscription option enabled
                await self.async_client.post(
                    self.path, self.data_nda, format="json"
                )

                # Webhook should be triggered
                webhook_triggered = WebhookEvent.objects.filter(
                    webhook=self.webhook
                ).prefetch_related("webhook")
                # Does the webhook was triggered?
                self.assertEqual(await webhook_triggered.acount(), 1)
                webhook_triggered_first = await webhook_triggered.afirst()
                content = webhook_triggered_first.content
                # Compare the content of the webhook to the recap document
                pacer_doc_id = content["payload"]["results"][0][
                    "recap_documents"
                ][0]["pacer_doc_id"]
                recap_document = RECAPDocument.objects.all()
                recap_document_first = await recap_document.afirst()
                self.assertEqual(
                    recap_document_first.pacer_doc_id, pacer_doc_id
                )

                # Does the Idempotency-Key is generated
                self.assertNotEqual(webhook_triggered_first.event_id, "")
                self.assertEqual(webhook_triggered_first.status_code, 500)
                self.assertEqual(webhook_triggered_first.error_message, "")

                # Is the webhook event updated for retry?
                first_retry_time = fake_now_0 + timedelta(minutes=3)
                self.assertEqual(
                    webhook_triggered_first.next_retry_date, first_retry_time
                )
                self.assertEqual(
                    webhook_triggered_first.event_status,
                    WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                )
                self.assertEqual(webhook_triggered_first.retry_counter, 1)
                self.assertEqual(webhook_triggered_first.response, "ERROR")
                self.assertEqual(
                    webhook_triggered_first.webhook.failure_count, 1
                )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d: (None, ""),
    )
    async def test_update_webhook_after_network_error(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
        mock_download_pacer_pdf_by_rd,
    ):
        """This test verifies if a WebhookEvent is properly enqueued for retry
        after a network failure when trying to send the webhook.
        """

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: exec(
                "raise ConnectionError('Connection Error')"
            ),
        ):
            fake_now_0 = now()
            with time_machine.travel(fake_now_0, tick=False):
                # Trigger a new recap.email notification from testing_1@recap.email
                # auto-subscription option enabled
                await self.async_client.post(
                    self.path, self.data_nda, format="json"
                )

                # Webhook should be triggered
                webhook_triggered = WebhookEvent.objects.filter(
                    webhook=self.webhook
                ).prefetch_related("webhook")
                # Does the webhook was triggered?
                self.assertEqual(await webhook_triggered.acount(), 1)
                webhook_triggered_first = await webhook_triggered.afirst()
                content = webhook_triggered_first.content
                # Compare the content of the webhook to the recap document
                pacer_doc_id = content["payload"]["results"][0][
                    "recap_documents"
                ][0]["pacer_doc_id"]
                recap_document = RECAPDocument.objects.all()
                recap_document_first = await recap_document.afirst()
                self.assertEqual(
                    recap_document_first.pacer_doc_id, pacer_doc_id
                )

                # Does the Idempotency-Key is generated
                self.assertNotEqual(webhook_triggered_first.event_id, "")
                self.assertEqual(webhook_triggered_first.status_code, None)
                self.assertEqual(
                    webhook_triggered_first.error_message,
                    "ConnectionError: Connection Error",
                )

                # Is the webhook event updated for retry?
                first_retry_time = fake_now_0 + timedelta(minutes=3)
                self.assertEqual(
                    webhook_triggered_first.next_retry_date, first_retry_time
                )
                self.assertEqual(
                    webhook_triggered_first.event_status,
                    WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                )
                self.assertEqual(webhook_triggered_first.retry_counter, 1)
                self.assertEqual(webhook_triggered_first.response, "")
                self.assertEqual(
                    webhook_triggered_first.webhook.failure_count, 1
                )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d: (None, ""),
    )
    async def test_success_webhook_delivery(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
        mock_download_pacer_pdf_by_rd,
    ):
        """This test verifies if a WebhookEvent is properly updated after a
        successful delivery.
        """

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, raw=self.file_stream
            ),
        ):
            fake_now_0 = now()
            with time_machine.travel(fake_now_0, tick=False):
                # Trigger a new recap.email notification from testing_1@recap.email
                # auto-subscription option enabled
                await self.async_client.post(
                    self.path, self.data_nda, format="json"
                )

                # Webhook should be triggered
                webhook_triggered = WebhookEvent.objects.filter(
                    webhook=self.webhook
                ).prefetch_related("webhook")
                # Does the webhook was triggered?
                self.assertEqual(await webhook_triggered.acount(), 1)
                webhook_triggered_first = await webhook_triggered.afirst()
                content = webhook_triggered_first.content
                # Compare the content of the webhook to the recap document
                pacer_doc_id = content["payload"]["results"][0][
                    "recap_documents"
                ][0]["pacer_doc_id"]
                recap_document = RECAPDocument.objects.all()
                recap_document_first = await recap_document.afirst()
                self.assertEqual(
                    recap_document_first.pacer_doc_id, pacer_doc_id
                )

                # Does the Idempotency-Key is generated
                self.assertNotEqual(webhook_triggered_first.event_id, "")
                self.assertEqual(webhook_triggered_first.status_code, 200)
                self.assertEqual(webhook_triggered_first.error_message, "")

                self.assertEqual(webhook_triggered_first.next_retry_date, None)
                self.assertEqual(
                    webhook_triggered_first.event_status,
                    WEBHOOK_EVENT_STATUS.SUCCESSFUL,
                )
                self.assertEqual(webhook_triggered_first.retry_counter, 0)
                self.assertEqual(webhook_triggered_first.response, "OK")
                self.assertEqual(
                    webhook_triggered_first.webhook.failure_count, 0
                )

    @mock.patch(
        "cl.recap.tasks.download_pdf_by_magic_number",
        side_effect=lambda z, x, c, v, b, d: (None, ""),
    )
    async def test_retry_webhooks_integration(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
        mock_download_pacer_pdf_by_rd,
    ):
        """This test checks if a recap.email notification comes in and its
        WebhookEvent fails it's properly retried accordingly to the retry
        policy.
        """

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                500, raw=self.file_stream
            ),
        ):
            fake_now_0 = now()
            with time_machine.travel(fake_now_0, tick=False):
                # Trigger a new recap.email notification from testing_1@recap.email
                # auto-subscription option enabled
                await self.async_client.post(
                    self.path, self.data_nda, format="json"
                )

                # Webhook should be triggered
                webhook_triggered = WebhookEvent.objects.filter(
                    webhook=self.webhook
                )
                # Does the webhook was triggered?
                self.assertEqual(await webhook_triggered.acount(), 1)
                webhook_triggered_first = await webhook_triggered.afirst()
                content = webhook_triggered_first.content
                # Compare the content of the webhook to the recap document
                pacer_doc_id = content["payload"]["results"][0][
                    "recap_documents"
                ][0]["pacer_doc_id"]
                recap_document = RECAPDocument.objects.all()
                recap_document_first = await recap_document.afirst()
                self.assertEqual(
                    recap_document_first.pacer_doc_id, pacer_doc_id
                )
                self.assertNotEqual(webhook_triggered_first.event_id, "")
                self.assertEqual(webhook_triggered_first.status_code, 500)
                first_retry_time = fake_now_0 + timedelta(minutes=3)
                self.assertEqual(
                    webhook_triggered_first.next_retry_date, first_retry_time
                )
                self.assertEqual(
                    webhook_triggered_first.event_status,
                    WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                )
                self.assertEqual(webhook_triggered_first.retry_counter, 1)

            elapsed_times = [
                (1, 2, 3, WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY),
                (2, 3, 12, WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY),
            ]
            for try_count, delay, elapsed, status in elapsed_times:
                fake_now = fake_now_0 + timedelta(minutes=delay)
                next_retry_time = fake_now_0 + timedelta(minutes=elapsed)
                with time_machine.travel(fake_now, tick=False):
                    await sync_to_async(retry_webhook_events)()

                    await webhook_triggered_first.arefresh_from_db()
                    self.assertEqual(
                        webhook_triggered_first.event_status,
                        status,
                    )
                    self.assertEqual(
                        webhook_triggered_first.retry_counter, try_count
                    )
                    self.assertEqual(
                        webhook_triggered_first.next_retry_date,
                        next_retry_time,
                    )

            # Update the retry counter and next_retry_date to mock the 6th
            # retry.
            fake_now_4 = fake_now_0 + timedelta(hours=18, minutes=12)
            await webhook_triggered.aupdate(
                retry_counter=6, next_retry_date=fake_now_4
            )
            elapsed_times = [
                # 18:12
                (1092, WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY),
                # 54:39
                (3279, WEBHOOK_EVENT_STATUS.FAILED),
            ]
            # Run a test 18:12 hours after, it should update the retry counter
            # to 7 and the next retry date to 36:27 hours later.
            # Run a second test 54:39 later, since max tries are reached the
            # webhook event should be not updated and marked as Failed.
            for elapsed, status in elapsed_times:
                fake_now = fake_now_0 + timedelta(minutes=elapsed)
                with time_machine.travel(fake_now, tick=False):
                    await sync_to_async(retry_webhook_events)()
                    # Triggered
                    webhook_triggered_first = await webhook_triggered.afirst()
                    self.assertEqual(
                        webhook_triggered_first.event_status,
                        status,
                    )

                    if status == WEBHOOK_EVENT_STATUS.FAILED:
                        self.assertEqual(len(mail.outbox), 3)
                        message = mail.outbox[2]
                        subject_to_compare = "webhook is now disabled"
                        self.assertIn(subject_to_compare, message.subject)
                        self.assertEqual(
                            webhook_triggered_first.retry_counter, 8
                        )
                    else:
                        self.assertEqual(
                            webhook_triggered_first.retry_counter, 7
                        )

                    seven_retry_time = fake_now_4 + timedelta(
                        hours=36, minutes=27
                    )
                    self.assertEqual(
                        webhook_triggered_first.next_retry_date,
                        seven_retry_time,
                    )

    def test_webhook_disabling(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """Can we properly email failing webhook events and disable webhooks
        if max retries are expired?

        Failing webhook event notifications should only be sent based on the
        oldest Enqueued for retry WebhookEvent. Avoiding notifying every
        failing webhook event.
        """

        fake_now = now()
        webhook_e1 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        webhook_e2 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_2'}",
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        # (try_count, total_notifications_sent, webhook_enabled)
        iterations = [
            (1, 0, True),
            (2, 1, True),  # Send first webhook failing notification
            (3, 1, True),
            (4, 1, True),
            (5, 1, True),
            (6, 2, True),  # Send second webhook failing notification
            (7, 2, True),
            (8, 3, False),  # Send webhook disabled notification
            (9, 3, False),
        ]
        webhook_e1_compare = WebhookEvent.objects.filter(pk=webhook_e1.id)
        webhook_e2_compare = WebhookEvent.objects.filter(pk=webhook_e2.id)
        for try_count, notification_out, webhook_enabled in iterations:
            with mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    500, mock_raw=True
                ),
            ):
                next_retry_date = fake_now + timedelta(minutes=3)
                with time_machine.travel(next_retry_date, tick=False):
                    expected_webhooks_to_retry = 2
                    expected_try_count = try_count
                    if try_count >= 8:
                        # After the 8 try, the webhook event is marked as
                        # Failed.
                        status_to_compare = WEBHOOK_EVENT_STATUS.FAILED
                    else:
                        status_to_compare = WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY

                    if try_count >= 9:
                        # No webhook events should be retried after 8 tries.
                        expected_webhooks_to_retry = 0
                        expected_try_count = 8

                    webhooks_to_retry = retry_webhook_events()
                    self.assertEqual(
                        webhooks_to_retry, expected_webhooks_to_retry
                    )
                    self.assertEqual(
                        webhook_e1_compare[0].event_status,
                        status_to_compare,
                    )
                    self.assertEqual(
                        webhook_e2_compare[0].event_status,
                        status_to_compare,
                    )
                    self.assertEqual(
                        webhook_e1_compare[0].retry_counter,
                        expected_try_count,
                    )
                    self.assertEqual(
                        webhook_e2_compare[0].retry_counter,
                        expected_try_count,
                    )
                    self.assertEqual(
                        webhook_e1_compare[0].webhook.enabled,
                        webhook_enabled,
                    )
                    self.assertEqual(
                        webhook_e2_compare[0].webhook.enabled,
                        webhook_enabled,
                    )
                    self.assertEqual(len(mail.outbox), notification_out)

                    if notification_out >= 1:
                        message = mail.outbox[notification_out - 1]
                        subject_to_compare = "webhook is failing"
                        if try_count in [8, 9]:
                            subject_to_compare = "webhook is now disabled"
                        self.assertIn(subject_to_compare, message.subject)

                    # Restore webhook event to test the remaining options
                    next_retry_date = webhook_e1.next_retry_date
                    webhook_e1_compare.update(next_retry_date=next_retry_date)
                    webhook_e2_compare.update(next_retry_date=next_retry_date)

    def test_cut_off_time_for_retry_events_and_restore_retry_counter(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """Can we avoid retrying failing webhook events if they are older than
        HOURS_WEBHOOKS_CUT_OFF? They should be marked as failed.

        Retry counter for failing webhook events created within the last
        HOURS_WEBHOOKS_CUT_OFF should be restarted to 0 once the parent webhook
        endpoint is re-enabled
        """

        fake_now = now()
        # Today - HOURS_WEBHOOKS_CUT_OFF hours
        fake_now_minus_2 = fake_now - timedelta(hours=HOURS_WEBHOOKS_CUT_OFF)
        with time_machine.travel(fake_now_minus_2, tick=False):
            webhook_e1 = WebhookEventFactory(
                webhook=self.webhook,
                content="{'message': 'ok_1'}",
                event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                retry_counter=7,
                next_retry_date=fake_now_minus_2 + timedelta(minutes=3),
            )
        # Today
        with time_machine.travel(fake_now, tick=False):
            webhook_e2 = WebhookEventFactory(
                webhook=self.webhook,
                content="{'message': 'ok_1'}",
                event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                retry_counter=2,
                next_retry_date=fake_now + timedelta(minutes=3),
            )

        # Today + 1 day
        fake_now_1 = fake_now + timedelta(days=1)
        with time_machine.travel(fake_now_1, tick=False):
            webhook_e3 = WebhookEventFactory(
                webhook=self.webhook,
                content="{'message': 'ok_2'}",
                event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                retry_counter=2,
                next_retry_date=fake_now_1 + timedelta(minutes=3),
            )

        # Today + HOURS_WEBHOOKS_CUT_OFF hours
        fake_now_2 = fake_now + timedelta(hours=HOURS_WEBHOOKS_CUT_OFF)
        with time_machine.travel(fake_now_2, tick=False):
            webhook_e4 = WebhookEventFactory(
                webhook=self.webhook,
                content="{'message': 'ok_2'}",
                event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                retry_counter=3,
                next_retry_date=fake_now_2 + timedelta(minutes=3),
            )

        webhook_e1_compare = WebhookEvent.objects.filter(pk=webhook_e1.id)
        webhook_e2_compare = WebhookEvent.objects.filter(pk=webhook_e2.id)
        webhook_e3_compare = WebhookEvent.objects.filter(pk=webhook_e3.id)
        webhook_e4_compare = WebhookEvent.objects.filter(pk=webhook_e4.id)
        webhook_compare = Webhook.objects.filter(pk=self.webhook.pk)

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                500, mock_raw=True
            ),
        ):
            # Today - HOURS_WEBHOOKS_CUT_OFF hours
            next_retry_date = fake_now_minus_2 + timedelta(minutes=3)
            with time_machine.travel(next_retry_date, tick=False):
                # Retry webhook_e1, marked as Failed, and disable its parent
                # webhook since max retries are reached.
                webhooks_to_retry = retry_webhook_events()
                self.assertEqual(webhooks_to_retry, 1)
                self.assertEqual(
                    webhook_e1_compare[0].event_status,
                    WEBHOOK_EVENT_STATUS.FAILED,
                )
                self.assertEqual(
                    webhook_compare[0].enabled,
                    False,
                )

            # Today + HOURS_WEBHOOKS_CUT_OFF hours
            next_retry_date = fake_now_2 + timedelta(minutes=3)
            with time_machine.travel(next_retry_date, tick=False):
                # No webhook events should be retried since
                # parent webhook is disabled.
                webhooks_to_retry = retry_webhook_events()
                self.assertEqual(webhooks_to_retry, 0)

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            fake_now_3 = fake_now + timedelta(
                hours=HOURS_WEBHOOKS_CUT_OFF + 12
            )
            with time_machine.travel(fake_now_3, tick=False):
                # Today + 3 days, Re-enable Webhook:
                self.webhook.enabled = True
                self.webhook.save()

                # Retry pending webhook events.
                webhooks_to_retry = retry_webhook_events()
                self.assertEqual(webhooks_to_retry, 2)

                # webhook_e3 and webhook_e4 delivered successfully
                self.assertEqual(
                    webhook_e3_compare[0].event_status,
                    WEBHOOK_EVENT_STATUS.SUCCESSFUL,
                )
                self.assertEqual(
                    webhook_e4_compare[0].event_status,
                    WEBHOOK_EVENT_STATUS.SUCCESSFUL,
                )
                self.assertEqual(webhook_e3_compare[0].retry_counter, 0)
                self.assertEqual(webhook_e4_compare[0].retry_counter, 0)

                # webhook_e2 marked as failed since it's older than
                # HOURS_WEBHOOKS_CUT_OFF.
                self.assertEqual(
                    webhook_e2_compare[0].event_status,
                    WEBHOOK_EVENT_STATUS.FAILED,
                )
                self.assertEqual(
                    webhook_e2_compare[0].retry_counter,
                    webhook_e2.retry_counter,
                )

    def test_webhook_continues_failing_after_an_event_delivery(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """Can we properly continue emailing failing webhook events emails
        after the oldest webhook event is delivered but then the webhook
        endpoint continues failing?
        """

        fake_now = now()
        webhook_e1 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        webhook_e2 = WebhookEventFactory(
            webhook=self.webhook,
            content="{'message': 'ok_2'}",
            event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
            next_retry_date=fake_now + timedelta(minutes=3),
        )
        # (try_count, total_notifications_sent, webhook_enabled)
        iterations = [
            (1, 0),
            (2, 1),  # Send first webhook failing notification
            (3, 1),
            (4, 1),
        ]
        webhook_e1_compare = WebhookEvent.objects.filter(pk=webhook_e1.id)
        webhook_e2_compare = WebhookEvent.objects.filter(pk=webhook_e2.id)
        for try_count, notification_out in iterations:
            # Try to deliver webhook_e1 and webhook_e2 4 times.
            with mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    500, mock_raw=True
                ),
            ):
                next_retry_date = fake_now + timedelta(minutes=3)
                with time_machine.travel(next_retry_date, tick=False):
                    webhooks_to_retry = retry_webhook_events()
                    self.assertEqual(webhooks_to_retry, 2)
                    self.assertEqual(len(mail.outbox), notification_out)

                    # Restore webhook event to test the remaining options
                    webhook_e1_compare.update(
                        next_retry_date=webhook_e1.next_retry_date,
                    )
                    webhook_e2_compare.update(
                        next_retry_date=webhook_e2.next_retry_date
                    )
                    if try_count == 4:
                        webhook_e2_compare.update(
                            next_retry_date=webhook_e2.next_retry_date
                            + timedelta(minutes=3),
                        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            # Deliver webhook_e1 successfully.
            next_retry_date = fake_now + timedelta(minutes=3)
            with time_machine.travel(next_retry_date, tick=False):
                webhooks_to_retry = retry_webhook_events()
                self.assertEqual(webhooks_to_retry, 1)
                self.assertEqual(
                    webhook_e1_compare[0].event_status,
                    WEBHOOK_EVENT_STATUS.SUCCESSFUL,
                )

        iterations = [
            (5, 1, True),
            (6, 2, True),  # Send second webhook failing notification
            (7, 2, True),
            (8, 3, False),  # Send disabled webhook failing notification
        ]
        # Continue trying to deliver webhook_e2 4 more times. Mocking a
        # failing webhook endpoint. Send a webhook failing notification on the
        # 6th try, and disable the webhook endpoint on the 8th try.
        for try_count, notification_out, webhook_enabled in iterations:
            with mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    500, mock_raw=True
                ),
            ):
                next_retry_date = fake_now + timedelta(minutes=6)
                with time_machine.travel(next_retry_date, tick=False):
                    expected_webhooks_to_retry = 1
                    expected_try_count = try_count
                    if try_count >= 8:
                        # After the 8 try, the webhook event is marked as
                        # Failed.
                        status_to_compare = WEBHOOK_EVENT_STATUS.FAILED
                    else:
                        status_to_compare = WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY

                    if try_count >= 9:
                        # No webhook events should be retried after 8 tries.
                        expected_webhooks_to_retry = 0
                        expected_try_count = 8

                    webhooks_to_retry = retry_webhook_events()
                    self.assertEqual(
                        webhooks_to_retry, expected_webhooks_to_retry
                    )
                    self.assertEqual(
                        webhook_e2_compare[0].event_status,
                        status_to_compare,
                    )
                    self.assertEqual(
                        webhook_e2_compare[0].retry_counter,
                        expected_try_count,
                    )
                    self.assertEqual(
                        webhook_e2_compare[0].webhook.enabled,
                        webhook_enabled,
                    )
                    self.assertEqual(len(mail.outbox), notification_out)

                    if notification_out >= 1:
                        message = mail.outbox[notification_out - 1]
                        subject_to_compare = "webhook is failing"
                        if try_count in [8, 9]:
                            subject_to_compare = "webhook is now disabled"
                        self.assertIn(subject_to_compare, message.subject)

                    webhook_e2_compare.update(
                        next_retry_date=webhook_e2.next_retry_date,
                    )

    def test_delete_old_webhook_events(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """Can we properly delete webhook events older than DAYS_TO_DELETE days?

        The delete_old_webhook_events is only executed once a day at 12:00 UTC.
        """

        fake_days_ago = now() - timedelta(days=DAYS_TO_DELETE + 1)
        with time_machine.travel(fake_days_ago, tick=False):
            webhook_e1 = WebhookEventFactory(
                webhook=self.webhook,
            )
            webhook_e2 = WebhookEventFactory(
                webhook=self.webhook,
            )

        webhook_e3 = WebhookEventFactory(
            webhook=self.webhook,
        )

        # It's not time to execute the delete method, one minute behind.
        no_time_to_delete_1 = now().replace(hour=11, minute=59, second=0)
        with time_machine.travel(no_time_to_delete_1, tick=False):
            deleted_count, notifications_send = execute_additional_tasks()
            self.restart_webhook_executed()
            self.assertEqual(deleted_count, None)

        # The delete method should be executed at 12:00 UTC.
        time_to_delete = now().replace(hour=12, minute=0, second=0)
        with time_machine.travel(time_to_delete, tick=False):
            deleted_count, notifications_send = execute_additional_tasks()
            self.assertEqual(deleted_count, 2)

        # It's not time to execute, already executed today.
        no_time_to_delete = now().replace(hour=12, minute=5, second=0)
        with time_machine.travel(no_time_to_delete, tick=False):
            deleted_count, notifications_send = execute_additional_tasks()
            self.restart_webhook_executed()
            self.assertEqual(deleted_count, None)

        webhook_events = WebhookEvent.objects.all()
        # webhook_e3 should still exist.
        self.assertEqual(webhook_events[0].pk, webhook_e3.pk)

    def test_send_notifications_if_webhook_still_disabled(
        self,
        mock_is_docket_entry_sealed,
        mock_enqueue_alert,
        mock_bucket_open,
        mock_cookies,
        mock_pacer_court_accessible,
        mock_get_document_number_from_confirmation_page,
    ):
        """Can we send a notification to users if one of their webhooks is
        still disabled, one, two and three days after?
        """
        # Enable disabled_webhook to avoid interfering with this test
        Webhook.objects.filter(pk=self.webhook_disabled.id).update(
            enabled=True
        )

        now_time = datetime.now(timezone.utc)
        fake_now = now_time.replace(hour=11, minute=00)

        fake_minus_2_days = fake_now - timedelta(days=2)
        with time_machine.travel(fake_minus_2_days, tick=False):
            webhook_e1 = WebhookEventFactory(
                webhook=self.webhook,
                content="{'message': 'ok_1'}",
                event_status=WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY,
                retry_counter=7,
                next_retry_date=fake_now + timedelta(minutes=3),
            )

        webhook_e1_compare = WebhookEvent.objects.filter(pk=webhook_e1.id)
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                500, mock_raw=True
            ),
        ):
            # Time to retry
            next_retry_date = fake_now + timedelta(minutes=3)
            with time_machine.travel(next_retry_date, tick=False):
                webhooks_to_retry = retry_webhook_events()
                self.assertEqual(webhooks_to_retry, 1)
                self.assertEqual(
                    webhook_e1_compare[0].event_status,
                    WEBHOOK_EVENT_STATUS.FAILED,
                )
                self.assertEqual(
                    webhook_e1_compare[0].webhook.enabled,
                    False,
                )
                self.assertEqual(len(mail.outbox), 1)
                subject_to_compare = "webhook is now disabled"
                message = mail.outbox[0]
                self.assertIn(subject_to_compare, message.subject)

        iterations = [
            (12, 1, 0),  # 12 hours after disabled, no new email out
            (24, 2, 1),  # 1 day after, 1° webhook still disabled notification
            (48, 3, 2),  # 2 days after, 2° webhook still disabled notification
            (72, 4, 3),  # 3 days after, 3° webhook still disabled notification
            (96, 4, 3),  # 4 days after, No new email out
        ]
        time_to_check = now_time.replace(hour=12, minute=00)
        minute_delay = 0
        for hours, email_out, days in iterations:
            minute_delay += 1
            hours_after = time_to_check + timedelta(
                hours=hours, minutes=minute_delay
            )
            with time_machine.travel(hours_after, tick=False):
                execute_additional_tasks()
                self.restart_webhook_executed()
                self.assertEqual(len(mail.outbox), email_out)

                subject_to_compare = "webhook is now disabled"
                if email_out > 1:
                    day_str = "day"
                    if days > 1:
                        day_str = "days"
                    subject_to_compare = (
                        f"has been disabled for {days} {day_str}"
                    )
                message = mail.outbox[email_out - 1]
                self.assertIn(subject_to_compare, message.subject)


@mock.patch("cl.recap.tasks.DocketReport", new=fakes.FakeDocketReport)
@mock.patch(
    "cl.recap.tasks.PossibleCaseNumberApi",
    new=fakes.FakePossibleCaseNumberApi,
)
@mock.patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
@mock.patch(
    "cl.recap.tasks.get_pacer_cookie_from_cache",
    side_effect=lambda x: True,
)
class RecapFetchWebhooksTest(TestCase):
    """Test RECAP Fetch Webhooks"""

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.user_profile = UserProfileWithParentsFactory()
        cls.webhook_enabled = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.RECAP_FETCH,
            url="https://example.com/",
            enabled=True,
        )

        cls.user_profile_2 = UserProfileWithParentsFactory()
        cls.webhook_disabled = WebhookFactory(
            user=cls.user_profile_2.user,
            event_type=WebhookEventType.RECAP_FETCH,
            url="https://example.com/",
            enabled=False,
        )

        att_page = fakes.FakeAttachmentPage()
        pacer_doc_id = att_page.data["pacer_doc_id"]
        document_number = att_page.data["document_number"]
        cls.de = DocketEntryWithParentsFactory(
            docket__court=cls.court, entry_number=document_number
        )
        cls.rd = RECAPDocumentFactory(
            docket_entry=cls.de,
            pacer_doc_id=pacer_doc_id,
            document_number=document_number,
        )

    def test_recap_fetch_docket_webhook(
        self, mock_court_accessible, mock_cookies
    ):
        """Can we send a webhook event when a docket RECAP fetch completed?"""

        fq = PacerFetchQueueFactory(
            user=self.user_profile.user,
            request_type=REQUEST_TYPE.DOCKET,
            court_id=self.court.pk,
            docket_number=fakes.DOCKET_NUMBER,
        )

        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 1)

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            result = do_pacer_fetch(fq)

        # Wait for the chain to complete
        result.get()

        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.SUCCESSFUL)

        self.assertEqual(dockets.count(), 2)

        # Only one webhook event should be triggered for user_profile since
        # user_profile_2 webhook endpoint is disabled.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 1)
        self.assertEqual(
            webhook_events[0].webhook.user,
            self.user_profile.user,
        )
        content = webhook_events[0].content
        # Compare the webhook event payload
        self.assertEqual(
            content["webhook"]["event_type"],
            WebhookEventType.RECAP_FETCH,
        )
        self.assertEqual(content["payload"]["id"], fq.id)
        self.assertEqual(
            content["payload"]["status"], PROCESSING_STATUS.SUCCESSFUL
        )
        self.assertNotEqual(content["payload"]["date_completed"], None)

    @mock.patch(
        "cl.recap.mergers.AttachmentPage",
        new=fakes.FakeAttachmentPage,
    )
    @mock.patch(
        "cl.corpus_importer.tasks.AttachmentPage",
        new=fakes.FakeAttachmentPage,
    )
    def test_recap_attachment_page_webhook(
        self, mock_court_accessible, mock_cookies
    ):
        """Can we send a webhook event when an attachment page RECAP fetch
        completed?
        """

        fq = PacerFetchQueueFactory(
            user=self.user_profile.user,
            request_type=REQUEST_TYPE.ATTACHMENT_PAGE,
            recap_document=self.rd,
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            result = do_pacer_fetch(fq)

        # Wait for the chain to complete
        result.get()

        dockets = Docket.objects.all()
        self.assertEqual(len(dockets), 1)

        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.SUCCESSFUL)

        # Only one webhook event should be triggered for user_profile since
        # user_profile_2 webhook endpoint is disabled.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 1)

        self.assertEqual(
            webhook_events[0].webhook.user,
            self.user_profile.user,
        )
        content = webhook_events[0].content
        # Compare the webhook event payload
        self.assertEqual(
            content["webhook"]["event_type"],
            WebhookEventType.RECAP_FETCH,
        )
        self.assertEqual(content["payload"]["id"], fq.id)
        self.assertEqual(
            content["payload"]["status"], PROCESSING_STATUS.SUCCESSFUL
        )
        self.assertNotEqual(content["payload"]["date_completed"], None)

    @mock.patch(
        "cl.recap.tasks.download_pacer_pdf_by_rd",
        side_effect=lambda z, x, c, v, b: (
            MockResponse(
                200,
                mock_bucket_open(
                    "gov.uscourts.ca8.17-2543.00803263743.0.pdf", "rb", True
                ),
            ),
            "OK",
        ),
    )
    def test_recap_pacer_doc_webhook(
        self, mock_court_accessible, mock_cookies, mock_download_pdf
    ):
        """Can we send a webhook event when a PDF RECAP fetch completed?"""

        fq = PacerFetchQueueFactory(
            user=self.user_profile.user,
            request_type=REQUEST_TYPE.PDF,
            recap_document=self.rd,
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            result = do_pacer_fetch(fq)

        # Wait for the chain to complete
        result.get()

        dockets = Docket.objects.all()
        self.assertEqual(len(dockets), 1)

        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.SUCCESSFUL)

        # Only one webhook event should be triggered for user_profile since
        # user_profile_2 webhook endpoint is disabled.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 1)

        self.assertEqual(
            webhook_events[0].webhook.user,
            self.user_profile.user,
        )
        content = webhook_events[0].content
        # Compare the webhook event payload
        self.assertEqual(
            content["webhook"]["event_type"],
            WebhookEventType.RECAP_FETCH,
        )
        self.assertEqual(content["payload"]["id"], fq.id)
        self.assertEqual(
            content["payload"]["status"], PROCESSING_STATUS.SUCCESSFUL
        )
        self.assertNotEqual(content["payload"]["date_completed"], None)


class CalculateRecapsSequenceNumbersTest(TestCase):
    """Test calculate_recap_sequence_numbers considering docket entries court
    timezone.
    """

    @classmethod
    def setUpTestData(cls):
        cls.cand = CourtFactory(id="cand", jurisdiction="FB")
        cls.nyed = CourtFactory(id="nyed", jurisdiction="FB")
        cls.nysd = CourtFactory(id="nysd", jurisdiction="FB")

        cls.d_cand = DocketFactory(
            source=Docket.RECAP,
            court=cls.cand,
            pacer_case_id="104490",
        )
        cls.d_nyed = DocketFactory(
            source=Docket.RECAP,
            court=cls.nyed,
            pacer_case_id="104491",
        )
        cls.d_nysd = DocketFactory(
            source=Docket.RECAP,
            court=cls.nysd,
            pacer_case_id="104492",
        )

        cls.de_date_asc = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=date(2021, 10, 15),
                    document_number=1,
                ),
                DocketEntryDataFactory(
                    date_filed=date(2021, 10, 15),
                    document_number=2,
                ),
                DocketEntryDataFactory(
                    date_filed=date(2021, 10, 15),
                    document_number=3,
                ),
            ],
        )

        cls.de_datetime_desc = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime(
                        2021, 10, 16, 2, 46, 51, tzinfo=tzutc()
                    ),
                    document_number=3,
                ),
                DocketEntryDataFactory(
                    date_filed=datetime(
                        2021, 10, 16, 2, 46, 51, tzinfo=tzutc()
                    ),
                    document_number=2,
                ),
                DocketEntryDataFactory(
                    date_filed=datetime(
                        2021, 10, 16, 2, 46, 51, tzinfo=tzutc()
                    ),
                    document_number=1,
                ),
            ],
        )

        cls.de_datetime_prev_differs = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime(
                        2021, 10, 17, 2, 46, 51, tzinfo=tzutc()
                    ),
                    document_number=3,
                ),
                DocketEntryDataFactory(
                    date_filed=datetime(
                        2021, 10, 16, 2, 46, 51, tzinfo=tzutc()
                    ),
                    document_number=2,
                ),
                DocketEntryDataFactory(
                    date_filed=datetime(
                        2021, 10, 16, 2, 46, 51, tzinfo=tzutc()
                    ),
                    document_number=1,
                ),
            ],
        )

    def test_get_order_of_docket(self):
        """Test get_order_of_docket method"""

        order_asc = get_order_of_docket(self.de_date_asc["docket_entries"])
        self.assertEqual(order_asc, "asc")

        order_desc = get_order_of_docket(
            self.de_datetime_desc["docket_entries"]
        )
        self.assertEqual(order_desc, "desc")

    def test_calculate_recap_sequence_numbers(self):
        """Does calculate_recap_sequence_numbers method works properly using
        court timezone when time is available?
        """

        async_to_sync(add_docket_entries)(
            self.d_nyed, self.de_datetime_desc["docket_entries"]
        )
        docket_entries_nyed = DocketEntry.objects.filter(
            docket__court=self.nyed
        ).order_by("recap_sequence_number")
        entry_number = 1
        # Validate recap_sequence_number generated from entries in desc order
        for de in docket_entries_nyed:
            self.assertEqual(de.entry_number, entry_number)
            self.assertEqual(
                de.recap_sequence_number, f"2021-10-15.00{entry_number}"
            )
            entry_number += 1

        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_date_asc["docket_entries"]
        )
        docket_entries_cand = DocketEntry.objects.filter(
            docket__court=self.cand
        ).order_by("recap_sequence_number")
        entry_number = 1
        # Validate recap_sequence_number generated from entries in asc order
        for de in docket_entries_cand:
            self.assertEqual(de.entry_number, entry_number)
            self.assertEqual(
                de.recap_sequence_number, f"2021-10-15.00{entry_number}"
            )
            entry_number += 1

        async_to_sync(add_docket_entries)(
            self.d_nysd, self.de_datetime_prev_differs["docket_entries"]
        )
        docket_entries_nysd = DocketEntry.objects.filter(
            docket__court=self.nysd
        ).order_by("recap_sequence_number")
        # Validate recap_sequence_number changes if the previous entry date
        # differs
        entry_number = 1
        prev_de = None
        for de in docket_entries_nysd:
            if not prev_de or de.date_filed == prev_de.date_filed:
                self.assertEqual(
                    de.recap_sequence_number, f"2021-10-15.00{entry_number}"
                )
            else:
                self.assertEqual(de.recap_sequence_number, "2021-10-16.001")
            self.assertEqual(de.entry_number, entry_number)
            entry_number += 1
            prev_de = de


class LookupDocketsTest(TestCase):
    """Test find_docket_object lookups work properly, avoid overwriting
    dockets with identical docket_number_core if they are different cases.
    """

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_appellate = CourtFactory(id="ca1", jurisdiction="F")

        cls.docket_1 = DocketFactory(
            case_name="Young v. State",
            docket_number="No. 3:17-CV-01477",
            court=cls.court,
            source=Docket.HARVARD,
            pacer_case_id=None,
        )
        cls.docket_core_data = RECAPEmailDocketDataFactory(
            case_name="Young v. State", docket_number="3:17-CV-01477"
        )
        cls.docket_2 = DocketFactory(
            case_name="Young 2 v. State",
            docket_number="212-213",
            docket_number_core=None,
            court=cls.court,
            source=Docket.HARVARD,
            pacer_case_id=None,
        )
        cls.docket_no_core_data = RECAPEmailDocketDataFactory(
            case_name="Young v. State", docket_number="212-213"
        )
        cls.docket_case_id = DocketFactory(
            case_name="Barton v. State",
            docket_number="No. 3:17-mj-01477",
            court=cls.court,
            source=Docket.HARVARD,
            pacer_case_id="12345",
        )
        cls.docket_case_id_2 = DocketFactory(
            case_name="Barton v. State",
            docket_number="No. 4:20-cv-01245",
            court=cls.court,
            source=Docket.HARVARD,
            pacer_case_id="54321",
        )
        cls.docket_data = RECAPEmailDocketDataFactory(
            case_name="Barton v. State", docket_number="3:17-mj-01477"
        )

    def test_case_id_and_docket_number_core_lookup(self):
        """Confirm if lookup by pacer_case_id and docket_number_core works
        properly.
        """

        d = async_to_sync(find_docket_object)(
            self.court.pk, "12345", self.docket_data["docket_number"]
        )
        async_to_sync(update_docket_metadata)(d, self.docket_data)
        d.save()

        # Successful lookup, dockets matched
        self.assertEqual(d.id, self.docket_case_id.id)
        self.assertEqual(
            d.docket_number_core, self.docket_case_id.docket_number_core
        )

    def test_case_id_lookup(self):
        """Confirm if lookup by only pacer_case_id works properly."""

        d = async_to_sync(find_docket_object)(
            self.court.pk, "54321", self.docket_data["docket_number"]
        )
        async_to_sync(update_docket_metadata)(d, self.docket_data)
        d.save()

        # Successful lookup, dockets matched
        self.assertEqual(d.id, self.docket_case_id_2.id)
        self.assertEqual(
            d.docket_number_core, self.docket_case_id_2.docket_number_core
        )

    def test_docket_number_core_lookup(self):
        """Confirm if lookup by only docket_number_core works properly."""

        d = async_to_sync(find_docket_object)(
            self.court.pk,
            self.docket_core_data["docket_entries"][0]["pacer_case_id"],
            self.docket_core_data["docket_number"],
        )
        async_to_sync(update_docket_metadata)(d, self.docket_core_data)
        d.save()

        # Successful lookup, dockets matched
        self.assertEqual(d.id, self.docket_1.id)
        self.assertEqual(
            d.docket_number_core, self.docket_1.docket_number_core
        )

    def test_docket_number_lookup(self):
        """Confirm if lookup by only docket_number works properly."""

        d = async_to_sync(find_docket_object)(
            self.court.pk,
            self.docket_no_core_data["docket_entries"][0]["pacer_case_id"],
            self.docket_no_core_data["docket_number"],
        )
        async_to_sync(update_docket_metadata)(d, self.docket_no_core_data)
        d.save()

        # Successful lookup, dockets matched
        self.assertEqual(d.id, self.docket_2.id)
        self.assertEqual(
            d.docket_number_core, self.docket_2.docket_number_core
        )

    def test_avoid_overwrite_docket_by_number_core(self):
        """Can we avoid overwriting a docket when we got two identical
        docket_number_core in the same court, but they are different dockets?
        """

        d = async_to_sync(find_docket_object)(
            self.court.pk,
            self.docket_data["docket_entries"][0]["pacer_case_id"],
            self.docket_data["docket_number"],
        )

        async_to_sync(update_docket_metadata)(d, self.docket_data)
        d.save()

        # Docket is not overwritten a new one is created instead.
        self.assertNotEqual(d.id, self.docket_1.id)
        self.assertEqual(
            d.docket_number_core, self.docket_1.docket_number_core
        )

    def test_avoid_overwrite_docket_by_number_core_multiple_results(self):
        """Can we avoid overwriting a docket when we got multiple results for a
        docket_number_core in the same court but they are different dockets?
        """

        DocketFactory(
            case_name="Young v. State",
            docket_number="No. 3:17-CV-01477",
            court=self.court,
            source=Docket.HARVARD,
            pacer_case_id=None,
        )

        d = async_to_sync(find_docket_object)(
            self.court.pk,
            self.docket_data["docket_entries"][0]["pacer_case_id"],
            self.docket_data["docket_number"],
        )

        async_to_sync(update_docket_metadata)(d, self.docket_data)
        d.save()

        # Docket is not overwritten a new one is created instead.
        self.assertNotEqual(d.id, self.docket_1.id)
        self.assertEqual(
            d.docket_number_core, self.docket_1.docket_number_core
        )

    def test_lookup_by_normalized_docket_number_case(self):
        """Can we match a docket which its docket number case is different
        from the incoming data?
        """
        d = DocketFactory(
            case_name="Young v. State",
            docket_number="No. 3:18-MJ-01477",
            court=self.court_appellate,
            source=Docket.RECAP,
            pacer_case_id=None,
        )

        docket_data_lower_number = RECAPEmailDocketDataFactory(
            case_name="Barton v. State",
            docket_number="3:18-mj-01477",
            docket_entries=[
                RECAPEmailDocketEntryDataFactory(pacer_case_id="1234568")
            ],
        )
        new_d = async_to_sync(find_docket_object)(
            self.court_appellate.pk,
            docket_data_lower_number["docket_entries"][0]["pacer_case_id"],
            docket_data_lower_number["docket_number"],
        )
        async_to_sync(update_docket_metadata)(new_d, docket_data_lower_number)
        new_d.save()
        # The existing docket is matched instead of creating a new one.
        self.assertEqual(new_d.pk, d.pk)


class CleanUpDuplicateAppellateEntries(TestCase):
    """Test clean_up_duplicate_appellate_entries method that finds and clean
    duplicated entries after a court enables document numbers.
    """

    @mock.patch(
        "cl.recap.management.commands.remove_appellate_entries_with_long_numbers.logger"
    )
    def test_clean_duplicate_appellate_entries(self, mock_logger):
        """Test clean duplicated entries by document number and description"""

        court = CourtFactory(id="ca5", jurisdiction="F")
        docket = DocketFactory(
            court=court,
            case_name="Foo v. Bar",
            docket_number="12-40601",
            pacer_case_id="12345",
        )

        # Duplicated entry by pacer_doc_id as number
        de1 = DocketEntryFactory(
            docket=docket,
            entry_number=506585234,
        )
        RECAPDocumentFactory(
            docket_entry=de1,
            pacer_doc_id="00506585234",
            document_number="00506585234",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        # This entry should be preserved.
        de1_2 = DocketEntryFactory(
            docket=docket,
            entry_number=1,
        )
        RECAPDocumentFactory(
            docket_entry=de1_2,
            pacer_doc_id="00506585234",
            document_number="1",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        # Duplicated entry with no entry number and no pacer_doc_id
        de2 = DocketEntryFactory(
            docket=docket,
            entry_number=None,
            description="Lorem ipsum dolor sit amet",
        )
        RECAPDocumentFactory(
            docket_entry=de2,
            pacer_doc_id="",
            document_number="",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        # This entry should be preserved.
        de2_2 = DocketEntryFactory(
            docket=docket,
            entry_number=2,
            description="Lorem ipsum dolor sit amet",
        )
        RECAPDocumentFactory(
            docket_entry=de2_2,
            pacer_doc_id="",
            document_number="2",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        # No duplicated entry with pacer_doc_id as number
        de3 = DocketEntryFactory(
            docket=docket,
            entry_number=506585238,
        )
        RECAPDocumentFactory(
            docket_entry=de3,
            pacer_doc_id="00506585238",
            document_number="00506585238",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        # No duplicated entry with document number.
        de4 = DocketEntryFactory(
            docket=docket,
            entry_number=105,
        )
        RECAPDocumentFactory(
            docket_entry=de4,
            pacer_doc_id="00506585239",
            document_number="105",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        docket_entries = DocketEntry.objects.all()
        recap_documents = RECAPDocument.objects.all()
        self.assertEqual(docket_entries.count(), 6)
        self.assertEqual(recap_documents.count(), 6)

        # Clean up duplicated entries.
        clean_up_duplicate_appellate_entries([court.pk], None, True)

        # After the cleanup, 2 entries should be removed.
        mock_logger.info.assert_called_with(
            f"Cleaned 2 entries in {court.pk} after 2023-01-08."
        )
        self.assertEqual(docket_entries.count(), 4)
        self.assertEqual(recap_documents.count(), 4)

        # Confirm the right entries are preserved.
        assert all(
            de.entry_number in [105, 506585238, 1, 2] for de in docket_entries
        )

    @mock.patch(
        "cl.recap.management.commands.remove_appellate_entries_with_long_numbers.logger"
    )
    def test_skip_entries_before_date(self, mock_logger):
        """Test skip looking for duplicated entries created before the date
        the court enabled document numbers
        """

        court = CourtFactory(id="ca11", jurisdiction="F")
        docket = DocketFactory(
            court=court,
            case_name="Foo v. ca11",
            docket_number="12-40601",
            pacer_case_id="12345",
        )
        with time_machine.travel(
            datetime(year=2022, month=9, day=4), tick=False
        ):
            de1 = DocketEntryFactory(
                docket=docket,
                entry_number=506585234,
            )
            RECAPDocumentFactory(
                docket_entry=de1,
                pacer_doc_id="00506585234",
                document_number="00506585234",
                document_type=RECAPDocument.PACER_DOCUMENT,
            )

        clean_up_duplicate_appellate_entries([court.pk], None, True)
        mock_logger.info.assert_called_with(
            f"Skipping {court.pk}, no entries created after 2022-10-01 found."
        )
        docket_entries = DocketEntry.objects.all()
        self.assertEqual(docket_entries.count(), 1)


class RemoveDuplicatedMinuteEntries(TestCase):
    """Test remove duplicated minute entries while avoid deleting those who
    are not duplicates in the same day.
    """

    @classmethod
    def setUpTestData(cls):
        cls.cand = CourtFactory(id="cand", jurisdiction="FD")
        cls.d = DocketFactory(
            source=Docket.RECAP,
            court=cls.cand,
        )

    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    def test_avoid_deleting_non_duplicated_minute_entries(
        self,
        mock_webhook_post,
    ):
        """Confirm non duplicated entries are not deleted when merging the
        docket history report.
        """
        docket_entries = DocketEntry.objects.all()
        self.assertEqual(docket_entries.count(), 0)

        docket_data = DocketDataFactory(
            docket_entries=[
                MinuteDocketEntryDataFactory(
                    date_filed=date(2020, 10, 15),
                    date_entered=date(2020, 10, 15),
                    description="The corrected publicly accessible audio line for today's conference is available",
                    short_description=None,
                    document_number=210,
                ),
                MinuteDocketEntryDataFactory(
                    date_filed=date(2020, 10, 15),
                    date_entered=date(2020, 10, 15),
                    description="Set/Reset Deadlines: Expert Discovery due by 6/11/2021. (cf) (Entered: 10/15/2020)",
                    short_description=None,
                ),
                MinuteDocketEntryDataFactory(
                    date_filed=date(2020, 10, 15),
                    date_entered=date(2020, 10, 15),
                    description="Set/Reset Deadlines: Fact Discovery due by 2/12/2021. (cf) (Entered: 10/15/2020)",
                    short_description=None,
                ),
            ],
        )

        # Add initial docket entries with only long descriptions.
        data = deepcopy(docket_data)
        async_to_sync(add_docket_entries)(self.d, data["docket_entries"])
        # 3 entries should be created.
        self.assertEqual(docket_entries.count(), 3)

        data_history = deepcopy(docket_data)
        # Add short descriptions to entries, simulating a docket history report.
        data_history["docket_entries"][0][
            "short_description"
        ] = "Order on Motion for Extension of Time to Complete Discovery"
        data_history["docket_entries"][1][
            "short_description"
        ] = "Set/Reset Deadlines"
        data_history["docket_entries"][2][
            "short_description"
        ] = "Set/Reset Deadlines"
        # Merge docket history report entries.
        async_to_sync(add_docket_entries)(
            self.d, data_history["docket_entries"]
        )
        # Entries are properly merged without removing non duplicated entries.
        self.assertEqual(docket_entries.count(), 3)
        # Confirm entries were properly merged.
        for entry_db, entry in zip(
            docket_entries, data_history["docket_entries"]
        ):
            self.assertEqual(entry_db.description, entry["description"])
            self.assertEqual(
                entry_db.recap_documents.all()[0].description,
                entry["short_description"],
            )

    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    def test_remove_duplicated_minute_entries(
        self,
        mock_webhook_post,
    ):
        """Confirm that we can remove minute entries that are in fact
        duplicated.
        """
        docket_entries = DocketEntry.objects.all()
        self.assertEqual(docket_entries.count(), 0)

        docket_data = DocketDataFactory(
            docket_entries=[
                MinuteDocketEntryDataFactory(
                    date_filed=date(2020, 10, 15),
                    date_entered=date(2020, 10, 15),
                    description="The corrected publicly accessible audio line for today's conference is available",
                    short_description=None,
                    document_number=210,
                ),
                MinuteDocketEntryDataFactory(  # Duplicated entry
                    date_filed=date(2020, 10, 15),
                    date_entered=date(2020, 10, 15),
                    short_description="Set/Reset Deadlines",
                    description=None,
                ),
                MinuteDocketEntryDataFactory(
                    date_filed=date(2020, 10, 15),
                    date_entered=date(2020, 10, 15),
                    description="Set/Reset Deadlines: Fact Discovery due by 2/12/2021. (cf) (Entered: 10/15/2020)",
                    short_description=None,
                ),
                MinuteDocketEntryDataFactory(
                    date_filed=date(2020, 10, 15),
                    date_entered=date(2020, 10, 15),
                    description="Set/Reset Deadlines: Expert Discovery due by 6/11/2021. (cf) (Entered: 10/15/2020)",
                    short_description=None,
                ),
            ],
        )

        # Add initial docket entries.
        data = deepcopy(docket_data)
        async_to_sync(add_docket_entries)(self.d, data["docket_entries"])
        # 4 entries should be created.
        self.assertEqual(docket_entries.count(), 4)

        # Adapt docket entries to simulate docket history report entries
        # without duplicates.
        data_history = deepcopy(docket_data)
        docket_entries_history = data_history["docket_entries"][0:3]
        docket_entries_history[0][
            "short_description"
        ] = "Order on Motion for Extension of Time to Complete Discovery"
        docket_entries_history[1][
            "description"
        ] = "Set/Reset Deadlines: Expert Discovery due by 6/11/2021. (cf) (Entered: 10/15/2020)"
        docket_entries_history[2]["short_description"] = "Set/Reset Deadlines"
        # Merge docket history report entries.
        async_to_sync(add_docket_entries)(self.d, docket_entries_history)
        # Entries are properly merged removing the duplicated one.
        self.assertEqual(docket_entries.count(), 3)
        # Confirm entries were properly merged.
        for entry_db, entry in zip(docket_entries, docket_entries_history):
            self.assertEqual(entry_db.description, entry["description"])
            self.assertEqual(
                entry_db.recap_documents.all()[0].description,
                entry["short_description"],
            )
