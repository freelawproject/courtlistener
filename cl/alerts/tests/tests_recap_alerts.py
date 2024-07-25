import datetime
from unittest import mock

import time_machine
from asgiref.sync import sync_to_async
from django.core import mail
from django.core.management import call_command
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.timezone import now
from elasticsearch_dsl import Q, connections

from cl.alerts.factories import AlertFactory
from cl.alerts.management.commands.cl_send_recap_alerts import (
    index_daily_recap_documents,
)
from cl.alerts.models import (
    SCHEDULED_ALERT_HIT_STATUS,
    SEARCH_TYPES,
    Alert,
    ScheduledAlertHit,
)
from cl.alerts.utils import (
    avoid_indexing_auxiliary_alert,
    build_plain_percolator_query,
    percolate_document,
    prepare_percolator_content,
    recap_document_hl_matched,
)
from cl.api.factories import WebhookFactory
from cl.api.models import WebhookEvent, WebhookEventType
from cl.donate.models import NeonMembership
from cl.lib.elasticsearch_utils import do_es_sweep_alert_query
from cl.lib.redis_utils import get_redis_interface
from cl.lib.test_helpers import RECAPSearchTestCase
from cl.people_db.factories import (
    AttorneyFactory,
    AttorneyOrganizationFactory,
    PartyFactory,
    PartyTypeFactory,
)
from cl.search.documents import (
    DocketDocument,
    DocketDocumentPercolator,
    ESRECAPDocumentPlain,
    RECAPDocumentPercolator,
    RECAPPercolator,
    RECAPSweepDocument,
)
from cl.search.factories import (
    BankruptcyInformationFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.models import Docket
from cl.search.tasks import index_docket_parties_in_es
from cl.tests.cases import ESIndexTestCase, RECAPAlertsAssertions, TestCase
from cl.tests.utils import MockResponse
from cl.users.factories import UserProfileWithParentsFactory


@mock.patch(
    "cl.alerts.utils.get_alerts_set_prefix",
    return_value="alert_hits_sweep",
)
class RECAPAlertsSweepIndexTest(
    RECAPSearchTestCase, ESIndexTestCase, TestCase, RECAPAlertsAssertions
):
    """
    RECAP Alerts Sweep Index Tests
    """

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")
        cls.mock_date = now()
        with time_machine.travel(
            cls.mock_date, tick=False
        ), cls.captureOnCommitCallbacks(execute=True):
            super().setUpTestData()

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

    def setUp(self):
        self.r = get_redis_interface("CACHE")
        self.r.delete("alert_sweep:query_date")
        self.r.delete("alert_sweep:task_id")
        keys = self.r.keys("alert_hits_sweep:*")
        if keys:
            self.r.delete(*keys)

    async def test_recap_document_hl_matched(self, mock_prefix) -> None:
        """Test recap_document_hl_matched method that determines weather a hit
        contains RECAPDocument HL fields."""

        # Index base document factories.
        with time_machine.travel(self.mock_date, tick=False):
            index_daily_recap_documents(
                self.r,
                DocketDocument._index._name,
                RECAPSweepDocument,
                testing=True,
            )

        # Docket-only query
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": '"401 Civil"',
        }
        search_query = RECAPSweepDocument.search()
        results, parent_results, _ = await sync_to_async(
            do_es_sweep_alert_query
        )(
            search_query,
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
        search_query = RECAPSweepDocument.search()
        results, parent_results, _ = await sync_to_async(
            do_es_sweep_alert_query
        )(
            search_query,
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
        search_query = RECAPSweepDocument.search()
        results, parent_results, _ = await sync_to_async(
            do_es_sweep_alert_query
        )(
            search_query,
            search_query,
            search_params,
        )
        docket_result = results[0]
        for rd in docket_result["child_docs"]:
            rd_field_matched = recap_document_hl_matched(rd)
            self.assertEqual(rd_field_matched, True)

    def test_filter_recap_alerts_to_send(self, mock_prefix) -> None:
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
            name="Test RT RECAP Alert",
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
        ):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # Only the RECAP RT alert for a member and the RECAP DLY alert are sent.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(rt_recap_alert.name, html_content)

        html_content = self.get_html_content_from_email(mail.outbox[1])
        self.assertIn(dly_recap_alert.name, html_content)

    def test_index_daily_recap_documents(self, mock_prefix) -> None:
        """Test index_daily_recap_documents method over different documents
        conditions.
        """
        RECAPSweepDocument._index.delete(ignore=404)
        RECAPSweepDocument.init()
        recap_search = DocketDocument.search()
        recap_dockets = recap_search.query(Q("match", docket_child="docket"))
        self.assertEqual(recap_dockets.count(), 2)

        recap_documents = recap_search.query(
            Q("match", docket_child="recap_document")
        )
        self.assertEqual(recap_documents.count(), 3)

        sweep_search = RECAPSweepDocument.search()
        self.assertEqual(
            sweep_search.count(),
            0,
            msg="Wrong number of documents in the sweep index.",
        )

        # Index documents based Dockets changed today + all their
        # RECAPDocuments indexed the same day.
        with time_machine.travel(self.mock_date, tick=False):
            documents_indexed = index_daily_recap_documents(
                self.r,
                DocketDocument._index._name,
                RECAPSweepDocument,
                testing=True,
            )
        self.assertEqual(
            documents_indexed, 5, msg="Wrong number of documents indexed."
        )

        sweep_search = RECAPSweepDocument.search()
        dockets_sweep = sweep_search.query(Q("match", docket_child="docket"))
        self.assertEqual(dockets_sweep.count(), 2)

        documents_sweep = sweep_search.query(
            Q("match", docket_child="recap_document")
        )
        self.assertEqual(documents_sweep.count(), 3)

        # Index Docket changed today + their RECAPDocuments indexed on
        # previous days
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED CASE",
                docket_number="1:21-bk-1234",
                source=Docket.RECAP,
            )

        # Its related RD is ingested two days before.
        two_days_before = now() - datetime.timedelta(days=2)
        mock_two_days_before = two_days_before.replace(hour=5)
        with time_machine.travel(
            mock_two_days_before, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File",
                document_number="1",
                is_available=True,
            )

        # Run the indexer.
        with time_machine.travel(self.mock_date, tick=False):
            documents_indexed = index_daily_recap_documents(
                self.r,
                DocketDocument._index._name,
                RECAPSweepDocument,
                testing=True,
            )
        self.assertEqual(
            documents_indexed, 7, msg="Wrong number of documents indexed."
        )

        # Index a RECAPDocument changed today including its parent Docket
        # indexed on previous days.
        with time_machine.travel(
            mock_two_days_before, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            docket_2 = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED CASE OFF",
                docket_number="1:21-bk-1250",
                source=Docket.RECAP,
            )

        # Its related RD is ingested today.
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de_2 = DocketEntryWithParentsFactory(
                docket=docket_2,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd_2 = RECAPDocumentFactory(
                docket_entry=alert_de_2,
                description="Motion to File Lorem",
                document_number="2",
            )

        # Run the indexer.
        with time_machine.travel(self.mock_date, tick=False):
            documents_indexed = index_daily_recap_documents(
                self.r,
                DocketDocument._index._name,
                RECAPSweepDocument,
                testing=True,
            )
        self.assertEqual(
            documents_indexed, 9, msg="Wrong number of documents indexed."
        )

        # Docket and RD created on previous days, will be used later to confirm
        # documents got indexed into the sweep index after partial updates.
        three_days_before = now() - datetime.timedelta(days=5)
        mock_three_days_before = three_days_before.replace(hour=5)
        with time_machine.travel(
            mock_three_days_before, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            docket_old = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED LOREM OFF",
                docket_number="1:21-bk-1254",
                source=Docket.RECAP,
            )
            alert_de_old = DocketEntryWithParentsFactory(
                docket=docket_old,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd_old = RECAPDocumentFactory(
                docket_entry=alert_de_old,
                description="Motion to File",
                document_number="1",
                is_available=True,
            )
            rd_old_2 = RECAPDocumentFactory(
                docket_entry=alert_de_old,
                description="Motion to File 2",
                document_number="2",
                is_available=True,
            )

        # Run the indexer. No new documents re_indexed.
        with time_machine.travel(self.mock_date, tick=False):
            documents_indexed = index_daily_recap_documents(
                self.r,
                DocketDocument._index._name,
                RECAPSweepDocument,
                testing=True,
            )
        self.assertEqual(
            documents_indexed, 9, msg="Wrong number of documents indexed."
        )

        # Update the documents today:
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            rd_old_2.document_number = 3
            rd_old_2.save()

        # Run the indexer. No new documents re_indexed.
        with time_machine.travel(self.mock_date, tick=False):
            documents_indexed = index_daily_recap_documents(
                self.r,
                DocketDocument._index._name,
                RECAPSweepDocument,
                testing=True,
            )
        self.assertEqual(
            documents_indexed, 11, msg="Wrong number of documents indexed."
        )

        # Update the Docket today:
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            docket_old.case_name = "SUBPOENAS SERVED LOREM OFF UPDATED"
            docket_old.save()

        # Run the indexer. No new documents re_indexed.
        with time_machine.travel(self.mock_date, tick=False):
            documents_indexed = index_daily_recap_documents(
                self.r,
                DocketDocument._index._name,
                RECAPSweepDocument,
                testing=True,
            )
        self.assertEqual(
            documents_indexed, 12, msg="Wrong number of documents indexed."
        )

        docket_old.delete()
        docket.delete()
        docket_2.delete()

    def test_filter_out_alerts_to_send_by_query_and_hits(
        self, mock_prefix
    ) -> None:
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

        # This docket-only alert matches a Docket ingested today.
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
            call_command("cl_send_recap_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        # The docket-only alert doesn't contain any nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            docket_only_alert.name,
            1,
            self.de.docket.case_name,
            0,
        )

        # Assert email text version:
        txt_email = mail.outbox[0].body
        self.assertIn(docket_only_alert.name, txt_email)

        # The following test shouldn't match the Docket-only alert when the RD
        # is added today since its parent Docket was not modified today.
        AlertFactory(
            user=self.user_profile_2.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only Not Triggered",
            query='q="405 Civil"&type=r',
        )
        # Simulate docket is ingested a day before.
        one_day_before = self.mock_date - datetime.timedelta(days=1)
        with time_machine.travel(
            one_day_before, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
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

        # Its related RD is ingested today.
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File",
                document_number="1",
                is_available=True,
                page_count=5,
                pacer_doc_id="018036652436",
                plain_text="plain text for 018036652436",
            )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)
        # The RD ingestion's shouldn't match the docket-only alert.
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        # Test a RECAP-only alert query.
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
            call_command("cl_send_recap_alerts", testing_mode=True)
        # 1 New alert should be triggered.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[1])
        self._confirm_number_of_alerts(html_content, 1)
        # Only one child hit should be included in the case within the alert.
        self._count_alert_hits_and_child_hits(
            html_content,
            recap_only_alert.name,
            1,
            alert_de.docket.case_name,
            1,
        )
        self._assert_child_hits_content(
            html_content,
            recap_only_alert.name,
            alert_de.docket.case_name,
            [rd.description],
        )
        # Assert email text version:
        txt_email = mail.outbox[1].body
        self.assertIn(recap_only_alert.name, txt_email)
        self.assertIn(rd.description, txt_email)

        # Trigger the same alert again to confirm that no new alert is
        # triggered because previous hits have already triggered the same alert
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)
        # No new alert should be triggered.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            # Create a new RD for the same DocketEntry to confirm this new RD is
            # properly included in the alert email.
            rd_2 = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File 2",
                document_number="2",
                is_available=True,
                page_count=3,
                pacer_doc_id="018036652436",
                plain_text="plain text for 018036652436",
            )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # A new alert should be triggered containing only the new RD created.
        self.assertEqual(
            len(mail.outbox), 3, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[2])
        self._confirm_number_of_alerts(html_content, 1)
        self._assert_child_hits_content(
            html_content,
            recap_only_alert.name,
            alert_de.docket.case_name,
            [rd_2.description],
        )

        # The following test confirms that hits previously matched with other
        # alerts can match a different alert.
        recap_only_alert_2 = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only Docket Entry",
            query=f"q=docket_entry_id:{alert_de.pk}&type=r",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # A new alert should be triggered containing two RDs (rd and rd_2)
        self.assertEqual(
            len(mail.outbox), 4, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[3])
        self._confirm_number_of_alerts(html_content, 1)
        self._assert_child_hits_content(
            html_content,
            recap_only_alert_2.name,
            alert_de.docket.case_name,
            [rd.description, rd_2.description],
        )
        # Assert email text version:
        txt_email = mail.outbox[3].body
        self.assertIn(recap_only_alert.name, txt_email)
        self.assertIn(rd.description, txt_email)
        self.assertIn(rd_2.description, txt_email)

        # The following test confirms that a cross-object alert is properly
        # matched and triggered
        cross_object_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object query",
            query=f'q="Motion to File 2"&docket_number={docket.docket_number}&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # A new alert should be triggered containing one RD (rd_2)
        self.assertEqual(
            len(mail.outbox), 5, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[4])
        self._confirm_number_of_alerts(html_content, 1)
        self._assert_child_hits_content(
            html_content,
            cross_object_alert.name,
            alert_de.docket.case_name,
            [rd_2.description],
        )
        # Assert email text version:
        txt_email = mail.outbox[4].body
        self.assertIn(cross_object_alert.name, txt_email)
        self.assertIn(rd_2.description, txt_email)

        docket.delete()

    def test_special_cross_object_alerts_or_clause(self, mock_prefix) -> None:
        """This test confirms that hits are properly filtered out or included
        in alerts for special cross-object alerts that can match either a
        Docket-only hit and/or Docket + RDs simultaneously in the same hit.
        These cases include queries that use an OR clause combining
        Docket field + RD fields.
        """

        # The following test confirms that an alert with a query that can match
        # a Docket or RECAPDocuments from different cases simultaneously are
        # properly filtered.
        cross_object_alert_d_or_rd_field = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object query",
            query=f"q=docket_id:{self.de.docket.pk} OR pacer_doc_id:{self.rd_2.pacer_doc_id}&type=r",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # A new alert should be triggered containing a Docket-only hit and a
        # Docket with the nested RD matched.
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self._confirm_number_of_alerts(html_content, 1)

        # This hit should only display the Docket matched by its ID,
        # no RECAPDocument should be matched.
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_d_or_rd_field.name,
            2,
            self.de.docket.case_name,
            0,
        )
        # The second hit should display the rd_2 nested below its parent docket.
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_d_or_rd_field.name,
            self.de_1.docket.case_name,
            [self.rd_2.description],
        )
        # Assert email text version:
        txt_email = mail.outbox[0].body
        self.assertIn(cross_object_alert_d_or_rd_field.name, txt_email)
        self.assertIn(self.rd_2.description, txt_email)

        # This test confirms that we're able to trigger cross-object alerts
        # that include an OR clause and match documents that belong to the
        # same case.
        cross_object_alert_d_or_rd_field_same_case = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object query",
            query=f"q=docket_id:{self.de.docket.pk} OR pacer_doc_id:{self.rd.pacer_doc_id}&type=r",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # A new alert should be triggered, containing the RD document nested
        # below its parent docket.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[1])
        self._confirm_number_of_alerts(html_content, 1)
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_d_or_rd_field.name,
            1,
            self.de.docket.case_name,
            1,
        )
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_d_or_rd_field_same_case.name,
            self.de.docket.case_name,
            [self.rd.description],
        )

    def test_special_cross_object_alerts_text_query(self, mock_prefix) -> None:
        """This test confirms that hits are properly filtered out or included
        in alerts for special cross-object alerts that can match either a
        Docket-only hit and/or Docket + RDs simultaneously in the same hit.
        These cases include queries that use a text query that can match a
        Docket and RD field simultaneously.
        """

        # This test confirms a text query cross-object alert matches documents
        # according to trigger conditions like indexed date and previous triggers
        # by the same document.
        cross_object_alert_text = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object text query",
            query=f'q="United states"&type=r',
        )
        two_days_before = self.mock_date - datetime.timedelta(days=2)
        mock_two_days_before = two_days_before.replace(hour=5)
        with time_machine.travel(
            mock_two_days_before, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="United States of America",
                docket_number="1:21-bk-1009",
                source=Docket.RECAP,
            )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # No alert should be triggered since the matched docket was not
        # modified during the current day.
        self.assertEqual(
            len(mail.outbox), 0, msg="Outgoing emails don't match."
        )

        # Index new documents that match cross_object_alert_text, an RD, and
        # an empty docket.
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File",
            )
            rd_3 = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File New",
                document_number="2",
                pacer_doc_id="018036652875",
                plain_text="United states Lorem",
            )

            docket_2 = DocketFactory(
                court=self.court,
                case_name="United States vs Lorem",
                docket_number="1:21-bk-1008",
                source=Docket.RECAP,
            )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # An alert should be triggered containing two hits. One matched by
        # the rd_3 plain text description and one matched by docket_2 case_name
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self._confirm_number_of_alerts(html_content, 1)
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_text.name,
            2,
            docket.case_name,
            1,
        )
        # rd_3 should appear nested in this hit.
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_text.name,
            docket.case_name,
            [rd_3.description],
        )
        # The docket_2 hit shouldn't contain RDs.
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_text.name,
            docket_2.case_name,
            [],
        )
        # Modify 1:21-bk-1009 docket today:
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            docket.cause = "405 Civil"
            docket.save()

        # Trigger the alert again:
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # A new alert should be triggered containing the docket as a hit with
        # no nested RDs.
        html_content = self.get_html_content_from_email(mail.outbox[1])
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        self._confirm_number_of_alerts(html_content, 1)
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_text.name,
            1,
            docket.case_name,
            0,
        )
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_text.name,
            docket.case_name,
            [],
        )

        # Trigger alert again:
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)
        # No new alerts should be triggered.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

        # Index new documents that match cross_object_alert_text, an RD, and
        # an empty docket.
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            rd_4 = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Hearing new",
                document_number="3",
                pacer_doc_id="0180366528790",
                plain_text="Lorem ipsum",
            )
            rd_5 = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Hearing new 2",
                document_number="4",
                pacer_doc_id="018026657750",
                plain_text="United states of america plain text",
            )

        # This test confirms that we're able to trigger cross-object alerts
        # that include an OR clause and a cross-object text query.
        cross_object_alert_d_or_rd_field_text_query = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object query combined.",
            query=f"q=docket_id:{self.de.docket.pk} OR "
            f"pacer_doc_id:{self.rd.pacer_doc_id} OR "
            f'("United States of America" OR '
            f"pacer_doc_id:{rd_3.pacer_doc_id})&type=r",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # A new alert should be triggered, containing the RD document nested below
        # its parent docket.
        html_content = self.get_html_content_from_email(mail.outbox[2])
        self.assertEqual(
            len(mail.outbox), 3, msg="Outgoing emails don't match."
        )
        # The email contains two alerts: one for cross_object_alert_text
        # triggered by the new rd_5 added, and one for cross_object_alert_d_or_rd_field_text_query.
        self._confirm_number_of_alerts(html_content, 2)
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_text.name,
            1,
            docket.case_name,
            1,
        )
        # The cross_object_alert_d_or_rd_field_text_query alert contains two
        # hits. The first one matches "docket" and rd_3 and rd_5 nested below
        # due to the OR clause in the text query, and the second hit matches
        # self.de.docket and self.rd.
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_d_or_rd_field_text_query.name,
            2,
            docket.case_name,
            2,
        )
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_d_or_rd_field_text_query.name,
            docket.case_name,
            [rd_3.description, rd_5.description],
        )
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_d_or_rd_field_text_query.name,
            self.de.docket.case_name,
            [self.rd.description],
        )

        # This test confirms that hits are properly filtered when using AND in
        # the text query.
        cross_object_alert_d_or_rd_field_text_query_and = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object query combined.",
            query=f'q=("United States of America" AND '
            f"pacer_doc_id:{rd_3.pacer_doc_id})&type=r",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # A new alert should be triggered, containing rd_3 document nested below
        # its parent docket.
        html_content = self.get_html_content_from_email(mail.outbox[3])
        self.assertEqual(
            len(mail.outbox), 4, msg="Outgoing emails don't match."
        )
        self._confirm_number_of_alerts(html_content, 1)
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_d_or_rd_field_text_query_and.name,
            1,
            docket.case_name,
            1,
        )
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_d_or_rd_field_text_query_and.name,
            docket.case_name,
            [rd_3.description],
        )

        docket.delete()
        docket_2.delete()

    def test_limit_alert_case_child_hits(self, mock_prefix) -> None:
        """Test limit case child hits up to 5 and display the "View additional
        results for this Case" button.
        """

        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de = DocketEntryWithParentsFactory(
                docket=self.de.docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd_descriptions = []
            for i in range(6):
                rd = RECAPDocumentFactory(
                    docket_entry=alert_de,
                    description=f"Motion to File {i+1}",
                    document_number=f"{i+1}",
                    pacer_doc_id=f"018036652436{i+1}",
                )
                if i < 5:
                    # Omit the last alert to compare. Only up to 5 should be
                    # included in the case.
                    rd_descriptions.append(rd.description)

        recap_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only Docket Entry",
            query=f"q=docket_entry_id:{alert_de.pk}&type=r",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            call_command("cl_send_recap_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(recap_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        # The case alert should contain up to 5 child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            recap_only_alert.name,
            1,
            self.de.docket.case_name,
            5,
        )
        self._assert_child_hits_content(
            html_content,
            recap_only_alert.name,
            alert_de.docket.case_name,
            rd_descriptions,
        )
        # Assert the View more results button is present in the alert.
        self.assertIn("View Additional Results for this Case", html_content)

        # Assert email text version:
        txt_email = mail.outbox[0].body
        self.assertIn(recap_only_alert.name, txt_email)
        for description in rd_descriptions:
            with self.subTest(
                description=description, msg="Plain text descriptions"
            ):
                self.assertIn(
                    description,
                    txt_email,
                    msg="RECAPDocument wasn't found in the email content.",
                )

        self.assertIn("View Additional Results for this Case", txt_email)

        alert_de.delete()

    @override_settings(SCHEDULED_ALERT_HITS_LIMIT=3)
    def test_multiple_alerts_email_hits_limit_per_alert(
        self, mock_prefix
    ) -> None:
        """Test multiple alerts can be grouped in an email and hits within an
        alert are limited to SCHEDULED_ALERT_HITS_LIMIT (3) hits.
        """

        with self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name=f"SUBPOENAS SERVED CASE",
                docket_number=f"1:21-bk-123",
                source=Docket.RECAP,
                cause="410 Civil",
            )
            dockets_created = []
            for i in range(3):
                docket_created = DocketFactory(
                    court=self.court,
                    case_name=f"SUBPOENAS SERVED CASE {i}",
                    docket_number=f"1:21-bk-123{i}",
                    source=Docket.RECAP,
                    cause="410 Civil",
                )
                dockets_created.append(docket_created)

            alert_de = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File",
                document_number="1",
                pacer_doc_id="018036652439",
            )
            rd_2 = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File 2",
                document_number="2",
                pacer_doc_id="018036652440",
                plain_text="plain text lorem",
            )

        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only",
            query='q="410 Civil"&type=r',
        )
        recap_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only Docket Entry",
            query=f"q=docket_entry_id:{alert_de.pk}&type=r",
        )
        cross_object_alert_with_hl = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object",
            query=f'q="File Amicus Curiae" AND "Motion to File 2" AND '
            f'"plain text lorem" AND "410 Civil" AND '
            f"id:{rd_2.pk}&docket_number={docket.docket_number}"
            f'&case_name="{docket.case_name}"&type=r',
        )
        AlertFactory(
            user=self.user_profile_2.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object",
            query=f'q="File Amicus Curiae" AND "Motion to File 2" AND '
            f'"plain text lorem" AND "410 Civil" AND '
            f"id:{rd_2.pk}&docket_number={docket.docket_number}"
            f'&case_name="{docket.case_name}"&type=r',
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            call_command("cl_send_recap_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

        # Assert webhooks.
        webhook_events = WebhookEvent.objects.all().values_list(
            "content", flat=True
        )
        self.assertEqual(len(webhook_events), 3)
        # Assert docket-only alert.
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 3)
        # The docket-only alert doesn't contain any nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            docket_only_alert.name,
            3,
            docket.case_name,
            0,
        )
        self._count_webhook_hits_and_child_hits(
            list(webhook_events),
            docket_only_alert.name,
            3,
            docket.case_name,
            0,
        )

        # Assert RECAP-only alert.
        self.assertIn(recap_only_alert.name, html_content)
        # The recap-only alert contain 2 child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            recap_only_alert.name,
            1,
            alert_de.docket.case_name,
            2,
        )
        self._count_webhook_hits_and_child_hits(
            list(webhook_events),
            recap_only_alert.name,
            1,
            alert_de.docket.case_name,
            2,
        )
        self._assert_child_hits_content(
            html_content,
            recap_only_alert.name,
            alert_de.docket.case_name,
            [rd.description, rd_2.description],
        )

        # Assert Cross-object alert.
        self.assertIn(recap_only_alert.name, html_content)
        # The cross-object alert only contain 1 child hit.
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_with_hl.name,
            1,
            alert_de.docket.case_name,
            1,
        )
        self._count_webhook_hits_and_child_hits(
            list(webhook_events),
            cross_object_alert_with_hl.name,
            1,
            alert_de.docket.case_name,
            1,
        )
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_with_hl.name,
            alert_de.docket.case_name,
            [rd_2.description],
        )

        # Assert HL in the cross_object_alert_with_hl
        self.assertIn(f"<strong>{docket.case_name}</strong>", html_content)
        self.assertEqual(
            html_content.count(f"<strong>{docket.case_name}</strong>"), 1
        )
        self.assertIn(f"<strong>{docket.docket_number}</strong>", html_content)
        self.assertEqual(
            html_content.count(f"<strong>{docket.docket_number}</strong>"), 1
        )
        self.assertIn(f"<strong>{rd_2.plain_text}</strong>", html_content)
        self.assertEqual(
            html_content.count(f"<strong>{rd_2.plain_text}</strong>"), 1
        )
        self.assertIn(f"<strong>{rd_2.description}</strong>", html_content)
        self.assertEqual(
            html_content.count(f"<strong>{rd_2.description}</strong>"), 1
        )
        self.assertIn("<strong>File Amicus Curiae</strong>", html_content)
        self.assertEqual(
            html_content.count("<strong>File Amicus Curiae</strong>"), 1
        )

        # Assert HL content in webhooks.
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "caseName",
            f"<strong>{docket.case_name}</strong>",
            child_field=False,
        )
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "docketNumber",
            f"<strong>{docket.docket_number}</strong>",
            child_field=False,
        )
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "snippet",
            f"<strong>{rd_2.plain_text}</strong>",
            child_field=True,
        )
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "short_description",
            f"<strong>{rd_2.description}</strong>",
            child_field=True,
        )
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "description",
            "<strong>File Amicus Curiae</strong>",
            child_field=True,
        )

        # Assert email text version:
        txt_email = mail.outbox[0].body
        self.assertIn(recap_only_alert.name, txt_email)
        self.assertIn(docket_only_alert.name, txt_email)
        self.assertIn(cross_object_alert_with_hl.name, txt_email)
        for description in [rd.description, rd_2.description]:
            with self.subTest(
                description=description, msg="Plain text descriptions"
            ):
                self.assertIn(
                    description,
                    txt_email,
                    msg="RECAPDocument wasn't found in the email content.",
                )

        docket.delete()
        for d in dockets_created:
            d.delete()

    def test_schedule_wly_and_mly_recap_alerts(self, mock_prefix) -> None:
        """Test Weekly and Monthly RECAP Search Alerts are scheduled daily
        before being sent later.
        """

        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.WEEKLY,
            name="Test Alert Docket Only",
            query='q="401 Civil"&type=r',
        )
        recap_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.MONTHLY,
            name="Test Alert RECAP Only Docket Entry",
            query=f"q=docket_entry_id:{self.de.pk}&type=r",
        )
        cross_object_alert_with_hl = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.WEEKLY,
            name="Test Alert Cross-object",
            query=f'q="401 Civil" id:{self.rd.pk}&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            call_command("cl_send_recap_alerts", testing_mode=True)

        # Weekly and monthly alerts are not sent right away but are scheduled as
        # ScheduledAlertHit to be sent by the cl_send_scheduled_alerts command.
        self.assertEqual(
            len(mail.outbox), 0, msg="Outgoing emails don't match."
        )
        schedule_alerts = ScheduledAlertHit.objects.all()
        self.assertEqual(schedule_alerts.count(), 3)

        # Webhooks are send immediately as hits are matched.
        webhook_events = WebhookEvent.objects.all().values_list(
            "content", flat=True
        )
        self.assertEqual(len(webhook_events), 3)

        # Send scheduled Weekly alerts and check assertions.
        call_command("cl_send_scheduled_alerts", rate=Alert.WEEKLY)
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        # Assert docket-only alert.
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self._count_alert_hits_and_child_hits(
            html_content,
            docket_only_alert.name,
            1,
            self.de.docket.case_name,
            0,
        )
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_with_hl.name,
            1,
            self.de.docket.case_name,
            1,
        )
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_with_hl.name,
            self.de.docket.case_name,
            [self.rd.description],
        )
        # Assert email text version:
        txt_email = mail.outbox[0].body
        self.assertIn(docket_only_alert.name, txt_email)
        self.assertIn(cross_object_alert_with_hl.name, txt_email)
        self.assertIn(self.rd.description, txt_email)

        # Send  scheduled Monthly alerts and check assertions.
        call_command("cl_send_scheduled_alerts", rate=Alert.MONTHLY)
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[1])
        self._count_alert_hits_and_child_hits(
            html_content,
            recap_only_alert.name,
            1,
            self.de.docket.case_name,
            2,
        )
        self._assert_child_hits_content(
            html_content,
            recap_only_alert.name,
            self.de.docket.case_name,
            [self.rd.description, self.rd_att.description],
        )
        # Assert email text version:
        txt_email = mail.outbox[1].body
        self.assertIn(recap_only_alert.name, txt_email)
        self.assertIn(self.rd.description, txt_email)
        self.assertIn(self.rd_att.description, txt_email)

    def test_alert_frequency_estimation(self, mock_prefix) -> None:
        """Test alert frequency ES API endpoint for RECAP Alerts."""

        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Frequency Test RECAP",
        }
        r = self.client.get(
            reverse(
                "alert_frequency", kwargs={"version": "4", "day_count": "100"}
            ),
            search_params,
        )
        self.assertEqual(r.json()["count"], 0)
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            # Docket filed today.
            docket = DocketFactory(
                court=self.court,
                case_name="Frequency Test RECAP",
                docket_number="1:21-bk-1240",
                source=Docket.RECAP,
                date_filed=now().date(),
            )

            # RECAPDocument filed today that belongs to a docket filed outside
            # the estimation range.
            date_outside_range = now() - datetime.timedelta(days=102)
            alert_de = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court,
                    case_name="Frequency Test RECAP",
                    docket_number="1:21-bk-1245",
                    source=Docket.RECAP,
                    date_filed=date_outside_range.date(),
                ),
                entry_number=1,
                date_filed=now().date(),
            )
            RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Frequency Test RECAP",
                document_number="1",
                pacer_doc_id="018036652450",
            )

        r = self.client.get(
            reverse(
                "alert_frequency", kwargs={"version": "4", "day_count": "100"}
            ),
            search_params,
        )
        # 2 expected hits in the last 100 days. One docket filed today + one
        # RECAPDocument filed today.
        self.assertEqual(r.json()["count"], 2)

        docket.delete()
        alert_de.docket.delete()

    @override_settings(PERCOLATOR_SEARCH_ALERTS_ENABLED=True)
    def test_percolator_plus_sweep_alerts_integration(
        self, mock_prefix
    ) -> None:
        """Integration test to confirm alerts missing by the percolator approach
        are properly send by the sweep index without duplicating alerts.
        """

        # Rename percolator index for this test to avoid collisions.
        RECAPPercolator._index._name = "recap_percolator_sweep"
        RECAPPercolator._index.delete(ignore=404)
        RECAPPercolator.init()
        RECAPDocumentPercolator._index._name = "recap_doc_percolator_sweep"
        RECAPDocumentPercolator._index.delete(ignore=404)
        RECAPDocumentPercolator.init()
        DocketDocumentPercolator._index._name = "docket_doc_percolator_sweep"
        DocketDocumentPercolator._index.delete(ignore=404)
        DocketDocumentPercolator.init()

        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only",
            query='q="410 Civil"&type=r',
        )
        cross_object_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object",
            query=f'q=pacer_doc_id:0190645981 AND "SUBPOENAS SERVED CASE"&type=r',
        )
        cross_object_alert_after_update = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object 2",
            query=f'q=pacer_doc_id:0190645981 AND "SUBPOENAS SERVED CASE UPDATED"&type=r',
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name=f"SUBPOENAS SERVED CASE",
                docket_number=f"1:21-bk-227",
                source=Docket.RECAP,
                cause="410 Civil",
            )
            alert_de = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )

            rd_1 = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File 1",
                document_number="1",
                pacer_doc_id="0190645981",
                plain_text="plain text lorem",
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        # Assert webhooks.
        webhook_events = WebhookEvent.objects.all().values_list(
            "content", flat=True
        )
        # 2 webhooks should be triggered one for each document ingested that
        # matched each alert.
        self.assertEqual(
            len(webhook_events), 2, msg="Webhook events didn't match."
        )

        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 2)
        # The docket-only alert doesn't contain any nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            docket_only_alert.name,
            1,
            docket.case_name,
            0,
        )

        # The cross_object_alert-only alert contain q nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert.name,
            1,
            docket.case_name,
            1,
        )

        # Now update the docket case_name to match cross_object_alert_after_update
        with time_machine.travel(self.mock_date, tick=False), mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            docket.case_name = "SUBPOENAS SERVED CASE UPDATED"
            docket.save()

        # No new alerts triggered by the percolator.
        # cross_object_alert_after_update alert is missed by the percolator.
        # due to the related RECAPDocument is not being percolated after the
        # Docket field update.
        call_command("cl_send_rt_percolator_alerts", testing_mode=True)
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        # The missing alert should be sent by the Sweep index alert approach.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

        # Assert webhooks.
        webhook_events = WebhookEvent.objects.all().values_list(
            "content", flat=True
        )
        # 3 webhooks should be triggered one for each document ingested that
        # matched each alert.
        self.assertEqual(
            len(webhook_events), 3, msg="Webhook events didn't match."
        )

        html_content = self.get_html_content_from_email(mail.outbox[1])
        self.assertIn(cross_object_alert_after_update.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)

        # The cross_object_alert_after_update alert contain 1 nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_after_update.name,
            1,
            docket.case_name,
            1,
        )

        docket.delete()


