from unittest.mock import patch

from django.db import connection
from django.test import AsyncClient, override_settings
from django.urls import reverse
from django.utils import timezone
from lxml import html as lhtml
from waffle.testutils import override_flag

from cl.lib.test_helpers import (
    CourtTestCase,
    PeopleTestCase,
    RECAPSearchTestCase,
    SearchTestCase,
    SimpleUserDataMixin,
)
from cl.search.models import Docket, Opinion, RECAPDocument
from cl.search.utils import get_v2_homepage_stats
from cl.tests.cases import TestCase

FAKE_STATS = {
    "alerts_in_last_ten": 0,
    "queries_in_last_ten": 0,
    "api_in_last_ten": 0,
    "minutes_of_oa": 0,
    "opinion_count": 0,
    "docket_count": 0,
    "recap_doc_count": 0,
}


def data_value_for_label(label_text: str, html: str) -> str:
    """Get the <data> value in a <dd> element for a given <dt> label"""
    tree = lhtml.fromstring(html)
    dt_nodes = tree.xpath(f"//dt[normalize-space(text())='{label_text}']")
    assert dt_nodes, f"Missing dt with label: {label_text}"
    container = dt_nodes[0].getparent()
    data_nodes = container.xpath(".//dd/data/@value")
    assert data_nodes, f"Missing <data> value for: {label_text}"
    return data_nodes[0]


