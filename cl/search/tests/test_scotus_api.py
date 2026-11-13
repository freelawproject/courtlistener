from datetime import date
from http import HTTPStatus
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse

from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    ScotusDocketMetadataFactory,
)
from cl.search.models import Docket, ScotusDocketMetadata
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory

BASENAMES = ["scotusdocketmetadata"]


class ScotusAPITestCase(TestCase):
    """Shared SCOTUS data for the API tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create the users, dockets and metadata shared by the tests."""
        cls.user = UserFactory()
        cls.superuser = UserFactory(is_staff=True, is_superuser=True)
        cls.court = CourtFactory(id="scotus", jurisdiction="F")
        cls.docket = DocketFactory(court=cls.court, source=Docket.SCRAPER)
        cls.docket_2 = DocketFactory(court=cls.court, source=Docket.SCRAPER)
        cls.metadata = ScotusDocketMetadataFactory(
            docket=cls.docket,
            capital_case=True,
            date_discretionary_court_decision=date(2025, 6, 24),
            questions_presented_file="recap/gov.uscourts.scotus.1/qp.pdf",
        )
        cls.metadata_no_file = ScotusDocketMetadataFactory(docket=cls.docket_2)

    @staticmethod
    def list_path(basename: str) -> str:
        """Return the v4 list URL for an endpoint basename."""
        return reverse(f"{basename}-list", kwargs={"version": "v4"})

    @staticmethod
    def detail_path(basename: str, pk: int) -> str:
        """Return the v4 detail URL for an endpoint basename and pk."""
        return reverse(
            f"{basename}-detail", kwargs={"version": "v4", "pk": pk}
        )


class ScotusAPIRoutingTest(ScotusAPITestCase):
    """The SCOTUS endpoints exist in v4 only."""

    async def test_endpoints_are_absent_from_v3(self) -> None:
        """Are the endpoints missing from v3, both as routes and URLs?"""
        for basename in BASENAMES:
            with self.subTest(basename=basename):
                with self.assertRaises(NoReverseMatch):
                    reverse(f"{basename}-list", kwargs={"version": "v3"})
                path = self.list_path(basename).replace("/v4/", "/v3/")
                r = await self.async_client.get(path)
                self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)


class ScotusAPIPermissionTest(ScotusAPITestCase):
    """The SCOTUS endpoints require an account and are read only."""

    async def test_anonymous_users_are_rejected(self) -> None:
        """Do anonymous requests get a 401?"""
        for basename in BASENAMES:
            with self.subTest(basename=basename):
                r = await self.async_client.get(self.list_path(basename))
                self.assertEqual(r.status_code, HTTPStatus.UNAUTHORIZED)

    async def test_write_methods_are_rejected(self) -> None:
        """Are writes refused, even for superusers?

        Plain users fail the model permission check first (403); superusers
        pass it and then hit the read-only viewset (405).
        """
        targets = {
            "scotusdocketmetadata": (ScotusDocketMetadata, self.metadata.pk),
        }
        counts_before = {
            name: await model.objects.acount()
            for name, (model, _) in targets.items()
        }
        for user, expected in (
            (self.user, HTTPStatus.FORBIDDEN),
            (self.superuser, HTTPStatus.METHOD_NOT_ALLOWED),
        ):
            await self.async_client.aforce_login(user)
            for name, (_, pk) in targets.items():
                requests = [
                    ("post", self.list_path(name)),
                    ("put", self.detail_path(name, pk)),
                    ("patch", self.detail_path(name, pk)),
                    ("delete", self.detail_path(name, pk)),
                ]
                for method, path in requests:
                    with self.subTest(
                        user=user.username, endpoint=name, method=method
                    ):
                        r = await getattr(self.async_client, method)(path)
                        self.assertEqual(r.status_code, expected)
        for name, (model, _) in targets.items():
            with self.subTest(endpoint=name):
                self.assertEqual(
                    await model.objects.acount(), counts_before[name]
                )


