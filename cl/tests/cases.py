import re
from datetime import datetime
from typing import cast
from urllib.parse import parse_qs, urlparse

from asgiref.sync import sync_to_async
from django import test
from django.contrib.staticfiles import testing
from django.core.management import call_command
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils.dateformat import format
from django.utils.html import strip_tags
from django_elasticsearch_dsl.registries import registry
from lxml import etree, html
from lxml.html import HtmlElement
from rest_framework.test import APITestCase as DRFTestCase
from rest_framework.utils.serializer_helpers import ReturnList

from cl.alerts.management.commands.cl_send_scheduled_alerts import (
    get_cut_off_date,
)
from cl.lib.redis_utils import get_redis_interface
from cl.search.models import SEARCH_TYPES


class RestartRateLimitMixin:
    """Restart the rate limiter counter to avoid getting blocked in frontend
    after tests.
    """

    @classmethod
    def restart_rate_limit(cls):
        r = get_redis_interface("CACHE")
        keys = r.keys(":1:rl:*")
        if keys:
            r.delete(*keys)

    @classmethod
    def tearDownClass(cls):
        cls.restart_rate_limit()
        super().tearDownClass()


class RestartSentEmailQuotaMixin:
    """Restart sent email quota in redis."""

    @classmethod
    def restart_sent_email_quota(cls, prefix="email"):
        r = get_redis_interface("CACHE")
        keys = r.keys(f"{prefix}:*")

        if keys:
            r.delete(*keys)

    def tearDown(self):
        self.restart_sent_email_quota()
        super().tearDown()


class TestCase(
    RestartRateLimitMixin,
    test.TestCase,
):
    pass


class TransactionTestCase(
    RestartRateLimitMixin,
    test.TransactionTestCase,
):
    pass


class LiveServerTestCase(
    RestartRateLimitMixin,
    test.LiveServerTestCase,
):
    pass


class StaticLiveServerTestCase(
    RestartRateLimitMixin,
    testing.StaticLiveServerTestCase,
):
    pass


class APITestCase(
    RestartRateLimitMixin,
    DRFTestCase,
):
    pass


@test.override_settings(
    ELASTICSEARCH_DSL_AUTO_REFRESH=True,
    ELASTICSEARCH_DISABLED=False,
)
class ESIndexTestCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        _index_suffixe = cls.__name__.lower()
        for index in registry.get_indices():
            index._name += f"-{_index_suffixe}"
            index.create(ignore=400)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        for index in registry.get_indices():
            index.delete(ignore=[404, 400])
            index._name = index._name.split("-")[0]
        super().tearDownClass()

    @classmethod
    def rebuild_index(cls, model):
        """Create and populate the Elasticsearch index and mapping"""
        call_command("search_index", "--rebuild", "-f", "--models", model)

    @classmethod
    def create_index(cls, model):
        """Create the elasticsearch index."""
        call_command("search_index", "--create", "-f", "--models", model)

    @classmethod
    def delete_index(cls, model):
        """Delete the elasticsearch index."""
        call_command("search_index", "--delete", "-f", "--models", model)

    @classmethod
    def restart_celery_throttle_key(cls):
        r = get_redis_interface("CACHE")
        keys = r.keys("celery_throttle:*")
        if keys:
            r.delete(*keys)
        keys = r.keys("celery_throttle:*")

    def tearDown(self) -> None:
        self.restart_celery_throttle_key()
        super().tearDown()

    def assert_es_feed_content(self, node_tests, response, namespaces):
        """Common assertion that checks the presence of specified nodes in an
        ES feed test.

        :param node_tests: A list of tuples, each containing an XPath query
        string and the expected count of nodes.
        :param response: The HTTP response that contains XML content.
        :param namespaces: A dictionary of XML namespaces required to parse
        the XPath expressions.
        :return: A lxml etree object parsed from the response content.
        """
        xml_tree = etree.fromstring(response.content)
        for test_content, count in node_tests:
            with self.subTest(test_content=test_content):
                node_count = len(
                    xml_tree.xpath(test_content, namespaces=namespaces)
                )  # type: ignore
                self.assertEqual(
                    node_count,
                    count,
                    msg=f"Did not find {count} node(s) with XPath query: {test_content}. "
                    f"Instead found: {node_count}",
                )

        return xml_tree

    @staticmethod
    def _get_frontend_counts_text(r):
        """Extract and clean frontend counts text from the response content."""
        tree = html.fromstring(r.content.decode())
        counts_h2_element = tree.xpath('//h2[@id="result-count"]')[0]
        counts_text = " ".join(counts_h2_element.xpath(".//text()"))
        counts_text = counts_text.replace("&nbsp;", " ")
        counts_text = counts_text.split()
        return " ".join(counts_text)