@override_settings(WAFFLE_CACHE_PREFIX="test_homepage_transitional_waffle")
class HomepageTransitionalTest(TestCase):
    """
    Transitional tests for current behavior that will change in the future as new templates are implemented.
    """

    def _assert_not_v2(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTemplateNotUsed(response, "v2_homepage.html")
        self.assertNotIn('x-data="header"', response.content.decode())

    @patch("cl.search.views.get_v2_homepage_stats", return_value=FAKE_STATS)
    @patch("cl.search.views.get_homepage_stats", return_value=FAKE_STATS)
    def test_flag_on_get_with_params_routes_to_legacy(
        self, _mock_homepage, _mock_v2_homepage
    ):
        # TODO: [redesign] Remove when new view for search results is implemented
        resp = self.client.get(reverse("show_results"), {"q": "test"})
        self._assert_not_v2(resp)

    @patch("cl.search.views.get_v2_homepage_stats", return_value=FAKE_STATS)
    @patch("cl.search.views.get_homepage_stats", return_value=FAKE_STATS)
    def test_flag_on_post_routes_to_legacy(
        self, _mock_homepage, _mock_v2_homepage
    ):
        # TODO: [redesign] Remove when new view to save search alerts is implemented
        resp = self.client.post(reverse("show_results"), data={"q": "test"})
        self._assert_not_v2(resp)


@patch("cl.search.views.get_v2_homepage_stats", return_value=FAKE_STATS)
@patch("cl.search.views.get_homepage_stats", return_value=FAKE_STATS)
@override_settings(WAFFLE_CACHE_PREFIX="test_homepage_routing_waffle")
class HomepageRoutingTest(TestCase):
    """
    Router chooses legacy vs new homepage correctly.
    We patch methods to get stats so routing tests don't interact with the DB/Redis.
    """

    @override_flag("use_new_design", False)
    def test_flag_off_routes_to_legacy(self, *mocks):
        resp = self.client.get(reverse("show_results"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "homepage.html")
        self.assertNotIn('x-data="header"', resp.content.decode())

    @override_flag("use_new_design", True)
    def test_flag_on_get_no_params_routes_to_new_homepage(self, *mocks):
        resp = self.client.get(reverse("show_results"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "v2_homepage.html")


@override_flag("use_new_design", True)
@override_settings(WAFFLE_CACHE_PREFIX="test_homepage_stats_smoke_waffle")
class HomepageStatsSmokeTest(TestCase):
    """Minimal test for stats block rendering on the new homepage."""

    def test_stats_rendered(self):
        resp = self.client.get(reverse("show_results"))
        html = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "v2_homepage.html")
        self.assertIn("Number of decisions in our system", html)
        self.assertIn("Number of federal cases in the RECAP Archive", html)


@override_flag("use_new_design", True)
@override_settings(WAFFLE_CACHE_PREFIX="test_async_homepage_waffle")
class AsyncHomepageTest(SimpleUserDataMixin, TestCase):
    """Tests new homepage renders correctly for authenticated and anonymous users."""

    def setUp(self):
        self.async_client = AsyncClient()

    async def test_header_anonymous_user(self):
        await self.async_client.alogout()
        resp = await self.async_client.get(reverse("show_results"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(">Login</a>", resp.content.decode())
        self.assertNotIn('id="header-profile-menu"', resp.content.decode())

    async def test_header_authenticated_user(self):
        await self.async_client.alogin(username="pandora", password="password")
        resp = await self.async_client.get(reverse("show_results"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(">Login</a>", resp.content.decode())
        self.assertIn('id="header-profile-menu"', resp.content.decode())


@override_flag("use_new_design", True)
@override_settings(WAFFLE_CACHE_PREFIX="test_homepage_structure_waffle")
class HomepageStructureTest(SimpleUserDataMixin, TestCase):
    """Structural tests for the new homepage layout."""

    def test_header_variant(self):
        resp = self.client.get(reverse("show_results"))
        html = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "v2_homepage.html")
        self.assertIn('x-data="header"', html)
        # Ensure no search widget in header (homepage variant)
        self.assertNotIn(
            'x-data="search"', html.split("<header")[1].split("</header")[0]
        )

    def test_scroll_buttons_have_accessibility_attrs(self):
        resp = self.client.get(reverse("show_results"))
        html = resp.content.decode()
        self.assertIn('aria-label="Scroll actions left"', html)
        self.assertIn('aria-label="Scroll actions right"', html)
        self.assertIn('role="toolbar"', html)

    def test_stats_section_order_and_labels(self):
        resp = self.client.get(reverse("show_results"))
        html = resp.content.decode()
        self.assertIn('id="stats-title"', html)
        expected_labels = [
            "Number of decisions in our system",
            "Federal cases in the RECAP Archive",
            "Federal filings in the RECAP Archive",
            "Minutes of oral argument recordings in our system",
            "Number of searches conducted in the last ten days",
            "Number of alert emails sent over the last ten days",
            "Number of API calls made in the last ten days",
        ]
        for label in expected_labels:
            with self.subTest(label=label):
                self.assertIn(label, html, f"Not found in template: {label}")


@override_flag("use_new_design", True)
@override_settings(WAFFLE_CACHE_PREFIX="test_corpus_search_form_waffle")
class CorpusSearchFormTest(SimpleUserDataMixin, TestCase):
    """Tests for corpus search form rendering and accessibility."""

    @classmethod
    def setUpTestData(cls):
        """Fetch the homepage once and share across all tests"""
        super().setUpTestData()
        cls.response = cls.client_class().get(reverse("show_results"))
        cls.html = cls.response.content.decode()
        cls.tree = lhtml.fromstring(cls.html)

    def test_unique_form_field_ids(self):
        """Test that form fields have unique IDs across desktop and mobile forms"""
        tree = self.tree

        # Test common fields that appear in multiple fieldsets
        common_fields = ["case_name", "docket_number", "judge"]
        namespaces = ["opinions", "recap", "oral_arguments", "judges"]

        for field in common_fields:
            for namespace in namespaces:
                # Check desktop ID exists
                desktop_id = f"desktop_{namespace}_{field}"
                desktop_inputs = tree.xpath(f'//input[@id="{desktop_id}"]')

                # Check mobile ID exists
                mobile_id = f"mobile_{namespace}_{field}"
                mobile_inputs = tree.xpath(f'//input[@id="{mobile_id}"]')

                # Some fields may not exist in all namespaces
                # But if they exist, they should be unique
                if desktop_inputs:
                    self.assertEqual(
                        len(desktop_inputs),
                        1,
                        f"Desktop ID {desktop_id} should appear exactly once, found {len(desktop_inputs)}",
                    )

                if mobile_inputs:
                    self.assertEqual(
                        len(mobile_inputs),
                        1,
                        f"Mobile ID {mobile_id} should appear exactly once, found {len(mobile_inputs)}",
                    )

    def test_no_duplicate_ids_in_dom(self):
        """Test no duplicate ID attributes exist anywhere in the DOM

        Comprehensive check that validates HTML uniqueness constraint for ID
        attributes across the entire rendered page. This catches any duplicate
        IDs regardless of source (forms, components, static elements).

        This is the primary regression test for the duplicate ID bug.
        """
        tree = self.tree

        # Get all elements with id attribute
        all_ids = tree.xpath("//*[@id]/@id")

        # Find duplicates
        id_counts = {}
        for id_value in all_ids:
            id_counts[id_value] = id_counts.get(id_value, 0) + 1

        duplicates = {
            id_val: count for id_val, count in id_counts.items() if count > 1
        }

        self.assertEqual(
            duplicates,
            {},
            f"Found duplicate IDs in the DOM: {duplicates}",
        )

    def test_label_for_matches_input_id(self):
        """Test label 'for' attributes correctly reference existing input IDs

        Validates accessibility: every <label for="..."> must have exactly one
        matching element with that ID. Ensures the unique ID solution didn't
        break label/input associations.
        """
        tree = self.tree

        # Get all labels with 'for' attribute
        labels = tree.xpath("//label[@for]")

        for label in labels:
            label_for = label.get("for")
            # Find the corresponding input/select/textarea
            matching_inputs = tree.xpath(f'//*[@id="{label_for}"]')

            self.assertEqual(
                len(matching_inputs),
                1,
                f"Label with for='{label_for}' should have exactly one matching element, found {len(matching_inputs)}",
            )


@override_flag("use_new_design", True)
@patch("cl.search.utils.get_redis_interface")
@override_settings(WAFFLE_CACHE_PREFIX="test_homepage_stats_waffle")
class HomepageStatsTest(
    RECAPSearchTestCase,
    CourtTestCase,
    PeopleTestCase,
    SearchTestCase,
    TestCase,
):
    """Stats tests that checks values displayed correspond with actual data in the DB.

    Skips Redis to keep this test scoped to DB queries.
    """

    def _assert_equal_subtests(self, tests):
        for test in tests:
            with self.subTest(test=test):
                self.assertEqual(test["expected"], test["observed"])

    def test_count_from_db(self, mock_get_redis):
        """Ensure total estimate counters match queryset counts from the db."""
        mock_get_redis.return_value.mget.return_value = [None] * 10
        with connection.cursor() as cursor:
            tables = [
                m._meta.db_table for m in (Opinion, Docket, RECAPDocument)
            ]
            for table in tables:
                cursor.execute(
                    f"ANALYZE {connection.ops.quote_name(table)}"
                )  # Required for DB count estimates used in get_total_estimate_count

        opinion_count = Opinion.objects.count()
        docket_count = Docket.objects.count()
        recap_doc_count = RECAPDocument.objects.count()
        get_v2_homepage_stats.invalidate()

        resp = self.client.get(reverse("show_results"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "v2_homepage.html")

        html = resp.content.decode()

        tests = [
            {
                "expected": str(opinion_count),
                "observed": data_value_for_label(
                    "Number of decisions in our system", html
                ),
            },
            {
                "expected": str(docket_count),
                "observed": data_value_for_label(
                    "Federal cases in the RECAP Archive", html
                ),
            },
            {
                "expected": str(recap_doc_count),
                "observed": data_value_for_label(
                    "Federal filings in the RECAP Archive", html
                ),
            },
        ]
        self._assert_equal_subtests(tests)

    def test_last_ten_days_aggregates(self, mock_get_redis):
        """Ensure only last 10 days stats appear in HTML."""
        now = timezone.now()
        date_today = now.date().isoformat()

        # Mock Redis to return stats for today only (in-window)
        def mock_mget(*keys):
            results = []
            for key in keys:
                if f"alerts.sent.{date_today}" in key:
                    results.append(b"3")  # Redis returns bytes
                elif f"search.results.{date_today}" in key:
                    results.append(b"9")  # Redis returns bytes
                elif f"api:v4.d:{date_today}.count" in key:
                    results.append(b"0")
                else:
                    results.append(None)  # Out-of-window dates return None
            return results

        mock_get_redis.return_value.mget.side_effect = mock_mget

        get_v2_homepage_stats.invalidate()
        resp = self.client.get(reverse("show_results"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "v2_homepage.html")

        html = resp.content.decode()

        tests = [
            {
                "expected": "3",
                "observed": data_value_for_label(
                    "Number of alert emails sent over the last ten days", html
                ),
            },
            {
                "expected": "9",
                "observed": data_value_for_label(
                    "Number of searches conducted in the last ten days", html
                ),
            },
        ]
        self._assert_equal_subtests(tests)