@override_settings(PERCOLATOR_SEARCH_ALERTS_ENABLED=True)
@mock.patch(
    "cl.alerts.utils.get_alerts_set_prefix",
    return_value="alert_hits_percolator",
)
class RECAPAlertsPercolatorTest(
    RECAPSearchTestCase, ESIndexTestCase, TestCase, RECAPAlertsAssertions
):
    """
    RECAP Alerts Percolator Tests
    """

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")
        cls.mock_date = now()
        with time_machine.travel(cls.mock_date, tick=False):
            super().setUpTestData()
            cls.docket_3 = DocketFactory(
                court=cls.court,
                case_name="SUBPOENAS SERVED OFF",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                docket_number="1:21-bk-1235",
                nature_of_suit="440",
                source=Docket.RECAP,
                cause="405 Civil",
                jurisdiction_type="'U.S. Government Defendant",
                jury_demand="1,000,000",
            )
            call_command(
                "cl_index_parent_and_child_docs",
                search_type=SEARCH_TYPES.RECAP,
                queue="celery",
                pk_offset=0,
                testing_mode=True,
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

    def setUp(self):
        RECAPPercolator._index.delete(ignore=404)
        RECAPPercolator.init()
        RECAPDocumentPercolator._index.delete(ignore=404)
        RECAPDocumentPercolator.init()
        DocketDocumentPercolator._index.delete(ignore=404)
        DocketDocumentPercolator.init()
        self.r = get_redis_interface("CACHE")
        keys = self.r.keys("alert_hits_percolator:*")
        if keys:
            self.r.delete(*keys)

    @staticmethod
    def confirm_query_matched(response, query_id) -> bool:
        """Confirm if a percolator query matched."""

        matched = False
        for hit in response:
            if hit.meta.id == query_id:
                matched = True
        return matched

    @staticmethod
    def save_percolator_query(cd):
        query = build_plain_percolator_query(cd)
        query_dict = query.to_dict()
        percolator_query = RECAPPercolator(
            percolator_query=query_dict,
            rate=Alert.REAL_TIME,
            date_created=now(),
        )
        percolator_query.save(refresh=True)

        if not avoid_indexing_auxiliary_alert(
            DocketDocumentPercolator.__name__, cd
        ):
            d_percolator_query = DocketDocumentPercolator(
                percolator_query=query_dict,
                rate=Alert.REAL_TIME,
                date_created=now(),
            )
            d_percolator_query.save(refresh=True)
        if not avoid_indexing_auxiliary_alert(
            RECAPDocumentPercolator.__name__, cd
        ):
            rd_percolator_query = RECAPDocumentPercolator(
                percolator_query=query_dict,
                rate=Alert.REAL_TIME,
                date_created=now(),
            )
            rd_percolator_query.save(refresh=True)
        return percolator_query.meta.id

    @staticmethod
    def prepare_and_percolate_document(app_label, document_id):
        percolator_index, es_document_index, document_content = (
            prepare_percolator_content(app_label, document_id, None)
        )
        responses = percolate_document(
            str(document_id),
            percolator_index,
            es_document_index,
            document_content,
            app_label=app_label,
        )
        return responses

    @classmethod
    def delete_documents_from_index(cls, index_alias, queries):
        es_conn = connections.get_connection()
        for query_id in queries:
            es_conn.delete(index=index_alias, id=query_id)

    def test_recap_document_cross_object_percolator_queries(
        self, mock_prefix
    ) -> None:
        """Test if a variety of RECAPDocuments can trigger cross-object percolator
        queries"""

        created_queries_ids = []

        # Test Percolate a RECAPDocument. It should match the query containing
        # a Docket query terms + party filter + and RECAPDocument filter.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED ON",
            "attachment_number": "2",
            "party": "Defendant Jane Roe",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        app_label = "search.RECAPDocument"
        responses = self.prepare_and_percolate_document(
            app_label, str(self.rd_att.pk)
        )
        expected_queries = 1
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id), True
        )

        # Test Percolate a RECAPDocument. It should match the query containing
        # a Docket query terms and RECAPDocument filter.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED ON",
            "document_number": "1",
            "order_by": "score desc",
        }
        query_id_1 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_1)
        responses = self.prepare_and_percolate_document(
            app_label, str(self.rd.pk)
        )
        expected_queries = 1
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_1), True
        )

        # Test Percolate a RECAPDocument. It should match the query containing
        # Docket AND RD text query terms.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "(SUBPOENAS SERVED ON) AND (Amicus Curiae Lorem Served)",
            "order_by": "score desc",
        }
        query_id_2 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_2)
        responses = self.prepare_and_percolate_document(
            app_label, str(self.rd.pk)
        )
        expected_queries = 2
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_1), True
        )
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_2), True
        )

        # Test Percolate a RECAPDocument. It should match the query containing
        # Docket AND OR text query terms.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "(SUBPOENAS SERVED ON) OR (Amicus Curiae Lorem Served)",
            "order_by": "score desc",
        }
        query_id_3 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_3)
        responses = self.prepare_and_percolate_document(
            app_label, str(self.rd.pk)
        )
        expected_queries = 3
        self.assertEqual(
            len(responses[0]),
            expected_queries,
            msg="Wrong number of queries matched.",
        )
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_1), True
        )
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_2), True
        )
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_3), True
        )

    def test_recap_document_percolator(self, mock_prefix) -> None:
        """Test if a variety of RECAPDocument triggers a RD-only percolator
        query."""

        created_queries_ids = []
        # Test percolate text query + different filters.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": '"Mauris iaculis" AND pacer_doc_id:016156723121 AND '
            "entry_date_filed:[2014-07-18T00:00:00Z TO 2014-07-20T00:00:00Z]",
            "document_number": "3",
            "description": "Leave to File",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        app_label = "search.RECAPDocument"
        responses = self.prepare_and_percolate_document(
            app_label, str(self.rd_2.pk)
        )
        expected_queries = 1
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id), True
        )

        # Test percolate only filters combination.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "document_number": "1",
            "attachment_number": "2",
            "description": "Amicus Curiae",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        responses = self.prepare_and_percolate_document(
            app_label, str(self.rd_att.pk)
        )
        expected_queries = 1
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id), True
        )

        # Test percolate a different document targeting a different filters
        # combination.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Leave to File",
            "document_number": "1",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        responses = self.prepare_and_percolate_document(
            app_label, str(self.rd.pk)
        )
        expected_queries = 1
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id), True
        )

        # Test percolate the same document loosen the query.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Leave to File",
            "order_by": "score desc",
        }
        query_id_2 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_2)
        responses = self.prepare_and_percolate_document(
            app_label, str(self.rd.pk)
        )
        expected_queries = 2
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id), True
        )
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_2), True
        )

    def test_docket_percolator(self, mock_prefix) -> None:
        """Test if a variety of Docket documents triggers a percolator query."""

        document_index_alias = DocketDocument._index._name
        created_queries_ids = []

        # Test Percolate a docket object. It shouldn't match the query
        # containing a RECAPDocument filter
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED ON",
            "document_number": "1",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        responses = percolate_document(
            str(self.de.docket.pk),
            RECAPPercolator._index._name,
            document_index_alias,
        )
        expected_queries = 0
        self.assertEqual(len(responses[0]), expected_queries)

        # Test Percolate a docket object. It shouldn't match the query
        # containing text query terms contained only in a RD.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "(SUBPOENAS SERVED ON) AND (Amicus Curiae Lorem Served)",
            "order_by": "score desc",
        }
        query_id_1 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_1)
        responses = percolate_document(
            str(self.de.docket.pk),
            RECAPPercolator._index._name,
            document_index_alias,
        )
        expected_queries = 0
        self.assertEqual(len(responses[0]), expected_queries)

        # Test Percolate a docket object. Combining docket terms OR RECAPDocument
        # fields. This query can be triggered only by the Docket document.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "(SUBPOENAS SERVED ON) OR (Amicus Curiae Lorem Served)",
            "order_by": "score desc",
        }
        query_id_2 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_2)
        responses = percolate_document(
            str(self.de.docket.pk),
            RECAPPercolator._index._name,
            document_index_alias,
        )
        expected_queries = 1
        self.assertEqual(len(responses[0]), expected_queries, msg="error 1")
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_2), True
        )

        # Test percolate text query + different filters.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": 'cause:"401 Civil"',
            "case_name": "SUBPOENAS SERVED ON",
            "party": "Defendant Jane Roe",
            "filed_after": datetime.date(2015, 8, 16),
            "order_by": "score desc",
        }
        query_id_3 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_3)
        responses = percolate_document(
            str(self.de.docket.pk),
            RECAPPercolator._index._name,
            document_index_alias,
        )
        expected_queries = 2
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_2), True
        )
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_3), True
        )

        # Test percolate text query + case_name filter.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": '"405 Civil"',
            "case_name": "SUBPOENAS SERVED OFF",
            "order_by": "score desc",
        }
        query_id_4 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_4)
        responses = percolate_document(
            str(self.docket_3.pk),
            RECAPPercolator._index._name,
            document_index_alias,
        )
        expected_queries = 1
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_4), True
        )

        # Test percolate one filter.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "SUBPOENAS SERVED OFF",
            "order_by": "score desc",
        }
        query_id_5 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_5)
        responses = percolate_document(
            str(self.de_1.docket.pk),
            RECAPPercolator._index._name,
            document_index_alias,
        )
        expected_queries = 1
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_5), True
        )

        # Test percolate text query.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED ON",
            "order_by": "score desc",
        }
        query_id_6 = self.save_percolator_query(cd)
        created_queries_ids.append(query_id_6)
        responses = percolate_document(
            str(self.de.docket.pk),
            RECAPPercolator._index._name,
            document_index_alias,
        )
        expected_queries = 3
        self.assertEqual(len(responses[0]), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_2), True
        )
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_3), True
        )
        self.assertEqual(
            self.confirm_query_matched(responses[0], query_id_6), True
        )

    def test_index_and_delete_recap_alerts_from_percolator(
        self, mock_prefix
    ) -> None:
        """Test a RECAP alert is removed from the RECAPPercolator index."""

        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.WEEKLY,
            name="Test Alert Docket Only",
            query='q="401 Civil"&type=r',
        )

        self.assertTrue(
            RECAPPercolator.exists(id=docket_only_alert.pk),
            msg=f"Alert id: {docket_only_alert.pk} was not indexed.",
        )
        self.assertTrue(
            RECAPDocumentPercolator.exists(id=docket_only_alert.pk),
            msg=f"Alert id: {docket_only_alert.pk} was not indexed.",
        )
        self.assertTrue(
            DocketDocumentPercolator.exists(id=docket_only_alert.pk),
            msg=f"Alert id: {docket_only_alert.pk} was not indexed.",
        )

        docket_only_alert_id = docket_only_alert.pk
        # Remove the alert.
        docket_only_alert.delete()
        self.assertFalse(
            RECAPPercolator.exists(id=docket_only_alert_id),
            msg=f"Alert id: {docket_only_alert_id} was not indexed.",
        )
        self.assertFalse(
            RECAPDocumentPercolator.exists(id=docket_only_alert_id),
            msg=f"Alert id: {docket_only_alert_id} was not indexed.",
        )
        self.assertFalse(
            DocketDocumentPercolator.exists(id=docket_only_alert_id),
            msg=f"Alert id: {docket_only_alert_id} was not indexed.",
        )

        # Index an alert with Docket filters.
        docket_only_alert_filter = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.WEEKLY,
            name="Test Alert Docket Only",
            query='q="401 Civil"&case_name="Lorem Ipsum"&type=r',
        )

        self.assertTrue(
            RECAPPercolator.exists(id=docket_only_alert_filter.pk),
            msg=f"Alert id: {docket_only_alert_filter.pk} was not indexed.",
        )
        # The docket_only_alert_filter shouldn't be indexed into the
        # RECAPDocumentPercolator due to its incompatibility.
        self.assertFalse(
            RECAPDocumentPercolator.exists(id=docket_only_alert_filter.pk),
            msg=f"Alert id: {docket_only_alert_filter.pk} was not indexed.",
        )
        self.assertTrue(
            DocketDocumentPercolator.exists(id=docket_only_alert_filter.pk),
            msg=f"Alert id: {docket_only_alert_filter.pk} was not indexed.",
        )

        docket_only_alert_filter_id = docket_only_alert_filter.pk
        # Remove the alert.
        docket_only_alert_filter.delete()
        self.assertFalse(
            RECAPPercolator.exists(id=docket_only_alert_filter_id),
            msg=f"Alert id: {docket_only_alert_filter_id} was not indexed.",
        )
        self.assertFalse(
            DocketDocumentPercolator.exists(id=docket_only_alert_filter_id),
            msg=f"Alert id: {docket_only_alert_filter_id} was not indexed.",
        )

    def test_percolate_document_on_ingestion(self, mock_prefix) -> None:
        """Confirm a Docket or RECAPDocument is percolated upon ingestion."""

        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only 1",
            query='q="SUBPOENAS SERVED CASE"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED CASE",
                docket_number="1:21-bk-1234",
                source=Docket.RECAP,
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        # The docket-only alert doesn't contain any nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            docket_only_alert.name,
            1,
            docket.case_name,
            0,
        )

        recap_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only 2",
            query='q="plain text for 018036652436"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court,
                    case_name="SUBPOENAS SERVED OFF",
                    docket_number="1:21-bk-1239",
                    source=Docket.RECAP,
                ),
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File",
                document_number="1",
                is_available=True,
                page_count=5,
                pacer_doc_id="018036652436",
                plain_text="plain text for 018036652436",
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        html_content = self.get_html_content_from_email(mail.outbox[1])
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

        self.assertIn(rd.description, html_content)
        self.assertIn(recap_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        # The RECAPDocument alert contain one nested child hit.
        self._count_alert_hits_and_child_hits(
            html_content,
            recap_only_alert.name,
            1,
            alert_de.docket.case_name,
            1,
        )

        # Related DE. RD creation.
        de_entry_field_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only 3",
            query='q="Hearing for Leave"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de_2 = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court,
                    case_name="SUBPOENAS SERVED ON",
                    docket_number="1:21-bk-12876",
                    source=Docket.RECAP,
                ),
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="Hearing for Leave to File Amicus Curiae Lorem Served",
            )
            rd_2 = RECAPDocumentFactory(
                docket_entry=alert_de_2,
                description="Motion to File",
                document_number="1",
                is_available=True,
                page_count=5,
                pacer_doc_id="01803665477",
                plain_text="plain text for 01803665477",
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        html_content = self.get_html_content_from_email(mail.outbox[2])
        self.assertEqual(
            len(mail.outbox), 3, msg="Outgoing emails don't match."
        )
        self.assertIn(rd_2.description, html_content)
        self.assertIn(de_entry_field_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        # The RECAPDocument alert contain one nested child hit.
        self._count_alert_hits_and_child_hits(
            html_content,
            de_entry_field_alert.name,
            1,
            alert_de_2.docket.case_name,
            1,
        )

        # DE/RD update.
        de_entry_field_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only 4",
            query='q="Hearing to File Updated"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de_2.description = "Hearing to File Updated"
            alert_de_2.save()

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        # No alert should be triggered on DE updates.
        self.assertEqual(
            len(mail.outbox), 3, msg="Outgoing emails don't match."
        )

        # Alert is triggered only after a RECAPDocument creation/update to avoid
        # percolating the same document twice.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            rd_2.document_number = 1
            rd_2.save()

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 4, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[3])

        self.assertIn(rd_2.description, html_content)
        self.assertIn(de_entry_field_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        # The RECAPDocument alert contain one nested child hit.
        self._count_alert_hits_and_child_hits(
            html_content,
            de_entry_field_alert.name,
            1,
            alert_de_2.docket.case_name,
            1,
        )

        # Docket update.
        docket_update_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only 5",
            query='q="SUBPOENAS SERVED LOREM"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            docket.case_name = "SUBPOENAS SERVED LOREM"
            docket.save()

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        html_content = self.get_html_content_from_email(mail.outbox[4])
        self.assertEqual(
            len(mail.outbox), 5, msg="Outgoing emails don't match."
        )
        self.assertIn(docket_update_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        # The docket-only alert doesn't contain any nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            docket_update_alert.name,
            1,
            docket.case_name,
            0,
        )

        # Percolate Docket upon Bankruptcy data is added/updated.
        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only 6",
            query="q=(SUBPOENAS SERVED) AND chapter:7&type=r",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            BankruptcyInformationFactory(docket=docket, chapter="7")

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        html_content = self.get_html_content_from_email(mail.outbox[5])
        self.assertEqual(
            len(mail.outbox), 6, msg="Outgoing emails don't match."
        )
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)

        # Percolate Docket upon parties data is added/updated.
        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only 7",
            query='atty_name="John Lorem"&type=r',
        )
        firm = AttorneyOrganizationFactory(
            name="Associates LLP 2", lookup_key="firm_llp"
        )
        attorney = AttorneyFactory(
            name="John Lorem",
            organizations=[firm],
            docket=docket,
        )
        PartyTypeFactory.create(
            party=PartyFactory(
                name="Defendant Jane Roe",
                docket=docket,
                attorneys=[attorney],
            ),
            docket=docket,
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            index_docket_parties_in_es.delay(docket.pk)

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 7, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[6])
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)

    def test_recap_alerts_highlighting(self, mock_prefix) -> None:
        """Confirm RECAP Search alerts are properly highlighted."""

        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only",
            query='q="SUBPOENAS SERVED CASE"&docket_number="1:21-bk-1234"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED CASE",
                docket_number="1:21-bk-1234",
                source=Docket.RECAP,
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        self.assertIn(f"<strong>{docket.case_name}</strong>", html_content)
        self.assertIn(f"<strong>{docket.docket_number}</strong>", html_content)

        recap_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert RECAP Only",
            query='q="plain text for 018036652000"&description="Affidavit Of Compliance"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court,
                    case_name="SUBPOENAS SERVED OFF",
                    docket_number="1:21-bk-1239",
                    source=Docket.RECAP,
                ),
                entry_number=1,
                description="Affidavit Of Compliance",
            )
            rd = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File",
                document_number="1",
                pacer_doc_id="018036652000",
                plain_text="plain text for 018036652000",
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[1])
        self.assertIn(recap_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        self.assertIn(f"<strong>{rd.plain_text}</strong>", html_content)
        self.assertIn(
            f"<strong>{rd.docket_entry.description}</strong>", html_content
        )

    @override_settings(SCHEDULED_ALERT_HITS_LIMIT=3)
    def test_group_percolator_alerts(self, mock_prefix) -> None:
        """Test group Percolator RECAP Alerts in an email and hits."""

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name=f"SUBPOENAS SERVED CASE",
                docket_number=f"1:21-bk-123",
                source=Docket.RECAP,
                cause="410 Civil",
            )
            dockets_created = []
            docket_case_names = [docket.case_name]
            for i in range(3):
                docket_created = DocketFactory(
                    court=self.court,
                    case_name=f"SUBPOENAS SERVED CASE {i}",
                    docket_number=f"1:21-bk-123{i}",
                    source=Docket.RECAP,
                    cause="410 Civil",
                )
                dockets_created.append(docket_created)
                if i < 2:
                    docket_case_names.append(docket_created.case_name)

            alert_de = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )

            rd_1 = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File 1",
                document_number="1",
                pacer_doc_id="01803665981",
                plain_text="plain text lorem",
            )
            rd_descriptions = [rd_1.description]
            rd_ids = [rd_1.pk]
            for i in range(5):
                rd = RECAPDocumentFactory(
                    docket_entry=alert_de,
                    description=f"Motion to File {i+2}",
                    document_number=f"{i+2}",
                    pacer_doc_id=f"018036652436{i+2}",
                )
                if i < 4:
                    # Omit the last alert to compare. Only up to 5 should be
                    # included in the case.
                    rd_descriptions.append(rd.description)

                rd_ids.append(rd.pk)
            docket_only_alert = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert Docket Only",
                query='q="410 Civil"&type=r',
            )
            recap_only_alert = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert RECAP Only Docket Entry",
                query=f"q=docket_entry_id:{alert_de.pk}&type=r",
            )

            cross_object_alert_with_hl = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert Cross-object",
                query=f'q="File Amicus Curiae" AND "Motion to File 1" AND '
                f'"plain text lorem" AND "410 Civil" AND '
                f"id:{rd_1.pk}&docket_number={docket.docket_number}"
                f'&case_name="{docket.case_name}"&type=r',
            )

        self.assertEqual(
            len(mail.outbox), 0, msg="Outgoing emails don't match."
        )

        # Assert webhooks.
        webhook_events = WebhookEvent.objects.all().values_list(
            "content", flat=True
        )
        # 11 webhooks should be triggered one for each document ingested that
        # matched each alert.
        self.assertEqual(
            len(webhook_events), 11, msg="Webhook events didn't match."
        )
        # 4 Webhooks for docket_only_alert without any nested recap_documents.
        self._count_percolator_webhook_hits_and_child_hits(
            webhook_events, docket_only_alert.name, 4, 0, None
        )
        # 6 Webhooks for recap_only_alert each one with 1 recap_document nested.
        self._count_percolator_webhook_hits_and_child_hits(
            webhook_events, recap_only_alert.name, 6, 6, rd_ids
        )
        # 1 Webhook for cross_object_alert_with_hl with 1 recap_document nested.
        self._count_percolator_webhook_hits_and_child_hits(
            webhook_events, cross_object_alert_with_hl.name, 1, 1, [rd_1.pk]
        )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        # Assert docket-only alert.
        html_content = self.get_html_content_from_email(mail.outbox[0])
        txt_email = mail.outbox[0].body
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 3)
        # The docket-only alert doesn't contain any nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            docket_only_alert.name,
            3,
            docket.case_name,
            0,
        )
        # Assert email text version.
        self.assertIn(docket_only_alert.name, txt_email)
        for case_name in docket_case_names:
            with self.subTest(
                alert=case_name, msg="Assert case_name in email."
            ):
                self.assertIn(case_name, txt_email)

        # Assert RECAP-only alert.
        self.assertIn(recap_only_alert.name, html_content)
        # The recap-only alert contain 2 child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            recap_only_alert.name,
            1,
            alert_de.docket.case_name,
            5,
        )
        self._assert_child_hits_content(
            html_content,
            recap_only_alert.name,
            alert_de.docket.case_name,
            rd_descriptions,
        )
        # Assert the View more results button is present in the alert.
        self.assertIn("View Additional Results for this Case", html_content)
        self.assertEqual(
            html_content.count("View Additional Results for this Case"), 1
        )

        # Assert email text version.
        self.assertIn(recap_only_alert.name, txt_email)
        self.assertIn("View Additional Results for this Case", txt_email)
        for rd_description in rd_descriptions:
            with self.subTest(
                alert=rd_description,
                msg="Assert RECAPDocument description in email.",
            ):
                self.assertIn(rd_description, txt_email)

        # Assert Cross-object alert.
        # The cross-object alert only contain 1 child hit.
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_with_hl.name,
            1,
            alert_de.docket.case_name,
            1,
        )
        self._count_webhook_hits_and_child_hits(
            list(webhook_events),
            cross_object_alert_with_hl.name,
            1,
            alert_de.docket.case_name,
            1,
        )
        self._assert_child_hits_content(
            html_content,
            cross_object_alert_with_hl.name,
            alert_de.docket.case_name,
            [rd_1.description],
        )

        # Assert email text version.
        self.assertIn(cross_object_alert_with_hl.name, txt_email)

        # Assert HL in the cross_object_alert_with_hl
        self.assertIn(f"<strong>{docket.case_name}</strong>", html_content)
        self.assertEqual(
            html_content.count(f"<strong>{docket.case_name}</strong>"), 1
        )
        self.assertIn(f"<strong>{docket.docket_number}</strong>", html_content)
        self.assertEqual(
            html_content.count(f"<strong>{docket.docket_number}</strong>"), 1
        )
        self.assertIn(f"<strong>{rd_1.plain_text}</strong>", html_content)
        self.assertEqual(
            html_content.count(f"<strong>{rd_1.plain_text}</strong>"), 1
        )
        self.assertIn(f"<strong>{rd_1.description}</strong>", html_content)
        self.assertEqual(
            html_content.count(f"<strong>{rd_1.description}</strong>"), 1
        )
        self.assertIn("<strong>File Amicus Curiae</strong>", html_content)
        self.assertEqual(
            html_content.count("<strong>File Amicus Curiae</strong>"), 1
        )

        # Assert HL content in webhooks.
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "caseName",
            f"<strong>{docket.case_name}</strong>",
            child_field=False,
        )
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "docketNumber",
            f"<strong>{docket.docket_number}</strong>",
            child_field=False,
        )
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "snippet",
            f"<strong>{rd_1.plain_text}</strong>",
            child_field=True,
        )
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "short_description",
            f"<strong>{rd_1.description}</strong>",
            child_field=True,
        )
        self._assert_webhook_hit_hl(
            webhook_events,
            cross_object_alert_with_hl.name,
            "description",
            "<strong>File Amicus Curiae</strong>",
            child_field=True,
        )

        for docket in dockets_created:
            docket.delete()

    def test_filter_out_alerts_to_send_by_query_and_hits(
        self, mock_prefix
    ) -> None:
        """Test RECAP alerts can be properly filtered out according to
        their query and hits matched conditions.

        - Docket-only Alerts should be triggered only upon a Docket ingestion.
          commiting RECAPDocument ingestion that can match the alert.
        - The Docket or RD shouldn’t have triggered the alert previously.
        - RECAP-only Alerts should only include RDs that have not triggered the
          same alert previously.
        """

        scheduled_hits = ScheduledAlertHit.objects.all()
        self.assertEqual(len(scheduled_hits), 0)

        # The following test should match the Docket-only query on docket
        # ingestion
        docket_only_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Docket Only Not Triggered",
            query='q="405 Civil"&type=r',
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
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

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        # Assert docket-only alert.
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(docket_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        # The docket-only alert doesn't contain any nested child hits.
        self._count_alert_hits_and_child_hits(
            html_content,
            docket_only_alert.name,
            1,
            docket.case_name,
            0,
        )

        # Test "AND" and "OR" cross object alert queries.
        cross_object_alert_d_and_rd_field = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object query AND",
            query=f'q="405 Civil" AND pacer_doc_id:018036652436&type=r',
        )
        cross_object_alert_d_or_rd_field = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert Cross-object query OR",
            query=f'q="405 Civil" OR pacer_doc_id:018036652436&type=r',
        )
        # RD ingestion.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            alert_de = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2024, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem Served",
            )
            rd = RECAPDocumentFactory(
                docket_entry=alert_de,
                description="Motion to File",
                document_number="1",
                is_available=True,
                page_count=5,
                pacer_doc_id="018036652436",
                plain_text="plain text for 018036652436",
            )

        # The RD ingestion's shouldn't match the docket-only alert.
        # It should only match the cross_object_alert_d_and_rd_field and
        # cross_object_alert_d_or_rd_field alerts.
        call_command("cl_send_rt_percolator_alerts", testing_mode=True)
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[1])
        self._confirm_number_of_alerts(html_content, 2)
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_d_and_rd_field.name,
            1,
            docket.case_name,
            1,
        )
        self._count_alert_hits_and_child_hits(
            html_content,
            cross_object_alert_d_or_rd_field.name,
            1,
            docket.case_name,
            1,
        )

        # Call cl_send_rt_percolator_alerts again. No alerts should be sent this time.
        call_command("cl_send_rt_percolator_alerts", testing_mode=True)
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        scheduled_hits = ScheduledAlertHit.objects.filter(
            hit_status=SCHEDULED_ALERT_HIT_STATUS.SENT
        )
        self.assertEqual(len(scheduled_hits), 3)
        docket.delete()

    @override_settings(ELASTICSEARCH_PAGINATION_BATCH_SIZE=3)
    def test_retrieve_all_the_matched_alerts_in_batches(self, mock_prefix):
        """Confirm that we can retrieve all the matched alerts by the
        percolator if the number of alerts matched exceeds the initial query
        ELASTICSEARCH_PAGINATION_BATCH_SIZE.
        Also assert that no RT alerts are scheduled to be sent according to its
        rate.
        """

        alerts_created_user_1 = []
        alerts_created_user_2 = []
        for i in range(6):
            docket_only_alert = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.WEEKLY,
                name=f"Test Alert Docket Only {i}",
                query='q="405 Civil"&type=r',
            )
            alerts_created_user_1.append(docket_only_alert)
            docket_only_alert_2 = AlertFactory(
                user=self.user_profile_2.user,
                rate=Alert.REAL_TIME,
                name=f"Test Alert Docket Only {i}",
                query='q="405 Civil"&type=r',
            )
            alerts_created_user_2.append(docket_only_alert_2)

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
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

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        webhook_events = WebhookEvent.objects.all().values_list(
            "content", flat=True
        )
        # 6 webhook events should be triggered, all of them for user_profile
        # # and none for user_profile_2 since it doesn't have a webhook enabled
        self.assertEqual(
            len(webhook_events), 6, msg="Webhook events didn't match."
        )

        # 1 email should be sent for user_profile
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        # Assert 6 alerts are contained in the email for user_profile
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self._confirm_number_of_alerts(html_content, 6)
        for alert in alerts_created_user_1:
            with self.subTest(alert=alert, msg="Assert alert in email."):
                self.assertIn(alert.name, html_content)

        # Send scheduled Weekly alerts and check assertions.
        call_command("cl_send_scheduled_alerts", rate=Alert.WEEKLY)
        # 1 additional email should be sent for user_profile_2
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        # Assert 6 alerts are contained in the email for user_profile_2
        html_content = self.get_html_content_from_email(mail.outbox[1])
        self._confirm_number_of_alerts(html_content, 6)
        for alert in alerts_created_user_2:
            with self.subTest(alert=alert, msg="Assert alert in email."):
                self.assertIn(alert.name, html_content)

        docket.delete()
