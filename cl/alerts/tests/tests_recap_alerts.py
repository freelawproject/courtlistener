import datetime
from unittest import mock

import time_machine
from asgiref.sync import sync_to_async
from django.core import mail
from django.core.management import call_command
from django.test.utils import override_settings
from django.utils.html import strip_tags
from django.utils.timezone import now
from lxml import html

from cl.alerts.factories import AlertFactory
from cl.alerts.models import SEARCH_TYPES, Alert
from cl.alerts.utils import query_includes_rd_field, recap_document_hl_matched
from cl.api.factories import WebhookFactory
from cl.api.models import WebhookEvent, WebhookEventType
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

    def _confirm_number_of_alerts(self, html_content, expected_count):
        """Test the number of alerts included in the email alert."""
        tree = html.fromstring(html_content)
        got = len(tree.xpath("//h2"))

        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of alerts in the email. "
            "Expected: %s - Got: %s\n\n" % (expected_count, got),
        )

    @staticmethod
    def _extract_cases_from_alert(html_tree, alert_title):
        """Extract the case elements (h3) under a specific alert (h2) from the
        HTML tree.
        """
        alert_element = html_tree.xpath(
            f"//h2[contains(text(), '{alert_title}')]"
        )
        h2_elements = html_tree.xpath("//h2")
        alert_index = h2_elements.index(alert_element[0])
        # Find the <h3> elements between this <h2> and the next <h2>
        if alert_index + 1 < len(h2_elements):
            next_alert_element = h2_elements[alert_index + 1]
            alert_cases = html_tree.xpath(
                f"//h2[contains(text(), '{alert_title}')]/following-sibling::*[following-sibling::h2[1] = '{next_alert_element.text}'][self::h3]"
            )
        else:
            alert_cases = html_tree.xpath(
                f"//h2[contains(text(), '{alert_title}')]/following-sibling::h3"
            )
        return alert_cases

    def _count_alert_hits_and_child_hits(
        self,
        html_content,
        alert_title,
        expected_hits,
        case_title,
        expected_child_hits,
    ):
        """Confirm the following assertions for the email alert:
        - An specific alert is included in the email alert.
        - The specified alert contains the expected number of hits.
        - The specified case contains the expected number of child hits.
        """
        tree = html.fromstring(html_content)
        alert_element = tree.xpath(f"//h2[contains(text(), '{alert_title}')]")
        self.assertTrue(
            alert_element, msg=f"Not alert with title {alert_title} found."
        )

        alert_cases = self._extract_cases_from_alert(tree, alert_title)

        self.assertEqual(
            len(alert_cases),
            expected_hits,
            msg="Did not get the right number of hits for the alert %s. "
            "Expected: %s - Got: %s\n\n"
            % (alert_title, expected_hits, len(alert_cases)),
        )
        if case_title:
            child_hit_count = 0
            for case in alert_cases:
                case_text = " ".join(case.xpath(".//text()")).strip()
                if case_title in case_text:
                    child_hit_count = len(
                        case.xpath("following-sibling::ul[1]/li/a")
                    )

            self.assertEqual(
                child_hit_count,
                expected_child_hits,
                msg="Did not get the right number of child hits for the case %s. "
                "Expected: %s - Got: %s\n\n"
                % (case_title, expected_child_hits, child_hit_count),
            )

    def _assert_child_hits_content(
        self,
        html_content,
        alert_title,
        case_title,
        expected_child_descriptions,
    ):
        """Confirm the child hits in a case are the expected ones, comparing
        their descriptions.
        """
        tree = html.fromstring(html_content)
        alert_element = tree.xpath(f"//h2[contains(text(), '{alert_title}')]")
        # Find the corresponding case_title under the alert_element
        alert_cases = self._extract_cases_from_alert(tree, alert_title)

        def extract_child_descriptions(case_item):
            child_documents = case_item.xpath("./following-sibling::ul[1]/li")
            results = []
            for li in child_documents:
                a_tag = li.xpath(".//a")[0]
                full_text = a_tag.text_content()
                first_part = full_text.split("\u2014")[0].strip()
                results.append(first_part)

            return results

        child_descriptions = set()
        for case in alert_cases:
            case_text = "".join(case.xpath(".//text()")).strip()
            if case_title in case_text:
                child_descriptions = set(extract_child_descriptions(case))
                break

        self.assertEqual(
            child_descriptions,
            set(expected_child_descriptions),
            msg=f"Child hits didn't match for case {case_title}, Got {child_descriptions}, Expected: {expected_child_descriptions} ",
        )

    def _count_webhook_hits_and_child_hits(
        self,
        webhooks,
        alert_title,
        expected_hits,
        case_title,
        expected_child_hits,
    ):
        """Confirm the following assertions for the search alert webhook:
        - An specific alert webhook was triggered.
        - The specified alert contains the expected number of hits.
        - The specified case contains the expected number of child hits.
        """

        for webhook in webhooks:
            if webhook["payload"]["alert"]["name"] == alert_title:
                webhook_cases = webhook["payload"]["results"]
                self.assertEqual(
                    len(webhook_cases),
                    expected_hits,
                    msg=f"Did not get the right number of hits for the alert %s. "
                    % alert_title,
                )
                for case in webhook["payload"]["results"]:
                    if case_title == strip_tags(case["caseName"]):
                        self.assertEqual(
                            len(case["recap_documents"]),
                            expected_child_hits,
                            msg=f"Did not get the right number of child documents for the case %s. "
                            % case_title,
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
            call_command("cl_send_recap_alerts")

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

        # Its related RD is ingested today.
        mock_date = now().replace(hour=5)
        with time_machine.travel(mock_date, tick=False):
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
            call_command("cl_send_recap_alerts")
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
            call_command("cl_send_recap_alerts")
        # No new alert should be triggered.
        self.assertEqual(
            len(mail.outbox), 2, msg="Outgoing emails don't match."
        )

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
            call_command("cl_send_recap_alerts")

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
            call_command("cl_send_recap_alerts")

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

    def test_limit_alert_case_child_hits(self) -> None:
        """Test limit case child hits up to 5 and display the "View additional
        results for this Case" button.
        """

        mock_date = now().replace(hour=5)
        with time_machine.travel(mock_date, tick=False):
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

        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
            sweep_index=True,
        )
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
        ), time_machine.travel(self.mock_date, tick=False):
            call_command("cl_send_recap_alerts")

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

    @override_settings(SCHEDULED_ALERT_HITS_LIMIT=3)
    def test_multiple_alerts_email_hits_limit_per_alert(self) -> None:
        """Test multiple alerts can be grouped in an email and hits within an
        alert are limited to SCHEDULED_ALERT_HITS_LIMIT (3) hits.
        """

        docket = DocketFactory(
            court=self.court,
            case_name=f"SUBPOENAS SERVED CASE",
            docket_number=f"1:21-bk-123",
            source=Docket.RECAP,
            cause="410 Civil",
        )
        for i in range(3):
            DocketFactory(
                court=self.court,
                case_name=f"SUBPOENAS SERVED CASE {i}",
                docket_number=f"1:21-bk-123{i}",
                source=Docket.RECAP,
                cause="410 Civil",
            )

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
