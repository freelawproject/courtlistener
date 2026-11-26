import re
from datetime import date
from http import HTTPStatus
from unittest import mock

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse
from waffle.testutils import override_flag

from cl.api.utils import LoggingMixin
from cl.search.factories import (
    CaseTransferFactory,
    CourtFactory,
    DocketFactory,
)
from cl.search.models import CaseTransfer, Court
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory

BASENAME = "casetransfer"
PREFIX = "case-transfers"

# The keys of a serialized case transfer.
TRANSFER_KEYS = {
    "resource_uri",
    "id",
    "date_created",
    "date_modified",
    "origin_court",
    "origin_docket_number",
    "origin_docket",
    "destination_court",
    "destination_docket_number",
    "destination_docket",
    "transfer_date",
    "transfer_type",
}


class CaseTransferAPITestCase(TestCase):
    """Shared case transfers for the API tests, with the endpoint's flag on.

    The flag is enabled in setUp, so subclasses that override setUp must
    call super().setUp().

    There are three transfers: one with both dockets in CourtListener, one
    whose destination isn't, and one whose origin isn't.
    """

    def setUp(self) -> None:
        """Turn on the endpoint's flag in a waffle cache of this test's own.

        Tests run in parallel and share the cache, so a common prefix would
        let a test that turns the flag off leak its cached value into others.
        The flag is set here rather than with a decorator because async tests
        can't write it to the database.
        """
        super().setUp()
        self.enterContext(override_settings(WAFFLE_CACHE_PREFIX=self.id()))
        self.enterContext(override_flag("case-transfer-api", active=True))

    @classmethod
    def setUpTestData(cls) -> None:
        """Create the users, courts, dockets and transfers shared by tests."""
        cls.user = UserFactory()
        cls.superuser = UserFactory(is_staff=True, is_superuser=True)
        cls.trial_court = CourtFactory(jurisdiction=Court.STATE_TRIAL)
        cls.appellate_court = CourtFactory(jurisdiction=Court.STATE_APPELLATE)
        cls.appellate_court_2 = CourtFactory(
            jurisdiction=Court.STATE_APPELLATE
        )
        cls.supreme_court = CourtFactory(jurisdiction=Court.STATE_SUPREME)
        cls.appellate_docket = DocketFactory(court=cls.appellate_court)
        cls.appellate_docket_2 = DocketFactory(court=cls.appellate_court)
        cls.supreme_docket = DocketFactory(court=cls.supreme_court)

        cls.appeal = CaseTransferFactory(
            origin_court=cls.appellate_court,
            origin_docket=cls.appellate_docket,
            destination_court=cls.supreme_court,
            destination_docket=cls.supreme_docket,
            transfer_date=date(2024, 3, 1),
            transfer_type=CaseTransfer.APPEAL,
        )
        cls.no_destination_docket = CaseTransferFactory(
            origin_court=cls.appellate_court,
            origin_docket=cls.appellate_docket_2,
            destination_court=cls.appellate_court_2,
            destination_docket=None,
            destination_docket_number="02-25-00001-CV",
            transfer_date=date(2025, 6, 15),
            transfer_type=CaseTransfer.WORKLOAD,
        )
        cls.no_origin_docket = CaseTransferFactory(
            origin_court=cls.trial_court,
            origin_docket=None,
            origin_docket_number="2023-CR-0001",
            destination_court=cls.appellate_court,
            destination_docket=cls.appellate_docket,
            transfer_date=date(2023, 11, 20),
            transfer_type=CaseTransfer.APPEAL,
        )

    @staticmethod
    def list_path() -> str:
        """Return the v4 list URL of the endpoint."""
        return reverse(f"{BASENAME}-list", kwargs={"version": "v4"})

    @staticmethod
    def detail_path(pk: int) -> str:
        """Return the v4 detail URL of a case transfer."""
        return reverse(
            f"{BASENAME}-detail", kwargs={"version": "v4", "pk": pk}
        )


