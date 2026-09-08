from http import HTTPStatus

from asgiref.sync import sync_to_async
from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cl.search.factories import (
    OpinionWithParentsFactory,
    ParentheticalFactory,
    ParentheticalGroupFactory,
)
from cl.tests.cases import TestCase
from cl.tests.utils import make_client
from cl.users.factories import UserProfileWithParentsFactory


class ParentheticalAPITest(TestCase):
    """Tests for the v4 /parentheticals/ endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        # An authenticated user is enough for read access; DjangoModelPermissions
        # only gates write methods.
        cls.user_profile = UserProfileWithParentsFactory.create()
        ps = Permission.objects.filter(codename="has_recap_api_access")
        cls.user_profile.user.user_permissions.add(*ps)

        # Two described opinions so we can prove filtering isolates results.
        cls.described_a = OpinionWithParentsFactory.create()
        cls.described_b = OpinionWithParentsFactory.create()
        cls.describing = OpinionWithParentsFactory.create()

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
        self.client = make_client(self.user_profile.user.pk)

    async def _get(self, params=None):
        return await self.client.get(self.list_path, params or {})

    async def test_list_requires_authentication(self) -> None:
        """Anonymous users cannot read the endpoint."""
        from cl.tests.utils import AsyncAPIClient

        anon = AsyncAPIClient()
        r = await anon.get(self.list_path)
        self.assertIn(
            r.status_code,
            (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN),
        )

    async def test_filter_by_described_opinion(self) -> None:
        """described_opinion returns the parentheticals describing that
        opinion, and excludes others."""
        r = await self._get({"described_opinion": self.described_a.pk})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        ids = {row["id"] for row in r.data["results"]}
        self.assertEqual(
            ids, {self.pa_high.pk, self.pa_mid.pk, self.pa_low.pk}
        )
        self.assertNotIn(self.pb.pk, ids)

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
        """Results page by descending id (stable cursor key); relevance is
        expressed via the score filter, not ordering."""
        r = await self._get({"described_opinion": self.described_a.pk})
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

    async def test_response_includes_links_and_text(self) -> None:
        """Each row carries the text, score, and links to both opinions so a
        client can render it without a follow-up request."""
        r = await self._get({"described_opinion": self.described_a.pk})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        row = r.data["results"][0]
        for key in (
            "text",
            "score",
            "describing_opinion",
            "described_opinion",
            "group",
            "absolute_url",
        ):
            self.assertIn(key, row)

    async def test_group_empty_when_not_computed(self) -> None:
        """A parenthetical whose group was never computed serializes with a
        null group. The API must not compute groups on demand."""
        r = await self._get({"described_opinion": self.described_a.pk})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        for row in r.data["results"]:
            self.assertIsNone(row["group"])

    async def test_group_embedded_when_present(self) -> None:
        """When a group already exists it is embedded inline with its
        aggregate metadata."""
        group = await sync_to_async(ParentheticalGroupFactory.create)(
            opinion=self.described_a,
            representative=self.pa_high,
            score=0.88,
            size=3,
        )
        self.pa_high.group = group
        await sync_to_async(self.pa_high.save)()

        r = await self._get({"described_opinion": self.described_a.pk})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        row = next(
            row for row in r.data["results"] if row["id"] == self.pa_high.pk
        )
        self.assertIsNotNone(row["group"])
        self.assertEqual(row["group"]["size"], 3)
        self.assertEqual(row["group"]["score"], 0.88)

    def test_no_n_plus_one_queries(self) -> None:
        """Listing many parentheticals issues a bounded number of queries
        regardless of row count (select_related avoids N+1)."""
        client = make_client(self.user_profile.user.pk)
        path = self.list_path

        def hit(expected_min_results):
            with CaptureQueriesContext(connection) as ctx:
                from asgiref.sync import async_to_sync

                resp = async_to_sync(client.get)(
                    path, {"describing_opinion": self.describing.pk}
                )
                self.assertEqual(resp.status_code, HTTPStatus.OK)
                self.assertGreaterEqual(
                    len(resp.data["results"]), expected_min_results
                )
            return len(ctx.captured_queries)

        baseline = hit(4)

        # Add more parentheticals authored by the same opinion.
        for i in range(5):
            ParentheticalFactory.create(
                described_opinion=self.described_b,
                describing_opinion=self.describing,
                text=f"extra {i}",
                score=0.2,
            )

        after = hit(9)
        # Query count must not grow with the number of rows (no N+1).
        self.assertLessEqual(after, baseline)

    async def test_empty_filters_ignored(self) -> None:
        """Empty filter params don't error (NoEmptyFilterSet behavior)."""
        r = await self._get({"described_opinion": ""})
        self.assertEqual(r.status_code, HTTPStatus.OK)
