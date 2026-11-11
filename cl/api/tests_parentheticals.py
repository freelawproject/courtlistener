from http import HTTPStatus
from typing import Any

from asgiref.sync import async_to_sync, sync_to_async
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse

from cl.search.factories import (
    CitationWithParentsFactory,
    OpinionWithParentsFactory,
    ParentheticalFactory,
    ParentheticalGroupFactory,
)
from cl.tests.cases import TestCase
from cl.tests.utils import AsyncAPIClient, make_client
from cl.users.factories import UserProfileWithParentsFactory


class ParentheticalAPITest(TestCase):
    """Tests for the v4 /parentheticals/ endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create a user, two described opinions and a citing opinion with
        four parentheticals of distinct scores.
        """
        # Any authenticated user can read; DjangoModelPermissions only gates
        # write methods.
        cls.user_profile = UserProfileWithParentsFactory.create()

        # Two described opinions so we can prove filtering isolates results.
        cls.described_a = OpinionWithParentsFactory.create()
        cls.described_b = OpinionWithParentsFactory.create()
        cls.describing = OpinionWithParentsFactory.create()
        CitationWithParentsFactory.create(
            cluster=cls.describing.cluster,
            volume=576,
            reporter="U.S.",
            page="644",
        )

        # Three parentheticals describing opinion A, authored by `describing`,
        # with distinct scores so ordering is observable.
        cls.pa_high = ParentheticalFactory.create(
            described_opinion=cls.described_a,
            describing_opinion=cls.describing,
            text="high score parenthetical",
            score=0.9,
        )
        cls.pa_mid = ParentheticalFactory.create(
            described_opinion=cls.described_a,
            describing_opinion=cls.describing,
            text="mid score parenthetical",
            score=0.5,
        )
        cls.pa_low = ParentheticalFactory.create(
            described_opinion=cls.described_a,
            describing_opinion=cls.describing,
            text="low score parenthetical",
            score=0.1,
        )
        # One parenthetical describing opinion B (different described opinion).
        cls.pb = ParentheticalFactory.create(
            described_opinion=cls.described_b,
            describing_opinion=cls.describing,
            text="describes B",
            score=0.7,
        )

        cls.list_path = reverse("parenthetical-list", kwargs={"version": "v4"})

    def setUp(self) -> None:
        """Build an API client authenticated as the test user."""
        self.async_client = make_client(self.user_profile.user.pk)

    async def _get(self, params: dict[str, Any] | None = None) -> Any:
        """Request the parentheticals list with the given query params."""
        return await self.async_client.get(self.list_path, params or {})

    async def test_list_requires_authentication(self) -> None:
        """Anonymous users cannot read the endpoint."""
        r = await AsyncAPIClient().get(self.list_path)
        self.assertIn(
            r.status_code,
            (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN),
        )

    def test_endpoint_is_not_available_in_v3(self) -> None:
        """The endpoint is new, so it is only registered in v4."""
        with self.assertRaises(NoReverseMatch):
            reverse("parenthetical-list", kwargs={"version": "v3"})

    async def test_filter_by_described_opinion(self) -> None:
        """described_opinion returns the parentheticals describing that
        opinion, and excludes others."""
        r = await self._get({"described_opinion": self.described_a.pk})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        ids = {row["id"] for row in r.data["results"]}
        self.assertEqual(
            ids, {self.pa_high.pk, self.pa_mid.pk, self.pa_low.pk}
        )

    async def test_filter_by_describing_opinion(self) -> None:
        """describing_opinion returns the parentheticals authored by an
        opinion (the table-of-authorities direction)."""
        r = await self._get({"describing_opinion": self.describing.pk})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        ids = {row["id"] for row in r.data["results"]}
        self.assertEqual(
            ids,
            {self.pa_high.pk, self.pa_mid.pk, self.pa_low.pk, self.pb.pk},
        )

    async def test_default_ordering_by_id_desc(self) -> None:
        """Results page by descending id, the default cursor key."""
        r = await self._get({"described_opinion": self.described_a.pk})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        ids = [row["id"] for row in r.data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))

    async def test_order_by_score(self) -> None:
        """order_by=-score returns the most descriptive parentheticals first,
        like the Summaries tab."""
        r = await self._get(
            {"described_opinion": self.described_a.pk, "order_by": "-score"}
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        ids = [row["id"] for row in r.data["results"]]
        self.assertEqual(
            ids, [self.pa_high.pk, self.pa_mid.pk, self.pa_low.pk]
        )

    async def test_order_by_unindexed_field_is_ignored(self) -> None:
        """Ordering by a field outside ordering_fields falls back to the
        default ordering instead of sorting on an unindexed column."""
        r = await self._get(
            {"described_opinion": self.described_a.pk, "order_by": "text"}
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        ids = [row["id"] for row in r.data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))

    async def test_score_filter(self) -> None:
        """score__gte filters out low-scoring parentheticals."""
        r = await self._get(
            {"described_opinion": self.described_a.pk, "score__gte": "0.4"}
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        ids = {row["id"] for row in r.data["results"]}
        self.assertEqual(ids, {self.pa_high.pk, self.pa_mid.pk})

    async def test_response_includes_display_context(self) -> None:
        """Each row carries the text, score, links and the citing case's
        context, so a client can render it without a follow-up request."""
        r = await self._get(
            {"described_opinion": self.described_a.pk, "id": self.pa_high.pk}
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        row = r.data["results"][0]
        describing_cluster = self.describing.cluster
        described_cluster = self.described_a.cluster
        self.assertEqual(row["text"], "high score parenthetical")
        self.assertEqual(row["score"], 0.9)
        self.assertEqual(row["describing_opinion_id"], self.describing.pk)
        self.assertEqual(row["described_opinion_id"], self.described_a.pk)
        self.assertEqual(
            row["describing_opinion_case_name"], describing_cluster.case_name
        )
        self.assertEqual(
            row["described_opinion_case_name"], described_cluster.case_name
        )
        self.assertEqual(row["describing_opinion_citation"], "576 U.S. 644")
        self.assertEqual(
            row["describing_opinion_date_filed"],
            str(describing_cluster.date_filed),
        )
        self.assertEqual(
            row["describing_opinion_court_id"],
            describing_cluster.docket.court_id,
        )
        self.assertEqual(
            row["absolute_url"],
            reverse(
                "view_case_summaries",
                args=[described_cluster.pk, described_cluster.slug],
            ),
        )

    async def test_group_empty_when_not_computed(self) -> None:
        """A parenthetical whose group was never computed serializes with a
        null group. The API must not compute groups on demand."""
        r = await self._get({"described_opinion": self.described_a.pk})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        for row in r.data["results"]:
            self.assertIsNone(row["group"])

    async def test_group_embedded_when_present(self) -> None:
        """When a group already exists it is embedded inline with its
        aggregate metadata and representative parenthetical."""
        group = await sync_to_async(ParentheticalGroupFactory.create)(
            opinion=self.described_a,
            representative=self.pa_high,
            score=0.88,
            size=3,
        )
        self.pa_high.group = group
        await sync_to_async(self.pa_high.save)()

        r = await self._get(
            {"described_opinion": self.described_a.pk, "id": self.pa_high.pk}
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        row = r.data["results"][0]
        self.assertEqual(row["group"]["size"], 3)
        self.assertEqual(row["group"]["score"], 0.88)
        self.assertEqual(row["group"]["representative_id"], self.pa_high.pk)
        self.assertTrue(
            row["group"]["representative"].endswith(
                reverse(
                    "parenthetical-detail",
                    kwargs={"version": "v4", "pk": self.pa_high.pk},
                )
            )
        )

    def test_queries_are_bounded_and_skip_text_fields(self) -> None:
        """Listing parentheticals issues a constant number of queries and
        never loads the opinions' text fields."""
        rows: list[int] = []

        def hit() -> tuple[int, list[str]]:
            """Request the list and return the query count and the SQL."""
            with CaptureQueriesContext(connection) as ctx:
                r = async_to_sync(self.async_client.get)(
                    self.list_path, {"described_opinion": self.described_b.pk}
                )
                self.assertEqual(r.status_code, HTTPStatus.OK)
                rows.append(len(r.json()["results"]))
            return len(ctx.captured_queries), [
                q["sql"] for q in ctx.captured_queries
            ]

        baseline, _ = hit()
        for i in range(5):
            describing = OpinionWithParentsFactory.create()
            CitationWithParentsFactory.create(cluster=describing.cluster)
            ParentheticalFactory.create(
                described_opinion=self.described_b,
                describing_opinion=describing,
                text=f"extra {i}",
            )
        count, sqls = hit()

        # Each new row has its own citing opinion, cluster and citation.
        self.assertEqual(rows, [1, 6])
        self.assertEqual(count, baseline)
        for sql in sqls:
            for column in ("plain_text", "html_with_citations", "syllabus"):
                self.assertNotIn(column, sql)

    async def test_empty_filters_ignored(self) -> None:
        """Empty filter params don't error (NoEmptyFilterSet behavior)."""
        r = await self._get({"described_opinion": ""})
        self.assertEqual(r.status_code, HTTPStatus.OK)
