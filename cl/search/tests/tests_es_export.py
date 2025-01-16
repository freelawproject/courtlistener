from django.core import mail
from django.core.management import call_command
from django.http import QueryDict
from django.urls import reverse

from cl.lib.search_utils import fetch_es_results_for_csv
from cl.lib.test_helpers import RECAPSearchTestCase
from cl.search.models import SEARCH_TYPES
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.users.factories import UserProfileWithParentsFactory


class ExportSearchTest(RECAPSearchTestCase, ESIndexTestCase, TestCase):

    errors = [
        ("Unbalance Quotes", 'q="test&type=o'),
        ("Unbalance Parentheses", "q=Leave)&type=o"),
        ("Bad syntax", "q=Leave /:&type=o"),
    ]

    @classmethod
    def setUpTestData(cls):
        cls.user_profile = UserProfileWithParentsFactory()
        cls.rebuild_index("search.Docket")
        super().setUpTestData()
        cls.rebuild_index("people_db.Person")
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def test_returns_empty_list_when_query_with_error(self) -> None:
        """Confirms the search helper returns an empty list when provided with
        invalid query parameters."""
        for description, query in self.errors:
            with self.subTest(description):
                results = fetch_es_results_for_csv(
                    QueryDict(query.encode(), mutable=True),
                    SEARCH_TYPES.OPINION,
                )
                self.assertEqual(len(results), 0)

    def test_limit_number_of_search_results(self) -> None:
        """Checks hat `fetch_es_results_for_csv` returns a list with a size
        equal to MAX_SEARCH_RESULTS_EXPORTED or the actual number of search
        results (if it's less than `MAX_SEARCH_RESULTS_EXPORTED`)
        """
        # This query should match all 5 judges indexed for this test
        query = "q=gender:Female&type=p"
        for i in range(6):
            with self.subTest(
                f"try to fetch only {i+1} results"
            ), self.settings(MAX_SEARCH_RESULTS_EXPORTED=i + 1):
                results = fetch_es_results_for_csv(
                    QueryDict(query.encode(), mutable=True),
                    SEARCH_TYPES.PEOPLE,
                )
                expected_result_count = min(
                    i + 1, 5
                )  # Cap at 5 (total matching results)
                self.assertEqual(len(results), expected_result_count)

    def test_can_flatten_nested_results(self) -> None:
        """checks `fetch_es_results_for_csv` correctly handles and flattens
        nested results."""
        # this query should match both docket records indexed
        query = "type=r&q=12-1235 OR Jackson"
        results = fetch_es_results_for_csv(
            QueryDict(query.encode(), mutable=True), SEARCH_TYPES.RECAP
        )
        # We expect 3 results because:
        #   - Docket 21-bk-1234 has 2 associated documents.
        #   - Docket 12-1235 has 1 associated document.
        #
        # The `fetch_es_results_for_csv` helper function should:
        #   - Flatten the results.
        #   - Add a row for each child document.
        self.assertEqual(len(results), 3)

    def test_avoids_sending_email_for_query_with_error(self) -> None:
        "Confirms we don't send emails when provided with invalid query"
        self.client.login(
            username=self.user_profile.user.username, password="password"
        )
        for description, query in self.errors:
            with self.subTest(description):
                self.client.post(
                    reverse("export_search_results"), {"query": query}
                )
                self.assertEqual(len(mail.outbox), 0)

    def test_do_not_send_empty_emails(self) -> None:
        """Confirms that no emails are sent when the search query returns no
        results"""
        self.client.login(
            username=self.user_profile.user.username, password="password"
        )
        self.client.post(
            reverse("export_search_results"), {"query": 'q="word"&type=r'}
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_email_with_attachment(self) -> None:
        "Confirms we dont send emails when provided with invalid query"
        self.client.login(
            username=self.user_profile.user.username, password="password"
        )
        self.client.post(
            reverse("export_search_results"), {"query": 'q="Jackson"&type=r'}
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "Your Search Results are Ready!"
        )
        self.assertEqual(mail.outbox[0].to[0], self.user_profile.user.email)
