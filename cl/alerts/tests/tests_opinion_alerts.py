import datetime
from unittest import mock

import time_machine
from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils.timezone import now

from cl.alerts.factories import AlertFactory
from cl.alerts.models import Alert
from cl.api.factories import WebhookFactory
from cl.api.models import WebhookEvent, WebhookEventType
from cl.donate.models import NeonMembership
from cl.lib.date_time import midnight_pt
from cl.lib.redis_utils import get_redis_interface
from cl.lib.test_helpers import CourtTestCase, PeopleTestCase, SearchTestCase
from cl.search.documents import OpinionPercolator
from cl.search.factories import OpinionClusterFactory, OpinionFactory
from cl.search.models import SEARCH_TYPES
from cl.tests.cases import ESIndexTestCase, SearchAlertsAssertions, TestCase
from cl.tests.utils import MockResponse
from cl.users.factories import UserProfileWithParentsFactory


@override_settings(PERCOLATOR_OPINIONS_SEARCH_ALERTS_ENABLED=True)
@mock.patch(
    "cl.alerts.utils.get_alerts_set_prefix",
    return_value="alert_hits_percolator_opinions",
)
@override_settings(NO_MATCH_HL_SIZE=100)
class OpinionAlertsPercolatorTest(
    CourtTestCase,
    PeopleTestCase,
    SearchTestCase,
    ESIndexTestCase,
    TestCase,
    SearchAlertsAssertions,
):
    """
    Opinion Alerts Percolator Tests
    """

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("alerts.Alert")
        cls.rebuild_index("search.OpinionCluster")
        cls.user_profile = UserProfileWithParentsFactory()
        NeonMembership.objects.create(
            level=NeonMembership.LEGACY, user=cls.user_profile.user
        )
        cls.webhook_enabled = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=True,
            version=2,
        )

        date_now = midnight_pt(now().date())
        cls.mock_date = date_now.replace(
            hour=20, minute=0, second=0, microsecond=0
        )
        with time_machine.travel(cls.mock_date, tick=False):
            super().setUpTestData()
            cls.opinion_cluster_4 = OpinionClusterFactory.create(
                case_name_full="Bank of America v. Lorem",
                case_name_short="America",
                syllabus="some rando syllabus",
                date_filed=datetime.date(1895, 6, 9),
                procedural_history="some rando history",
                source="C",
                judges="David",
                case_name="Bank of America",
                slug="case-name-cluster-4",
                precedential_status="Published",
                nature_of_suit="copyright",
                docket=cls.docket_2,
            )
            cls.opinion_cluster_5 = OpinionClusterFactory.create(
                case_name_full="Legal Association v. Lorem",
                case_name_short="Legal Association",
                syllabus="some rando syllabus",
                date_filed=datetime.date(1895, 6, 9),
                procedural_history="some rando history",
                source="C",
                judges="David",
                case_name="Legal Association",
                slug="case-name-cluster-5",
                precedential_status="Published",
                nature_of_suit="copyright",
                docket=cls.docket_2,
            )
            call_command(
                "cl_index_parent_and_child_docs",
                search_type=SEARCH_TYPES.OPINION,
                queue="celery",
                pk_offset=0,
                testing_mode=True,
            )

    def setUp(self):
        OpinionPercolator._index.delete(ignore=404)
        OpinionPercolator.init()

        self.r = get_redis_interface("CACHE")
        keys = self.r.keys("alert_hits_percolator_opinions:*")
        if keys:
            self.r.delete(*keys)

        self.percolator_call_count = 0

    def test_opinions_cross_object_percolator_queries(
        self, mock_prefix
    ) -> None:
        """Test if a variety of Opinions and OpinionClusters can trigger
        percolator queries
        """

        created_queries_ids = []

        # Test Percolate an Opinion. It should match the query containing
        # OpinionCluster AND Opinion text query terms.
        cd = {
            "type": SEARCH_TYPES.OPINION,
            "q": "(Debbas v. Franklin) AND (my plain text secret word for queries)",
            "order_by": "score desc",
        }
        app_label = "search.Opinion"
        query_id_1 = self.save_percolator_query(cd, OpinionPercolator)
        created_queries_ids.append(query_id_1)
        responses = self.prepare_and_percolate_document(
            app_label, str(self.opinion_1.pk)
        )
        expected_queries = 1
        self.assertEqual(len(responses.main_response), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses.main_response, query_id_1),
            True,
        )

        # Test Percolate an Opinion. It should match the query containing
        # an OpinionCluster query terms and Opinion filter.
        cd = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"cites:({self.opinion_1.pk}) AND {self.opinion_cluster_3.case_name}",
            "order_by": "score desc",
        }
        query_id_2 = self.save_percolator_query(cd, OpinionPercolator)
        created_queries_ids.append(query_id_2)
        app_label = "search.Opinion"
        responses = self.prepare_and_percolate_document(
            app_label, str(self.opinion_3.pk)
        )
        expected_queries = 1
        self.assertEqual(len(responses.main_response), expected_queries)
        self.assertEqual(
            self.confirm_query_matched(responses.main_response, query_id_2),
            True,
        )

        # Test Percolate an OpinionCluster it's not supported.
        app_label = "search.OpinionCluster"
        with self.assertRaises(NotImplementedError):
            self.prepare_and_percolate_document(
                app_label, str(self.opinion_cluster_2.pk)
            )

    def test_index_and_delete_opinion_alerts_from_percolator(
        self, mock_prefix
    ) -> None:
        """Test an Opinion alert is added/removed from the OpinionPercolator
        index.
        """

        with self.captureOnCommitCallbacks(execute=True):
            opinion_alert = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.WEEKLY,
                name="Test Opinion Alert",
                query='q="Howard v. Honda"&type=o&order_by=score desc',
                alert_type=SEARCH_TYPES.OPINION,
            )
        self.assertTrue(
            OpinionPercolator.exists(id=opinion_alert.pk),
            msg=f"Alert id: {opinion_alert.pk} was not indexed.",
        )
        alert_doc = OpinionPercolator.get(id=opinion_alert.pk)
        response_str = str(alert_doc.to_dict())
        self.assertIn("Howard v. Honda", response_str)
        self.assertIn("'rate': 'wly'", response_str)
        # function_score breaks percolator queries. Ensure it is never indexed.
        self.assertNotIn("function_score", response_str)

        opinion_alert_id = opinion_alert.pk
        # Remove the alert.
        opinion_alert.delete()
        self.assertFalse(
            OpinionPercolator.exists(id=opinion_alert_id),
            msg=f"Alert id: {opinion_alert_id} was not indexed.",
        )

        with self.captureOnCommitCallbacks(execute=True):
            # Index an alert with OpinionCluster filters.
            opinion_alert_filter = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.WEEKLY,
                name="Test Alert Opinion Only",
                query='q="Lorem"&case_name="Howard v. Honda"&type=o',
                alert_type=SEARCH_TYPES.OPINION,
            )
        self.assertTrue(
            OpinionPercolator.exists(id=opinion_alert_filter.pk),
            msg=f"Alert id: {opinion_alert_filter.pk} was not indexed.",
        )

        opinion_alert_filter_id = opinion_alert_filter.pk
        # Remove the alert.
        opinion_alert_filter.delete()
        self.assertFalse(
            OpinionPercolator.exists(id=opinion_alert_filter_id),
            msg=f"Alert id: {opinion_alert_filter_id} was not indexed.",
        )

    def test_percolate_document_on_ingestion(self, mock_prefix) -> None:
        """Confirm an Opinion is percolated upon ingestion."""

        opinion_cluster_indexing_time = self.mock_date - datetime.timedelta(
            seconds=15
        )
        with self.captureOnCommitCallbacks(execute=True):
            opinion_cluster_alert = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert OpinionCluster Only 1",
                query='q="Howard v. Honda"&type=o',
                alert_type=SEARCH_TYPES.OPINION,
            )

        with (
            mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ),
            time_machine.travel(opinion_cluster_indexing_time, tick=False),
            self.captureOnCommitCallbacks(execute=True),
        ):
            opinion = OpinionFactory.create(
                extracted_by_ocr=False,
                author=self.person_2,
                plain_text="Lorem ipsum text",
                cluster=self.opinion_cluster_2,
                local_path="test/search/opinion_doc.doc",
                per_curiam=False,
                type="020lead",
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        txt_content = mail.outbox[0].body

        self.assertIn(opinion_cluster_alert.name, html_content)
        self.assertIn(opinion_cluster_alert.name, txt_content)
        self._confirm_number_of_alerts(html_content, 1)
        self._count_alert_hits_and_child_hits(
            html_content,
            opinion_cluster_alert.name,
            1,
            self.opinion_cluster_2.case_name,
            1,
        )

        # Trigger an update for the same opinion. The alert shouldn't be trigger
        # again.
        with (
            time_machine.travel(opinion_cluster_indexing_time, tick=False),
            self.captureOnCommitCallbacks(execute=True),
        ):
            opinion.plain_text = "Lorem Dolor"
            opinion.save()

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        # Alert for Opinion only fields.
        with self.captureOnCommitCallbacks(execute=True):
            opinion_alert = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert Opinion Only 1",
                query='q="Curabitur id lorem vel"&type=o',
                alert_type=SEARCH_TYPES.OPINION,
            )

        with (
            mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ),
            time_machine.travel(opinion_cluster_indexing_time, tick=False),
            self.captureOnCommitCallbacks(execute=True),
        ):
            opinion_2 = OpinionFactory.create(
                extracted_by_ocr=False,
                author=self.person_2,
                plain_text="Curabitur id lorem vel "
                "orci aliquam commodo vitae a neque. Nam a nulla mi."
                " Fusce elementum felis eget luctus venenatis. Cras "
                "tincidunt a dolor ac commodo. Duis vel turpis hendrerit",
                cluster=self.opinion_cluster_3,
                local_path="test/search/opinion_doc.doc",
                per_curiam=False,
                type="020lead",
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[1])
        txt_content = mail.outbox[1].body

        self.assertIn(opinion_alert.name, html_content)
        self.assertIn(opinion_alert.name, txt_content)
        self._confirm_number_of_alerts(html_content, 1)
        self._count_alert_hits_and_child_hits(
            html_content,
            opinion_alert.name,
            1,
            self.opinion_cluster_3.case_name,
            1,
        )
        # Confirm that the snippet is truncated to the fragment_size defined
        # for the field when it's HL.
        snippet = self._extract_snippet_content(html_content)
        self.assertTrue(len(snippet) < len(opinion_2.plain_text))

        with (
            mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ),
            time_machine.travel(opinion_cluster_indexing_time, tick=False),
            self.captureOnCommitCallbacks(execute=True),
        ):
            opinion_3 = OpinionFactory.create(
                extracted_by_ocr=False,
                author=self.person_2,
                plain_text="",
                cluster=self.opinion_cluster_3,
                local_path="test/search/opinion_doc.doc",
                per_curiam=False,
                type="020lead",
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        # No alert should be triggered.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

        # The alert should be triggered upon the opinion update.
        with (
            mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ),
            time_machine.travel(opinion_cluster_indexing_time, tick=False),
            self.captureOnCommitCallbacks(execute=True),
        ):
            opinion_3.plain_text = (
                "Curabitur id lorem vel orci aliquam commodo"
            )
            opinion_3.save()

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 3, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[2])
        txt_content = mail.outbox[2].body

        self.assertIn(opinion_alert.name, html_content)
        self.assertIn(opinion_alert.name, txt_content)
        self._confirm_number_of_alerts(html_content, 1)
        self._count_alert_hits_and_child_hits(
            html_content,
            opinion_alert.name,
            1,
            self.opinion_cluster_3.case_name,
            1,
        )
        snippet = self._extract_snippet_content(html_content)
        self.assertIn(opinion_3.plain_text, snippet)

    def test_opinion_alerts_highlighting(self, mock_prefix) -> None:
        """Confirm Opinion Search alerts are properly highlighted."""

        with self.captureOnCommitCallbacks(execute=True):
            opinion_only_alert = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert Opinion Only",
                query=f'q="elementum"&case_name=cluster&docket_number="{self.docket_3.docket_number}"&type=o',
                alert_type=SEARCH_TYPES.OPINION,
            )
        with (
            mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            OpinionFactory.create(
                extracted_by_ocr=False,
                author=self.person_2,
                plain_text="Fusce elementum felis",
                cluster=self.opinion_cluster_3,
                local_path="test/search/opinion_doc.doc",
                per_curiam=False,
                type="020lead",
            )

        call_command("cl_send_rt_percolator_alerts", testing_mode=True)

        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self.assertIn(opinion_only_alert.name, html_content)
        self._confirm_number_of_alerts(html_content, 1)
        self.assertIn("<strong>cluster</strong>", html_content)
        self.assertIn("<strong>elementum</strong>", html_content)

    @override_settings(SCHEDULED_ALERT_HITS_LIMIT=3, OPINION_HITS_PER_RESULT=5)
    def test_group_percolator_alerts(self, mock_prefix) -> None:
        """Test group Percolator Opinion Alerts in an email and hits."""
        with self.captureOnCommitCallbacks(execute=True):
            alert_1 = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert Opinion",
                query='case_name="Howard" OR "cluster" OR "Debbas" OR "America"&type=o&stat_Published=on&stat_Errata=on',
                alert_type=SEARCH_TYPES.OPINION,
            )

            alert_2 = AlertFactory(
                user=self.user_profile.user,
                rate=Alert.REAL_TIME,
                name="Test Alert Opinion Text",
                query='q="elementum"&type=o',
                alert_type=SEARCH_TYPES.OPINION,
            )

        with (
            mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            clusters = [
                self.opinion_cluster_1,
                self.opinion_cluster_2,
                self.opinion_cluster_3,
                self.opinion_cluster_4,
            ]
            alert_1_ids = []
            alert_2_ids = []
            for i, cluster in enumerate(clusters):
                alert_1_o = OpinionFactory.create(
                    extracted_by_ocr=False,
                    author=self.person_2,
                    plain_text=f"Fusce Lorem felis {i}",
                    cluster=cluster,
                    local_path="test/search/opinion_doc.doc",
                    per_curiam=False,
                    type="020lead",
                )
                alert_1_ids.append(alert_1_o.id)

            for i in range(5):
                alert_2_o = OpinionFactory.create(
                    extracted_by_ocr=False,
                    author=self.person_2,
                    plain_text=f"Fusce elementum felis {i}",
                    cluster=self.opinion_cluster_5,
                    local_path="test/search/opinion_doc.doc",
                    per_curiam=False,
                    type="020lead",
                )
                alert_2_ids.append(alert_2_o.id)

        self.assertEqual(
            len(mail.outbox), 0, msg="Outgoing emails don't match."
        )

        # Assert webhooks.
        webhook_events = WebhookEvent.objects.filter(
            webhook__user=self.user_profile.user
        ).values_list("content", flat=True)

        # 9 webhooks for user_profile should be triggered one for each
        # document ingested that matched each alert.
        self.assertEqual(
            len(webhook_events), 9, msg="Webhook events didn't match."
        )

        # 4 Webhooks for alert_1.
        self._count_percolator_webhook_hits_and_child_hits(
            webhook_events, alert_1.name, 4, 4, alert_1_ids, "opinions"
        )
        # 5 Webhooks for alert_2 each one with 1 Opinion nested.
        self._count_percolator_webhook_hits_and_child_hits(
            webhook_events, alert_2.name, 5, 5, alert_2_ids, "opinions"
        )

        rt_mock_date_sent = self.mock_date + datetime.timedelta(
            seconds=settings.REAL_TIME_ALERTS_SENDING_RATE
        )
        with time_machine.travel(rt_mock_date_sent, tick=False):
            call_command("cl_send_rt_percolator_alerts", testing_mode=True)
            alerts_runtime_naive = datetime.datetime.now()

        # Only one email should be triggered because email alerts for
        # non-members are omitted.
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        # Assert alert_1 alert.
        html_content = self.get_html_content_from_email(mail.outbox[0])

        # Confirm that query overridden in the 'View Full Results' URL to
        # include a filter by timestamp.
        self._assert_timestamp_filter(
            html_content, Alert.REAL_TIME, alerts_runtime_naive
        )

        # Confirm Alert date_last_hit is updated.
        alert_1.refresh_from_db()
        self.assertEqual(
            alert_1.date_last_hit,
            rt_mock_date_sent,
            msg="Alert date of last hit didn't match.",
        )

        txt_email = mail.outbox[0].body
        self.assertIn(alert_1.name, html_content)
        self._confirm_number_of_alerts(html_content, 2)

        self._count_alert_hits_and_child_hits(
            html_content,
            alert_1.name,
            4,
            self.opinion_cluster_1.case_name,
            1,
        )
        # Assert email text version.
        self.assertIn(alert_1.name, txt_email)
        cluster_case_names = [cluster.case_name for cluster in clusters]
        for case_name in cluster_case_names:
            with self.subTest(
                alert=case_name, msg="Assert case_name in email."
            ):
                self.assertIn(case_name, txt_email)

        # Assert alert_2 alert.
        html_content = self.get_html_content_from_email(mail.outbox[0])

        # Confirm Alert date_last_hit is updated.
        alert_2.refresh_from_db()
        self.assertEqual(
            alert_2.date_last_hit,
            rt_mock_date_sent,
            msg="Alert date of last hit didn't match.",
        )

        txt_email = mail.outbox[0].body
        self.assertIn(alert_2.name, html_content)

        self._count_alert_hits_and_child_hits(
            html_content,
            alert_2.name,
            1,
            self.opinion_cluster_5.case_name,
            3,
        )
        # Assert email text version.
        self.assertIn(alert_2.name, txt_email)
        self.assertIn(self.opinion_cluster_5.case_name, txt_email)

    @override_settings(ELASTICSEARCH_PAGINATION_BATCH_SIZE=3)
    def test_retrieve_all_the_matched_alerts_in_batches(self, mock_prefix):
        """Confirm that we can retrieve all the matched alerts by the
        percolator if the number of alerts matched exceeds the initial query
        ELASTICSEARCH_PAGINATION_BATCH_SIZE.
        Also assert that no RT alerts are scheduled to be sent according to its
        rate.
        """

        alerts_created_user_1 = []
        for i in range(6):
            with self.captureOnCommitCallbacks(execute=True):
                alert_1 = AlertFactory(
                    user=self.user_profile.user,
                    rate=Alert.WEEKLY,
                    name=f"Test Alert Opinion {i}",
                    query='q="Curabitur id lorem"&type=o',
                    alert_type=SEARCH_TYPES.OPINION,
                )
                alerts_created_user_1.append(alert_1)
        with (
            mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            opinion = OpinionFactory.create(
                extracted_by_ocr=False,
                author=self.person_2,
                plain_text="Curabitur id lorem vel",
                cluster=self.opinion_cluster_3,
                local_path="test/search/opinion_doc.doc",
                per_curiam=False,
                type="020lead",
            )

        webhook_events = WebhookEvent.objects.all().values_list(
            "content", flat=True
        )
        # 6 webhook events should be triggered
        self.assertEqual(
            len(webhook_events), 6, msg="Webhook events didn't match."
        )

        # Send scheduled Weekly alerts and check assertions.
        call_command("cl_send_scheduled_alerts", rate=Alert.WEEKLY)

        # 1 emails should be sent for user_profile
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )

        # Assert 6 alerts are contained in the email for user_profile
        html_content = self.get_html_content_from_email(mail.outbox[0])
        self._confirm_number_of_alerts(html_content, 6)
        for alert in alerts_created_user_1:
            with self.subTest(alert=alert, msg="Assert alert in email."):
                self.assertIn(alert.name, html_content)

        opinion.delete()
