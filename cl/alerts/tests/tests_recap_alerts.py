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
        cls.mock_date = now().replace(day=15, hour=0)
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
            cls.webhook_enabled = WebhookFactory(
                user=cls.user_profile.user,
                event_type=WebhookEventType.SEARCH_ALERT,
                url="https://example.com/",
                enabled=True,
            )
            cls.search_alert = AlertFactory(
                user=cls.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert Docket Only",
                query='q="401 Civil"&type=r',
            )
            cls.search_alert_2 = AlertFactory(
                user=cls.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert RECAP Only",
                query='q="Mauris iaculis, leo sit amet hendrerit vehicula"&type=r',
            )
            cls.search_alert_3 = AlertFactory(
                user=cls.user_profile.user,
                rate=Alert.DAILY,
                name="Test Cross object",
                query="q=SUBPOENAS SERVED OFF Mauris iaculis&type=r",
            )

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

    def test_filter_out_alerts_to_send(self) -> None:
        """Test RECAP alerts hit can be properly filtered out according to
        their query and hits matched conditions.
        """

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")

        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