class CaseTransferAPIRoutingTest(CaseTransferAPITestCase):
    """The case transfers endpoint exists in v4 only."""

    async def test_endpoint_is_absent_from_v3(self) -> None:
        """Is the endpoint missing from v3, both as a route and a URL?"""
        with self.assertRaises(NoReverseMatch):
            reverse(f"{BASENAME}-list", kwargs={"version": "v3"})
        await self.async_client.aforce_login(self.user)
        r = await self.async_client.get(
            self.list_path().replace("/v4/", "/v3/")
        )
        self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)


class CaseTransferAPIFlagTest(CaseTransferAPITestCase):
    """The endpoint stays hidden until the case-transfer-api flag is on."""

    def setUp(self) -> None:
        """Log in as a plain user."""
        super().setUp()
        self.client.force_login(self.user)

    def get_root_prefixes(self) -> set[str]:
        """Return the route prefixes the v4 API root lists."""
        r = self.client.get(reverse("api-root", kwargs={"version": "v4"}))
        self.assertEqual(r.status_code, HTTPStatus.OK)
        return set(r.json())

    def test_endpoint_is_hidden_when_flag_is_off(self) -> None:
        """Does the endpoint 404 and drop out of the API root?"""
        with override_flag("case-transfer-api", active=False):
            for path in (self.list_path(), self.detail_path(self.appeal.pk)):
                with self.subTest(path=path):
                    r = self.client.get(path)
                    self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)
            root_prefixes = self.get_root_prefixes()
        self.assertNotIn(PREFIX, root_prefixes)
        # Unflagged routes are still listed.
        self.assertIn("dockets", root_prefixes)

    def test_anonymous_users_get_404_when_flag_is_off(self) -> None:
        """Does the flag hide the endpoint before asking for credentials?"""
        self.client.logout()
        with override_flag("case-transfer-api", active=False):
            r = self.client.get(self.list_path())
        self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)

    def test_endpoint_is_listed_when_flag_is_on(self) -> None:
        """Does the API root list the endpoint once the flag is on?"""
        self.assertIn(PREFIX, self.get_root_prefixes())


class CaseTransferAPIPermissionTest(CaseTransferAPITestCase):
    """The endpoint requires an account and is read only."""

    async def test_anonymous_users_are_rejected(self) -> None:
        """Do anonymous requests get a 401?"""
        r = await self.async_client.get(self.list_path())
        self.assertEqual(r.status_code, HTTPStatus.UNAUTHORIZED)

    async def test_write_methods_are_rejected(self) -> None:
        """Are writes refused, even for superusers?

        Plain users fail the model permission check first (403); superusers
        pass it and then hit the read-only viewset (405).
        """
        count_before = await CaseTransfer.objects.acount()
        requests = [
            ("post", self.list_path()),
            ("put", self.detail_path(self.appeal.pk)),
            ("patch", self.detail_path(self.appeal.pk)),
            ("delete", self.detail_path(self.appeal.pk)),
        ]
        for user, expected in (
            (self.user, HTTPStatus.FORBIDDEN),
            (self.superuser, HTTPStatus.METHOD_NOT_ALLOWED),
        ):
            await self.async_client.aforce_login(user)
            for method, path in requests:
                with self.subTest(user=user.username, method=method):
                    r = await getattr(self.async_client, method)(path)
                    self.assertEqual(r.status_code, expected)
        self.assertEqual(await CaseTransfer.objects.acount(), count_before)