class CountESTasksTestCase(SimpleTestCase):
    def setUp(self):
        self.task_call_count = 0

    def count_task_calls(
        self, task, immutable_signature, *args, **kwargs
    ) -> None:
        """Wraps the task to count its calls and assert the expected count."""
        # Increment the call count
        self.task_call_count += 1
        # Call the task
        if immutable_signature:
            return task.s(*args, **kwargs)
        else:
            task.apply_async(args=args, kwargs=kwargs)

    def reset_and_assert_task_count(self, expected) -> None:
        """Resets the task call count and asserts the expected number of calls."""

        assert self.task_call_count == expected, (
            f"Expected {expected} task calls, but got {self.task_call_count}"
        )
        self.task_call_count = 0


class V4SearchAPIAssertions(SimpleTestCase):
    """Common assertions for V4 Search API tests."""

    async def _compare_field(
        self,
        meta_field,
        meta_value,
        meta_fields_to_compare,
        content_to_compare,
    ):
        get_meta_expected_value = meta_fields_to_compare.get(meta_field)
        meta_expected_value = await sync_to_async(get_meta_expected_value)(
            content_to_compare
        )
        if meta_field == "score":
            # Special case for the score field. Only confirm the presence of
            # keys and avoid comparing values, as they differ in each response.
            self.assertEqual(
                set(meta_value.keys()),
                set(meta_expected_value.keys()),
                f"The keys in field '{meta_field}' do not match.",
            )
            for score_value in meta_value.values():
                self.assertIsNotNone(
                    score_value, "The score value can't be None."
                )

        else:
            self.assertEqual(
                meta_value,
                meta_expected_value,
                f"The field '{meta_field}' does not match.",
            )

    async def _test_api_fields_content(
        self,
        api_response,
        content_to_compare,
        fields_to_compare,
        child_document_keys,
        meta_fields_to_compare,
    ):
        for (
            field,
            get_expected_value,
        ) in fields_to_compare.items():
            with self.subTest(field=field):
                if isinstance(api_response, ReturnList):
                    parent_document = api_response[0]
                else:
                    parent_document = api_response.data["results"][0]
                actual_value = parent_document.get(field)
                if field in ["recap_documents", "opinions", "positions"]:
                    child_document = actual_value[0]
                    for child_field, child_value in child_document.items():
                        with self.subTest(child_field=child_field):
                            if child_field == "meta":
                                for (
                                    meta_field,
                                    meta_value,
                                ) in child_value.items():
                                    with self.subTest(meta_field=meta_field):
                                        self.assertFalse(
                                            meta_field == "score",
                                            msg="score key should not be present in nested documents",
                                        )
                                        await self._compare_field(
                                            meta_field,
                                            meta_value,
                                            meta_fields_to_compare,
                                            content_to_compare,
                                        )
                            else:
                                await self._compare_field(
                                    child_field,
                                    child_value,
                                    child_document_keys,
                                    content_to_compare,
                                )
                elif field == "meta":
                    for meta_field, meta_value in actual_value.items():
                        with self.subTest(meta_field=meta_field):
                            await self._compare_field(
                                meta_field,
                                meta_value,
                                meta_fields_to_compare,
                                content_to_compare,
                            )
                else:
                    expected_value = await sync_to_async(get_expected_value)(
                        content_to_compare
                    )
                    self.assertEqual(
                        actual_value,
                        expected_value,
                        f"Parent field '{field}' does not match.",
                    )

    def _test_results_ordering(self, test, field, version="v4"):
        """Ensure dockets appear in the response in a specific order."""

        with self.subTest(test=test, msg=f"{test['name']}"):
            r = self.client.get(
                reverse("search-list", kwargs={"version": version}),
                test["search_params"],
            )

            expected_order_key = "expected_order"
            if version == "v3":
                expected_order_key = (
                    "expected_order_v3"
                    if "expected_order_v3" in test
                    else "expected_order"
                )

            self.assertEqual(
                len(r.data["results"]), len(test[expected_order_key])
            )
            # Note that dockets where the date_field is null are sent to the bottom
            # of the results
            actual_order = [result[field] for result in r.data["results"]]
            self.assertEqual(
                actual_order,
                test[expected_order_key],
                msg=f"Expected order {test[expected_order_key]}, but got {actual_order} for "
                f"Search type: {test['search_params']['type']}",
            )

    def _assert_order_in_html(
        self, decoded_content: str, expected_order: list
    ) -> None:
        """Assert that the expected order of documents appears correctly in the
        HTML content."""

        for i in range(len(expected_order) - 1):
            self.assertTrue(
                decoded_content.index(str(expected_order[i]))
                < decoded_content.index(str(expected_order[i + 1])),
                f"Expected {expected_order[i]} to appear before {expected_order[i + 1]} in the HTML content.",
            )

    async def _test_article_count(self, params, expected_count, field_name):
        r = await self.async_client.get("/", params)
        tree = html.fromstring(r.content.decode())
        got = len(tree.xpath("//article"))
        self.assertEqual(
            got,
            expected_count,
            msg=f"Did not get the right number of search results in Frontend with {field_name} "
            "filter applied.\n"
            f"Expected: {expected_count}\n"
            f"     Got: {got}\n\n"
            f"Params were: {params}",
        )
        return r

    def _test_page_variables(
        self, response, test_case, current_page, search_type
    ):
        """Ensure the page variables are the correct ones according to the
        current page."""

        # Test page
        self.assertEqual(
            len(response.data["results"]),
            test_case["results"],
            msg="Results in page didn't match.",
        )
        self.assertEqual(
            response.data["count"],
            test_case["count_exact"],
            msg="Results count didn't match.",
        )
        if search_type == SEARCH_TYPES.RECAP:
            self.assertEqual(
                response.data["document_count"],
                test_case["document_count"],
                msg="Document count didn't match.",
            )
        else:
            self.assertNotIn(
                "document_count",
                response.data,
                msg="Document count should not be present.",
            )

        next_page = response.data["next"]
        expected_next_page = test_case["next"]
        if expected_next_page:
            self.assertTrue(next_page, msg="Next page value didn't match")
            current_page = next_page
        else:
            self.assertFalse(next_page, msg="Next page value didn't match")

        previous_page = response.data["previous"]
        expected_previous_page = test_case["previous"]
        if expected_previous_page:
            self.assertTrue(
                previous_page,
                msg="Previous page value didn't match",
            )
        else:
            self.assertFalse(
                previous_page,
                msg="Previous page value didn't match",
            )
        return next_page, previous_page, current_page


