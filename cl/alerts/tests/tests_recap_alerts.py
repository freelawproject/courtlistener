import datetime
from unittest import mock

import time_machine
from asgiref.sync import sync_to_async
from django.core import mail
from django.core.management import call_command
from django.utils.timezone import now

from cl.alerts.factories import AlertFactory
from cl.alerts.models import SEARCH_TYPES, Alert
from cl.alerts.utils import query_includes_rd_field, recap_document_hl_matched
from cl.api.factories import WebhookFactory
from cl.api.models import WebhookEventType
from cl.donate.models import NeonMembership
from cl.lib.elasticsearch_utils import do_es_sweep_alert_query
from cl.lib.test_helpers import RECAPSearchTestCase
from cl.search.documents import DocketSweepDocument
from cl.search.factories import (
    DocketEntryWithParentsFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.models import Docket
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.tests.utils import MockResponse
from cl.users.factories import UserProfileWithParentsFactory


class RECAPAlertsSweepIndexTest(
    RECAPSearchTestCase, ESIndexTestCase, TestCase
):
    """
    RECAP Alerts Sweep Index Tests
    """

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")
        cls.mock_date = now()
        with time_machine.travel(cls.mock_date, tick=False):
            super().setUpTestData()
            call_command(
                "cl_index_parent_and_child_docs",
                search_type=SEARCH_TYPES.RECAP,
                queue="celery",
                pk_offset=0,
                testing_mode=True,
                sweep_index=True,
            )

            cls.user_profile = UserProfileWithParentsFactory()
            NeonMembership.objects.create(
                level=NeonMembership.LEGACY, user=cls.user_profile.user
            )
            cls.user_profile_2 = UserProfileWithParentsFactory()
            NeonMembership.objects.create(
                level=NeonMembership.LEGACY, user=cls.user_profile_2.user
            )
            cls.user_profile_no_member = UserProfileWithParentsFactory()
            cls.webhook_enabled = WebhookFactory(
                user=cls.user_profile.user,
                event_type=WebhookEventType.SEARCH_ALERT,
                url="https://example.com/",
                enabled=True,
            )

    @staticmethod
    def get_html_content_from_email(email_content):
        html_content = None
        for content, content_type in email_content.alternatives:
            if content_type == "text/html":
                html_content = content
                break
        return html_content

    async def test_recap_document_hl_matched(self) -> None:
        """Test recap_document_hl_matched method that determines weather a hit
        contains RECAPDocument HL fields."""
        # Docket-only query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": '"401 Civil"',
        }
        search_query = DocketSweepDocument.search()
        results, total_hits = await sync_to_async(do_es_sweep_alert_query)(
            search_query,
            search_params,
        )
        docket_result = results[0]
        for rd in docket_result["child_docs"]:
            rd_field_matched = recap_document_hl_matched(rd)
            self.assertEqual(rd_field_matched, False)

        # RECAPDocument-only query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": '"Mauris iaculis, leo sit amet hendrerit vehicula"',
        }
        search_query = DocketSweepDocument.search()
        results, total_hits = await sync_to_async(do_es_sweep_alert_query)(
            search_query,
            search_params,
        )
        docket_result = results[0]
        for rd in docket_result["child_docs"]:
            rd_field_matched = recap_document_hl_matched(rd)
            self.assertEqual(rd_field_matched, True)

        # Cross-object query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED OFF Mauris iaculis",
        }
        search_query = DocketSweepDocument.search()
        results, total_hits = await sync_to_async(do_es_sweep_alert_query)(
            search_query,
            search_params,
        )
        docket_result = results[0]
        for rd in docket_result["child_docs"]:
            rd_field_matched = recap_document_hl_matched(rd)
            self.assertEqual(rd_field_matched, True)

    async def test_query_includes_rd_field(self) -> None:
        """Test query_includes_rd_field method that checks if a query
        includes any indexed fields in the query string or filters specific to
        RECAP Documents.
        """

        # Docket-only query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": '"401 Civil"',
        }
        self.assertEqual(query_includes_rd_field(search_params), False)

        # RECAPDocument-only query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": 'description:"lorem ipsum"',
        }
        self.assertEqual(query_includes_rd_field(search_params), True)

        # Cross-object query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": 'case_name:"American v." description:"lorem ipsum"',
        }
        self.assertEqual(query_includes_rd_field(search_params), True)

        # Docket-only query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "",
            "case_name": "SUBPOENAS",
        }
        self.assertEqual(query_includes_rd_field(search_params), False)

        # RECAPDocument-only query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "",
            "description": "Lorem",
        }
        self.assertEqual(query_includes_rd_field(search_params), True)

        # Cross-object query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "",
            "case_name": "SUBPOENAS",
            "document_number": 1,
        }
        self.assertEqual(query_includes_rd_field(search_params), True)

    def test_filter_recap_alerts_to_send(self) -> None:
        """Test filter RECAP alerts that met the conditions to be sent:
        - RECAP type alert.
        - RT or DLY rate
        - For RT rate the user must have an active membership.
        """

        rt_recap_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test RT RECAP Alert",
            query='q="401 Civil"&type=r',
        )
        dly_recap_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.DAILY,
            name="Test DLY RECAP Alert",
            query='q="401 Civil"&type=r',
        )
        AlertFactory(
            user=self.user_profile_2.user,
            rate=Alert.REAL_TIME,
            name="Test RT Opinion Alert",
            query='q="401 Civil"',
        )
        AlertFactory(
            user=self.user_profile_no_member.user,
            rate=Alert.REAL_TIME,
            name="Test RT RECAP Alert no Member",
            query='q="401 Civil"&type=r',
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")

        # Only the RECAP RT alert for a member and the RECAP DLY alert are sent.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(rt_recap_alert.name, html_content)

        html_content = self.get_html_content_from_email(mail.outbox[1])
        self.assertIn(dly_recap_alert.name, html_content)

    def test_filter_out_alerts_to_send_by_query_and_hits(self) -> None:
        """Test RECAP alerts can be properly filtered out according to
        their query and hits matched conditions.

        - Docket-only Alerts should be triggered only if the Docket was
          modified on the day. This prevents sending Alerts due to related
          RDs added on the same day which can match the query due to parent
          fields indexed into the RDs.
            - The Docket or RD shouldn’t have triggered the alert previously.
            - RECAP-only Alerts should only include RDs that have not triggered the
              same alert previously. If there are no hits after filtering RDs,
              don’t send the alert.
            - Cross-object queries should only include RDs that have not triggered
              the same alert previously. If there are no hits after filtering RDs,
              don’t send the alert.

        Assert the content structure accordingly.
        """

        # This docket-only alert, matches a Docket added today.

        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only",
            query='q="401 Civil"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(docket_only_alert.name, html_content)

        # This test shouldn't match the Docket-only alert when the RD is added
        # today since its parent Docket was not modified today.
        AlertFactory(
            user=self.user_profile_2.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only Not Triggered",
            query='q="405 Civil"&type=r',
        )
        one_day_before = now() - datetime.timedelta(days=1)
        mock_date = one_day_before.replace(hour=5)
        with time_machine.travel(mock_date, tick=False):
            docket = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED CASE",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                docket_number="1:21-bk-1234",
                nature_of_suit="440",
                source=Docket.RECAP,
                cause="405 Civil",
                jurisdiction_type="'U.S. Government Defendant",
                jury_demand="1,000,000",
            )

        mock_date = now().replace(hour=5)
        with time_machine.travel(mock_date, tick=False):
            de = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd = RECAPDocumentFactory(
                docket_entry=de,
                description="Motion to File",
                document_number="1",
                is_available=True,
                page_count=5,
                pacer_doc_id="018036652436",
                plain_text="plain text for 018036652436",
            )

        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
            sweep_index=True,
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")
        # No new alert should be triggered.
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        recap_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only",
            query='q="plain text for 018036652436"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")
        # 1 New alert should be triggered.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

        # Trigger the alert again.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")
        # No new alert should be triggered.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

        # Create a new RD for the same DocketEntry.
        rd = RECAPDocumentFactory(
            docket_entry=de,
            description="Motion to File 2",
            document_number="2",
            is_available=True,
            page_count=3,
            pacer_doc_id="018036652436",
            plain_text="plain text for 018036652436",
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
            sweep_index=True,
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")

        # A new alert should be triggered containing only the new RD created.
        self.assertEqual(
            len(mail.outbox), 3, msg="Outgoing emails don't match."
        )

        recap_only_alert_2 = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only Docket Entry",
            query=f"q=docket_entry_id:{de.pk}&type=r",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")

        # A new alert should be triggered containing two RDs.
        self.assertEqual(
            len(mail.outbox), 4, msg="Outgoing emails don't match."
        )