class CaseTransferAPISerializationTest(CaseTransferAPITestCase):
    """The endpoint returns the transfer's fields and links."""

    def setUp(self) -> None:
        """Log in as a plain user."""
        super().setUp()
        self.async_client.force_login(self.user)

    @staticmethod
    def absolute(path: str) -> str:
        """Return the absolute URL the test client's host gives a path."""
        return f"http://testserver{path}"

    def court_url(self, court: Court) -> str:
        """Return the absolute v4 URL of a court."""
        return self.absolute(
            reverse("court-detail", kwargs={"version": "v4", "pk": court.pk})
        )

    def docket_url(self, pk: int) -> str:
        """Return the absolute v4 URL of a docket."""
        return self.absolute(
            reverse("docket-detail", kwargs={"version": "v4", "pk": pk})
        )

    async def test_transfer_with_both_dockets(self) -> None:
        """Does a transfer link both its courts and both its dockets?"""
        r = await self.async_client.get(self.detail_path(self.appeal.pk))
        self.assertEqual(r.status_code, HTTPStatus.OK)
        data = r.json()
        self.assertEqual(set(data), TRANSFER_KEYS)
        self.assertEqual(data["id"], self.appeal.pk)
        self.assertEqual(
            data["origin_court"], self.court_url(self.appellate_court)
        )
        self.assertEqual(
            data["origin_docket"], self.docket_url(self.appellate_docket.pk)
        )
        self.assertEqual(
            data["origin_docket_number"], self.appellate_docket.docket_number
        )
        self.assertEqual(
            data["destination_court"], self.court_url(self.supreme_court)
        )
        self.assertEqual(
            data["destination_docket"], self.docket_url(self.supreme_docket.pk)
        )
        self.assertEqual(
            data["destination_docket_number"],
            self.supreme_docket.docket_number,
        )
        self.assertEqual(data["transfer_date"], "2024-03-01")
        self.assertEqual(data["transfer_type"], CaseTransfer.APPEAL)

    async def test_transfers_with_one_docket_outside_courtlistener(
        self,
    ) -> None:
        """Is the missing docket null while its court and number remain?"""
        cases = [
            (
                self.no_destination_docket,
                "destination",
                self.appellate_court_2,
                "02-25-00001-CV",
            ),
            (
                self.no_origin_docket,
                "origin",
                self.trial_court,
                "2023-CR-0001",
            ),
        ]
        for transfer, side, court, docket_number in cases:
            with self.subTest(side=side):
                r = await self.async_client.get(self.detail_path(transfer.pk))
                self.assertEqual(r.status_code, HTTPStatus.OK)
                data = r.json()
                self.assertIsNone(data[f"{side}_docket"])
                self.assertEqual(data[f"{side}_court"], self.court_url(court))
                self.assertEqual(data[f"{side}_docket_number"], docket_number)