class SearchAlertsAssertions:
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
            f"Expected: {expected_count} - Got: {got}\n\n",
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

    @staticmethod
    def clean_case_title(case_title):
        """Clean the case text to get the case name to compare it.
        Input: 1. SUBPOENAS SERVED CASE ()
        Output: SUBPOENAS SERVED CASE
        """

        # Split the string by the dot and take everything after it.
        parts = case_title.split(".", 1)
        if len(parts) > 1:
            case_title = parts[1].strip()
        # Remove everything from the first open parenthesis to the end
        case_title = re.split(r"\s*\(", case_title)[0].strip()
        return case_title

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
            msg=f"Did not get the right number of hits for the alert {alert_title}. "
            f"Expected: {expected_hits} - Got: {len(alert_cases)}\n\n",
        )
        if case_title:
            for case in alert_cases:
                case_text = " ".join(
                    [element.strip() for element in case.xpath(".//text()")]
                )
                case_text_cleaned = self.clean_case_title(case_text)
                if case_title == case_text_cleaned:
                    child_hit_count = len(
                        case.xpath(
                            "following-sibling::ul[1]/li/a | following-sibling::ul[1]/li/strong"
                        )
                    )
                    self.assertEqual(
                        child_hit_count,
                        expected_child_hits,
                        msg=f"Did not get the right number of child hits for the case {case_title}. "
                        f"Expected: {expected_child_hits} - Got: {child_hit_count}\n\n",
                    )
                    break

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
        # Get the alert cases from the HTML.
        alert_cases = self._extract_cases_from_alert(tree, alert_title)

        def extract_child_descriptions(case_item):
            child_documents = case_item.xpath("./following-sibling::ul[1]/li")
            results = []
            for li in child_documents:
                child_tag = li.xpath(".//a | .//strong")[0]
                full_text = child_tag.text_content()
                first_part = full_text.split("\u2014")[0].strip()
                results.append(first_part)

            return results

        child_descriptions = set()
        for case in alert_cases:
            case_text = "".join(case.xpath(".//text()")).strip()
            case_text_cleaned = self.clean_case_title(case_text)
            if case_title == case_text_cleaned:
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
        nested_field="recap_documents",
    ):
        """Confirm the following assertions for the search alert webhook:
        - An specific alert webhook was triggered.
        - The specified alert contains the expected number of hits.
        - The specified case contains the expected number of child hits.
        """

        matched_alert_name = None
        matched_case_title = None
        for webhook in webhooks:
            if webhook["payload"]["alert"]["name"] == alert_title:
                webhook_cases = webhook["payload"]["results"]
                self.assertEqual(
                    len(webhook_cases),
                    expected_hits,
                    msg=f"Did not get the right number of hits for the alert {alert_title}. ",
                )
                matched_alert_name = True
                for case in webhook["payload"]["results"]:
                    if case_title == strip_tags(case["caseName"]):
                        matched_case_title = True
                        if nested_field is None:
                            self.assertTrue(nested_field not in case)
                            continue
                        self.assertEqual(
                            len(case[nested_field]),
                            expected_child_hits,
                            msg=f"Did not get the right number of child documents for the case {case_title}. ",
                        )
        self.assertTrue(matched_alert_name, msg="Alert name didn't match")
        self.assertTrue(matched_case_title, msg="Case title didn't match")

    def _count_percolator_webhook_hits_and_child_hits(
        self,
        webhooks,
        alert_title,
        expected_hits,
        expected_child_hits,
        expected_child_descriptions,
    ):
        """Confirm the following assertions for the percolator search alert
        webhook:
        - The specified alert was triggered the expected number of times.
        - The specified alert contains only 1 hit.
        - If the specified case contains child documents it must be 1.
        """

        alert_title_webhooks = 0
        alert_child_hits = 0
        alert_child_ids = set()
        for webhook in webhooks:
            if webhook["payload"]["alert"]["name"] == alert_title:
                alert_title_webhooks += 1

                hits = webhook["payload"]["results"]

                self.assertEqual(
                    1,
                    len(hits),
                    msg="Did not get the right number of hits for the case {}. ".format(
                        webhook["payload"]["results"][0]["caseName"]
                    ),
                )
                alert_child_hits = alert_child_hits + len(
                    webhook["payload"]["results"][0]["recap_documents"]
                )
                for rd in webhook["payload"]["results"][0]["recap_documents"]:
                    alert_child_ids.add(rd["id"])

        self.assertEqual(
            alert_title_webhooks,
            expected_hits,
            msg=f"Did not get the right number of webhooks for alert {alert_title}. ",
        )
        self.assertEqual(
            alert_child_hits,
            expected_child_hits,
            msg=f"Did not get the right number of child hits for alert {alert_title}. ",
        )
        if expected_child_descriptions:
            self.assertEqual(
                alert_child_ids,
                set(expected_child_descriptions),
                msg=f"Did not get the right child hits IDs for alert {alert_title}. ",
            )

    def _assert_webhook_hit_hl(
        self,
        webhooks,
        alert_title,
        field_name,
        hl_expected,
        child_field,
        nested_field="recap_documents",
    ):
        """Assert Hl in webhook fields."""
        for webhook in webhooks:
            if webhook["payload"]["alert"]["name"] == alert_title:
                hit = webhook["payload"]["results"][0]
                if child_field:
                    self.assertNotIn(
                        "score",
                        hit[nested_field][0]["meta"],
                        msg="score shouldn't be present on webhook nested documents",
                    )
                    child_field_content = hit[nested_field][0][field_name]
                    self.assertIn(
                        hl_expected,
                        child_field_content,
                        msg=f"Did not get the HL content in field: {field_name}. ",
                    )
                else:
                    self.assertNotIn(
                        "score",
                        hit["meta"],
                        msg="score shouldn't be present on webhook main document",
                    )
                    parent_field_content = hit[field_name]
                    self.assertIn(
                        hl_expected,
                        parent_field_content,
                        msg=f"Did not get the HL content in field: {field_name}. ",
                    )

    def _assert_timestamp_filter(
        self, html_content, rate, date, sweep_index=False
    ):
        """Confirm that timestamp filter is properly set in the
        'View Full Results' URL.
        """
        view_results_url = html.fromstring(str(html_content)).xpath(
            '//a[text()="View Full Results / Edit this Alert"]/@href'
        )
        parsed_url = urlparse(view_results_url[0])
        params = parse_qs(parsed_url.query)
        cut_off_date = get_cut_off_date(rate, date, sweep_index)
        iso_datetime = (
            cut_off_date.strftime("%Y-%m-%dT%H:%M:%S")
            if isinstance(cut_off_date, datetime)
            else cut_off_date.strftime("%Y-%m-%d")
        )
        self.assertIn(f"timestamp:[{iso_datetime} TO *]", params["q"][0])

    def _assert_date_updated(self, date_to_compare, html_content, txt_content):
        """Confirm that date_updated is properly set in the alert email."""

        self.assertIn(
            f"Date Updated: {format(date_to_compare, 'F jS, Y h:i a T')}",
            html_content,
        )

        self.assertIn(
            f"Date Updated: {format(date_to_compare, 'F jS, Y h:i a T')}",
            txt_content,
        )

    @staticmethod
    def _extract_snippet_content(html_content: str):
        html_doc = html.fromstring(html_content)
        snippet_content = cast(
            list[HtmlElement],
            html_doc.xpath('//*[self::p or self::span][@id="snippet"]'),
        )
        assert snippet_content, "No snippet found"

        snippet_text = snippet_content[0].text_content().strip()
        return snippet_text.replace("…", "").replace("&hellip;", "")