class ScotusAPISerializationTest(ScotusAPITestCase):
    """The SCOTUS endpoints return SCOTUS fields and links."""

    def setUp(self) -> None:
        """Log in as a plain user."""
        self.async_client.force_login(self.user)

    @staticmethod
    def absolute(path: str) -> str:
        """Return the absolute URL the test client's host gives a path."""
        return f"http://testserver{path}"

    async def test_metadata(self) -> None:
        """Does metadata link its docket and expose its file as a URL?"""
        r = await self.async_client.get(
            self.detail_path("scotusdocketmetadata", self.metadata.pk)
        )
        data = r.json()
        self.assertEqual(
            set(data),
            {
                "resource_uri",
                "id",
                "docket",
                "date_created",
                "date_modified",
                "capital_case",
                "date_discretionary_court_decision",
                "linked_with",
                "questions_presented_url",
                "questions_presented_file",
            },
        )
        self.assertEqual(
            data["docket"],
            self.absolute(self.detail_path("docket", self.docket.pk)),
        )
        self.assertTrue(data["capital_case"])
        self.assertEqual(
            data["questions_presented_file"],
            self.absolute(self.metadata.questions_presented_file.url),
        )

        r = await self.async_client.get(
            self.detail_path("scotusdocketmetadata", self.metadata_no_file.pk)
        )
        self.assertIsNone(r.json()["questions_presented_file"])


class ScotusAPIFilterTest(ScotusAPITestCase):
    """The SCOTUS endpoints filter on their own fields and on related ones."""

    def setUp(self) -> None:
        """Log in as a plain user."""
        self.async_client.force_login(self.user)

    async def assert_filter_counts(
        self, basename: str, cases: list[tuple[dict, int]]
    ) -> None:
        """Check the number of results each set of query params returns."""
        for params, expected in cases:
            with self.subTest(endpoint=basename, params=params):
                r = await self.async_client.get(
                    self.list_path(basename), params
                )
                self.assertEqual(r.status_code, HTTPStatus.OK, r.json())
                self.assertEqual(len(r.json()["results"]), expected)

    async def test_metadata_filters(self) -> None:
        """Can metadata be filtered by its fields and its docket?"""
        await self.assert_filter_counts(
            "scotusdocketmetadata",
            [
                ({"id": self.metadata.pk}, 1),
                ({"docket": self.docket.pk}, 1),
                ({"docket__id": self.docket.pk}, 1),
                ({"capital_case": "true"}, 1),
                ({"capital_case": "false"}, 1),
                ({"date_discretionary_court_decision__year": 2025}, 1),
            ],
        )

    async def test_unknown_params_are_rejected(self) -> None:
        """Do typos in filter names return a 400 instead of everything?"""
        for basename in BASENAMES:
            with self.subTest(basename=basename):
                r = await self.async_client.get(
                    self.list_path(basename), {"bogus": "1"}
                )
                self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
                self.assertEqual(r.json()["unknown_params"], ["bogus"])


@mock.patch(
    "cl.api.utils.get_logging_prefix",
    return_value="api:test_counts",
)
class ScotusAPIQueryCountTest(ScotusAPITestCase):
    """The number of queries doesn't grow with the number of results."""

    def count_queries(self, basename: str) -> int:
        """Return the queries a filtered list request runs.

        The filter keeps NoFilterCacheListMixin from serving a cached
        response.
        """
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(self.list_path(basename), {"id__gt": 0})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        return len(ctx.captured_queries)

    def test_queries_are_flat(
        self, mock_logging_prefix: mock.MagicMock
    ) -> None:
        """Does adding rows add no queries?"""
        # Warm up process-level caches that other tests may have cleared,
        # so the first measurement doesn't count one-time lookups.
        for name in BASENAMES:
            self.count_queries(name)
        before = {name: self.count_queries(name) for name in BASENAMES}
        for _ in range(3):
            ScotusDocketMetadataFactory(docket=DocketFactory(court=self.court))
        for name in BASENAMES:
            with self.subTest(endpoint=name):
                self.assertEqual(self.count_queries(name), before[name])