class CaseTransferAPIFilterTest(CaseTransferAPITestCase):
    """The endpoint filters on its own fields and on related ones."""

    async def test_filters(self) -> None:
        """Can transfers be filtered by their fields, courts and dockets?"""
        await self.async_client.aforce_login(self.user)
        cases = [
            ({"id": self.appeal.pk}, 1),
            ({"origin_court": self.appellate_court.pk}, 2),
            ({"destination_court": self.appellate_court.pk}, 1),
            ({"origin_court__jurisdiction": Court.STATE_TRIAL}, 1),
            ({"destination_court__id": self.supreme_court.pk}, 1),
            (
                {
                    "origin_court__id__in": (
                        f"{self.trial_court.pk},{self.supreme_court.pk}"
                    )
                },
                1,
            ),
            ({"origin_docket": self.appellate_docket.pk}, 1),
            ({"destination_docket": self.appellate_docket.pk}, 1),
            ({"destination_docket__id": self.supreme_docket.pk}, 1),
            ({"origin_docket__isnull": "true"}, 1),
            ({"origin_docket__isnull": "false"}, 2),
            ({"destination_docket__isnull": "true"}, 1),
            ({"transfer_type": CaseTransfer.APPEAL}, 2),
            (
                {
                    "transfer_type__in": (
                        f"{CaseTransfer.WORKLOAD},{CaseTransfer.MERGE}"
                    )
                },
                1,
            ),
            ({"transfer_date__gte": "2024-01-01"}, 2),
            ({"transfer_date__year": 2023}, 1),
            ({"transfer_date__range": "2024-01-01,2024-12-31"}, 1),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                r = await self.async_client.get(self.list_path(), params)
                self.assertEqual(r.status_code, HTTPStatus.OK, r.json())
                self.assertEqual(len(r.json()["results"]), expected)


class CaseTransferAPIDynamicFieldsTest(CaseTransferAPITestCase):
    """The fields and omit params trim the response."""

    async def test_fields_and_omit(self) -> None:
        """Do fields and omit return only the requested keys?"""
        await self.async_client.aforce_login(self.user)
        cases = [
            ({"fields": "id,transfer_type"}, {"id", "transfer_type"}),
            (
                {"omit": "origin_docket,destination_docket"},
                TRANSFER_KEYS - {"origin_docket", "destination_docket"},
            ),
        ]
        for params, expected_keys in cases:
            with self.subTest(params=params):
                r = await self.async_client.get(
                    self.detail_path(self.appeal.pk), params
                )
                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertEqual(set(r.json()), expected_keys)


class CaseTransferAPIRelatedFilterTest(CaseTransferAPITestCase):
    """Related filters read only the ids of the objects they look up."""

    def test_related_filter_lookups_read_only_ids(self) -> None:
        """Do related filters look up their object by reading only its id?

        A related filter's exact value is checked by fetching that object,
        and only its pk is used afterwards.
        """
        self.client.force_login(self.user)
        cases = [
            ({"origin_court": self.appellate_court.pk}, "search_court", 2),
            ({"destination_court": self.supreme_court.pk}, "search_court", 1),
            ({"origin_docket": self.appellate_docket.pk}, "search_docket", 1),
            (
                {"destination_docket": self.supreme_docket.pk},
                "search_docket",
                1,
            ),
        ]
        for params, table, expected_count in cases:
            with self.subTest(params=params):
                with CaptureQueriesContext(connection) as ctx:
                    r = self.client.get(self.list_path(), params)
                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertEqual(len(r.json()["results"]), expected_count)

                # Court ids are strings and docket ids are integers.
                lookups = [
                    q["sql"]
                    for q in ctx.captured_queries
                    if re.search(
                        rf""""{table}"\."id" = ('[^']+'|\d+)\)? LIMIT""",
                        q["sql"],
                    )
                ]
                self.assertEqual(len(lookups), 1, lookups)
                selected = set(
                    re.findall(
                        rf'"{table}"\."(\w+)"', lookups[0].split(" FROM ")[0]
                    )
                )
                self.assertEqual(selected, {"id"})

    def test_court_filters_never_read_dockets(self) -> None:
        """Is filtering a transfer's courts by their dockets refused?

        Filtering courts by their dockets would scan every docket in
        CourtListener, so the court filters must not offer that relation.
        """
        self.client.force_login(self.user)
        for side in ("origin", "destination"):
            param = f"{side}_court__dockets__source"
            with self.subTest(param=param):
                with CaptureQueriesContext(connection) as ctx:
                    r = self.client.get(self.list_path(), {param: 0})
                self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
                self.assertEqual(r.json()["unknown_params"], [param])
                for query in ctx.captured_queries:
                    self.assertNotIn('"search_docket"', query["sql"])


# The usage stats write milestone events when their request counters reach
# certain values. Those counters live in Redis and other tests reset them, so
# the events are turned off to keep them from adding queries at random.
@mock.patch.object(LoggingMixin, "_handle_events")
@mock.patch(
    "cl.api.utils.get_logging_prefix",
    return_value="api:test_counts",
)
class CaseTransferAPIQueryCountTest(CaseTransferAPITestCase):
    """Listing transfers runs a fixed number of queries and no joins."""

    def capture_list_queries(self) -> list[str]:
        """Return the SQL of the queries a filtered list request runs.

        The filter keeps NoFilterCacheListMixin from serving a cached
        response.
        """
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(self.list_path(), {"id__gt": 0})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        return [q["sql"] for q in ctx.captured_queries]

    def test_queries_are_flat_and_read_no_courts_or_dockets(
        self,
        mock_logging_prefix: mock.MagicMock,
        mock_handle_events: mock.MagicMock,
    ) -> None:
        """Does adding transfers add no queries, and are no links fetched?

        The court and docket links are built from the transfer's own
        columns, so neither table should be read at all.
        """
        # Warm up process-level caches that other tests may have cleared,
        # so the first measurement doesn't count one-time lookups.
        self.capture_list_queries()
        before = len(self.capture_list_queries())
        for _ in range(3):
            # Each transfer gets its own courts and dockets, so fetching
            # them per row would show up as extra queries.
            CaseTransferFactory()
        queries = self.capture_list_queries()
        self.assertEqual(len(queries), before)
        for sql in queries:
            with self.subTest(sql=sql):
                self.assertNotIn('"search_court"', sql)
                self.assertNotIn('"search_docket"', sql)
