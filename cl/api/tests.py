import json
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any, Dict
from unittest import mock
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.humanize.templatetags.humanize import intcomma, ordinal
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.test import override_settings
from django.test.client import AsyncClient, AsyncRequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.timezone import now
from rest_framework.exceptions import NotFound
from rest_framework.pagination import Cursor, CursorPagination
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from cl.alerts.api_views import DocketAlertViewSet, SearchAlertViewSet
from cl.api.api_permissions import V3APIPermission
from cl.api.factories import WebhookEventFactory, WebhookFactory
from cl.api.models import WEBHOOK_EVENT_STATUS, WebhookEvent, WebhookEventType
from cl.api.pagination import VersionBasedPagination
from cl.api.utils import LoggingMixin, get_logging_prefix, invert_user_logs
from cl.api.views import build_chart_data, coverage_data, make_court_variable
from cl.api.webhooks import send_webhook_event
from cl.audio.api_views import AudioViewSet
from cl.audio.factories import AudioFactory
from cl.disclosures.api_views import (
    AgreementViewSet,
    DebtViewSet,
    FinancialDisclosureViewSet,
    GiftViewSet,
    InvestmentViewSet,
    NonInvestmentIncomeViewSet,
    PositionViewSet,
    ReimbursementViewSet,
    SpouseIncomeViewSet,
)
from cl.favorites.api_views import DocketTagViewSet, UserTagViewSet
from cl.lib.redis_utils import get_redis_interface
from cl.lib.test_helpers import AudioTestCase, SimpleUserDataMixin
from cl.people_db.api_views import (
    ABARatingViewSet,
    AttorneyViewSet,
    EducationViewSet,
    PartyViewSet,
    PersonDisclosureViewSet,
    PersonViewSet,
    PoliticalAffiliationViewSet,
    PositionViewSet,
    RetentionEventViewSet,
    SchoolViewSet,
    SourceViewSet,
)
from cl.people_db.factories import (
    AttorneyFactory,
    AttorneyOrganizationFactory,
    PartyFactory,
    PartyTypeFactory,
    RoleFactory,
)
from cl.people_db.models import Attorney
from cl.recap.factories import ProcessingQueueFactory
from cl.recap.views import (
    EmailProcessingQueueViewSet,
    FjcIntegratedDatabaseViewSet,
    PacerDocIdLookupViewSet,
    PacerFetchRequestViewSet,
    PacerProcessingQueueViewSet,
)
from cl.search.api_views import (
    CourtViewSet,
    DocketEntryViewSet,
    DocketViewSet,
    OpinionClusterViewSet,
    OpinionsCitedViewSet,
    OpinionViewSet,
    OriginatingCourtInformationViewSet,
    RECAPDocumentViewSet,
    TagViewSet,
)
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterFactoryWithChildrenAndParents,
)
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    SOURCES,
    Court,
    Docket,
    Opinion,
)
from cl.stats.models import Event
from cl.tests.cases import (
    ESIndexTestCase,
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
)
from cl.tests.utils import MockResponse, make_client
from cl.users.factories import UserFactory, UserProfileWithParentsFactory
from cl.users.models import UserProfile
from cl.visualizations.api_views import JSONViewSet, VisualizationViewSet


class BasicAPIPageTest(ESIndexTestCase, TestCase):
    """Test the basic views"""

    fixtures = [
        "judge_judy.json",
        "test_court.json",
        "test_objects_search.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.OpinionCluster")

    def setUp(self) -> None:
        self.async_client = AsyncClient()

    async def test_api_root(self) -> None:
        r = await self.async_client.get(
            reverse("api-root", kwargs={"version": "v4"}),
            HTTP_ACCEPT="text/html",
        )
        self.assertEqual(r.status_code, 200)

    async def test_api_index(self) -> None:
        r = await self.async_client.get(reverse("api_index"))
        self.assertEqual(r.status_code, 200)

    async def test_options_request(self) -> None:
        r = await self.async_client.options(reverse("court_index"))
        self.assertEqual(r.status_code, 200)

    async def test_court_index(self) -> None:
        r = await self.async_client.get(reverse("court_index"))
        self.assertEqual(r.status_code, 200)

    async def test_rest_docs(self) -> None:
        r = await self.async_client.get(reverse("rest_docs"))
        self.assertEqual(r.status_code, 200)

    async def test_rest_change_log(self) -> None:
        r = await self.async_client.get(reverse("rest_change_log"))
        self.assertEqual(r.status_code, 200)

    async def test_webhook_docs(self) -> None:
        r = await self.async_client.get(reverse("webhooks_docs"))
        self.assertEqual(r.status_code, 200)

    async def test_webhooks_getting_started(self) -> None:
        r = await self.async_client.get(reverse("webhooks_getting_started"))
        self.assertEqual(r.status_code, 200)

    async def test_bulk_data_index(self) -> None:
        r = await self.async_client.get(reverse("bulk_data_index"))
        self.assertEqual(r.status_code, 200)

    async def test_coverage_api(self) -> None:
        r = await self.async_client.get(
            reverse("coverage_data", kwargs={"version": 4, "court": "ca1"})
        )
        self.assertEqual(r.status_code, 200)

    async def test_coverage_api_via_url(self) -> None:
        r = await self.async_client.get("/api/rest/v4/coverage/ca1/")
        self.assertEqual(r.status_code, 200)

    async def test_api_info_page_displays_latest_rest_docs_by_default(
        self,
    ) -> None:
        response = await self.async_client.get(reverse("rest_docs"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "rest-docs-vlatest.html")

    async def test_api_info_page_can_display_different_versions_of_rest_docs(
        self,
    ) -> None:
        for version in ["v1", "v2", "v3"]:
            response = await self.async_client.get(
                reverse("rest_docs", kwargs={"version": version})
            )
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, f"rest-docs-{version}.html")
            version_to_compare = version.upper() if version != "v3" else "v3"
            header = f"REST API &ndash; {version_to_compare}"
            self.assertContains(response, header)


class CoverageTests(ESIndexTestCase, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.OpinionCluster")
        cls.court_scotus = CourtFactory(id="scotus", jurisdiction="F")
        cls.court_cand = CourtFactory(id="cand", jurisdiction="FD")

        cls.c_scotus_1 = OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Lorem.",
            docket=DocketFactory(
                court=cls.court_scotus, docket_number="123456"
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            date_filed=date(2000, 8, 15),
        )
        cls.c_scotus_2 = OpinionClusterFactoryWithChildrenAndParents(
            case_name="America vs Bank",
            docket=DocketFactory(
                court=cls.court_scotus, docket_number="34-2535"
            ),
            precedential_status=PRECEDENTIAL_STATUS.ERRATA,
            date_filed=date(2024, 6, 15),
        )
        cls.c_cand_1 = OpinionClusterFactoryWithChildrenAndParents(
            case_name="Johnson v. National",
            docket=DocketFactory(
                court=cls.court_cand, docket_number="36-2000"
            ),
            precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
            date_filed=date(1999, 7, 15),
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    async def test_coverage_data_view_provides_court_data(self) -> None:
        response = await coverage_data(HttpRequest(), "v4", "ca1")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        self.assertContains(response, "annual_counts")
        self.assertContains(response, "total")

    async def test_coverage_data_all_courts(self) -> None:
        r = await self.async_client.get(
            reverse("coverage_data", kwargs={"version": "4", "court": "all"})
        )
        j = json.loads(r.content)
        self.assertTrue(len(j["annual_counts"].keys()) > 0)
        self.assertIn("total", j)

    async def test_coverage_data_specific_court(self) -> None:
        r = await self.async_client.get(
            reverse(
                "coverage_data", kwargs={"version": "4", "court": "scotus"}
            )
        )
        j = json.loads(r.content)
        self.assertEqual(len(j["annual_counts"].keys()), 25)
        self.assertEqual(j["annual_counts"]["2000"], 1)
        self.assertEqual(j["annual_counts"]["2024"], 1)
        self.assertEqual(j["total"], 2)

        # Ensure that coverage can be filtered using a query string.
        r = await self.async_client.get(
            reverse(
                "coverage_data", kwargs={"version": "3", "court": "scotus"}
            ),
            {"q": "America"},
        )
        j = json.loads(r.content)
        self.assertEqual(len(j["annual_counts"].keys()), 1)
        self.assertEqual(j["annual_counts"]["2024"], 1)
        self.assertEqual(j["total"], 1)

    async def test_make_court_variable(self) -> None:
        """Confirm opinions counts per court are properly returned."""

        r = get_redis_interface("CACHE")
        cache_count = r.keys(":1:court_counts_o")
        if cache_count:
            r.delete(*cache_count)
        courts = await make_court_variable()
        for court in courts:
            if court.pk == self.court_scotus.pk:
                self.assertEqual(2, court.count)
            if court.pk == self.court_cand.pk:
                self.assertEqual(1, court.count)

    async def test_build_chart_data(self) -> None:
        """Confirm build_chart_data method returns the right data."""

        chart_data = await sync_to_async(build_chart_data)(["scotus", "cand"])
        for court_data in chart_data:
            if (
                court_data["group"]
                == self.court_scotus.get_jurisdiction_display()
            ):
                data = court_data["data"][0]
                self.assertEqual(data["id"], self.court_scotus.pk)
                self.assertEqual(data["label"], self.court_scotus.full_name)
                self.assertEqual(data["data"][0]["val"], 2)

                date_1 = datetime.fromisoformat(
                    data["data"][0]["timeRange"][0].replace("Z", "+00:00")
                )
                date_2 = datetime.fromisoformat(
                    data["data"][0]["timeRange"][1].replace("Z", "+00:00")
                )
                self.assertEqual(date_1.date(), self.c_scotus_1.date_filed)
                self.assertEqual(date_2.date(), self.c_scotus_2.date_filed)

            if (
                court_data["group"]
                == self.court_cand.get_jurisdiction_display()
            ):
                data = court_data["data"][0]
                self.assertEqual(data["id"], self.court_cand.pk)
                self.assertEqual(data["label"], self.court_cand.full_name)
                self.assertEqual(data["data"][0]["val"], 1)

                date_1 = datetime.fromisoformat(
                    data["data"][0]["timeRange"][0].replace("Z", "+00:00")
                )
                date_2 = datetime.fromisoformat(
                    data["data"][0]["timeRange"][1].replace("Z", "+00:00")
                )
                self.assertEqual(date_1.date(), self.c_cand_1.date_filed)
                self.assertEqual(date_2.date(), self.c_cand_1.date_filed)


@mock.patch(
    "cl.api.utils.get_logging_prefix",
    return_value="api:test_counts",
)
class ApiQueryCountTests(TransactionTestCase):
    """Check that the number of queries for an API doesn't explode

    I expect these tests to regularly need updating as new features are added
    to the APIs, but in the meantime, they're important checks because of how
    easy it is to explode the APIs. The issue that happens here is that if
    you're not careful, adding a related field to a model will add at least 20
    queries to each API request, one per returned item. This *kills*
    performance.
    """

    fixtures = [
        "test_objects_query_counts.json",
        "attorney_party.json",
    ]

    def clear_query_caches(self):
        """
        Resets all caches that may prevent query execution.
        Needed to ensure deterministic behavior of ``assertNumQueries`` (or
        after external changes to some Django database records).
        """
        self.addCleanup(Site.objects.clear_cache)
        self.addCleanup(ContentType.objects.clear_cache)

    def setUp(self) -> None:
        # Add the permissions to the user.
        up = UserProfileWithParentsFactory.create(
            user__username="recap-user",
            user__password=make_password("password"),
        )
        ps = Permission.objects.filter(codename="has_recap_api_access")
        up.user.user_permissions.add(*ps)
        self.assertTrue(
            self.client.login(username="recap-user", password="password")
        )

        ProcessingQueueFactory.create(court_id="scotus", uploader=up.user)
        AudioFactory.create(docket_id=1)

        r = get_redis_interface("STATS")
        api_prefix = "api:test_counts.count"
        r.set(api_prefix, 101)
        self.clear_query_caches()

    def tearDown(self) -> None:
        UserProfile.objects.all().delete()

    def test_audio_api_query_counts(self, mock_logging_prefix) -> None:
        with self.assertNumQueries(4):
            path = reverse("audio-list", kwargs={"version": "v3"})
            self.client.get(path)

    def test_no_bad_query_on_empty_parameters(
        self, mock_logging_prefix
    ) -> None:
        with CaptureQueriesContext(connection) as ctx:
            # Test issue 2066, ensuring that we ignore empty filters.
            path = reverse("docketentry-list", kwargs={"version": "v3"})
            self.client.get(path, {"docket__id": ""})
            for query in ctx.captured_queries:
                bad_query = 'IN (SELECT U0."id" FROM "search_docket" U0)'
                if bad_query in query["sql"]:
                    self.fail(
                        "DRF made a nasty query we thought we "
                        f"banished: {bad_query=}"
                    )

    def test_search_api_query_counts(self, mock_logging_prefix) -> None:
        with self.assertNumQueries(7):
            path = reverse("docket-list", kwargs={"version": "v3"})
            self.client.get(path)

        with self.assertNumQueries(8):
            path = reverse("docketentry-list", kwargs={"version": "v3"})
            self.client.get(path)

        with self.assertNumQueries(6):
            path = reverse("recapdocument-list", kwargs={"version": "v3"})
            self.client.get(path)

        with self.assertNumQueries(7):
            path = reverse("opinioncluster-list", kwargs={"version": "v3"})
            self.client.get(path)

        with self.assertNumQueries(5):
            path = reverse("opinion-list", kwargs={"version": "v3"})
            self.client.get(path)

    def test_party_endpoint_query_counts(self, mock_logging_prefix) -> None:
        with self.assertNumQueries(9):
            path = reverse("party-list", kwargs={"version": "v3"})
            self.client.get(path)

    def test_attorney_endpoint_query_counts(self, mock_logging_prefix) -> None:
        with self.assertNumQueries(6):
            path = reverse("attorney-list", kwargs={"version": "v3"})
            self.client.get(path)

    def test_recap_api_query_counts(self, mock_logging_prefix) -> None:
        with self.assertNumQueries(3):
            path = reverse("processingqueue-list", kwargs={"version": "v3"})
            self.client.get(path)

        with self.assertNumQueries(5):
            path = reverse("fast-recapdocument-list", kwargs={"version": "v3"})
            self.client.get(path, {"pacer_doc_id": "17711118263"})

    def test_recap_api_required_filter(self, mock_logging_prefix) -> None:
        path = reverse("fast-recapdocument-list", kwargs={"version": "v3"})
        r = self.client.get(path, {"pacer_doc_id": "17711118263"})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        r = self.client.get(path, {"pacer_doc_id__in": "17711118263,asdf"})
        self.assertEqual(r.status_code, HTTPStatus.OK)

    def test_count_on_query_counts(self, mock_logging_prefix) -> None:
        """
        Check that a v4 API request with param `count=on` only performs
        2 queries to the database: one to check the authenticated user,
        and another to select the count.
        """
        with CaptureQueriesContext(connection) as ctx:
            path = reverse("docket-list", kwargs={"version": "v4"})
            params = {"count": "on"}
            self.client.get(path, params)

        self.assertEqual(
            len(ctx.captured_queries),
            2,
            msg=f"{len(ctx.captured_queries)} queries executed, 2 expected",
        )

        executed_queries = [query["sql"] for query in ctx.captured_queries]
        expected_queries = [
            'FROM "auth_user" WHERE "auth_user"."id" =',
            'SELECT COUNT(*) AS "__count"',
        ]
        for executed_query, expected_fragment in zip(
            executed_queries, expected_queries
        ):
            self.assertIn(
                expected_fragment,
                executed_query,
                msg=f"Expected query fragment not found: {expected_fragment}",
            )

    def test_standard_request_no_count_query(
        self, mock_logging_prefix
    ) -> None:
        """
        Check that a v4 API request without param `count=on` doesn't perform
        a count query.
        """
        with CaptureQueriesContext(connection) as ctx:
            path = reverse("docket-list", kwargs={"version": "v4"})
            self.client.get(path)

        executed_queries = [query["sql"] for query in ctx.captured_queries]
        for sql in executed_queries:
            self.assertNotIn(
                'SELECT COUNT(*) AS "__count"',
                sql,
                msg="Unexpected COUNT query found in standard request.",
            )


class ApiEventCreationTestCase(TestCase):
    """Check that events are created properly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory.create()

    def setUp(self) -> None:
        self.r = get_redis_interface("STATS")
        self.flush_stats()
        self.endpoint_name = "audio-list"

    def tearDown(self) -> None:
        self.flush_stats()

    def flush_stats(self) -> None:
        # Flush existing stats (else previous tests cause issues)
        keys = self.r.keys("api:*")
        if keys:
            self.r.delete(*keys)

    async def hit_the_api(self, api_version) -> None:
        path = reverse("audio-list", kwargs={"version": f"{api_version}"})
        request = AsyncRequestFactory().get(path)

        # Create the view and change the milestones to be something we can test
        # (Otherwise, we need to make 1,000 requests in this test)
        view = AudioViewSet.as_view({"get": "list"})
        view.milestones = [1]

        # Set the attributes needed in the absence of middleware
        request.user = self.user
        await sync_to_async(view)(request, **{"version": f"{api_version}"})

    @mock.patch(
        "cl.api.utils.get_logging_prefix",
        return_value="api:Test",
    )
    @mock.patch.object(LoggingMixin, "milestones", new=[1])
    async def test_are_v3_events_created_properly(
        self, mock_logging_prefix
    ) -> None:
        """Are event objects created as v3 API requests are made?"""
        await self.hit_the_api("v3")

        expected_event_count = 2
        self.assertEqual(expected_event_count, await Event.objects.acount())
        event_descriptions = {
            event.description async for event in Event.objects.all()
        }
        expected_descriptions = set()
        expected_descriptions.add("API v3 has logged 1 total requests.")
        expected_descriptions.add(
            f"User '{self.user.username}' has placed their 1st API v3 request."
        )
        self.assertEqual(event_descriptions, expected_descriptions)

    @mock.patch(
        "cl.api.utils.get_logging_prefix",
        return_value="api:Test",
    )
    @mock.patch.object(LoggingMixin, "milestones", new=[1])
    async def test_are_v4_events_created_properly(
        self, mock_logging_prefix
    ) -> None:
        """Are event objects created as V4 API requests are made?"""
        await self.hit_the_api("v4")

        expected_event_count = 2
        self.assertEqual(expected_event_count, await Event.objects.acount())
        event_descriptions = {
            event.description async for event in Event.objects.all()
        }
        expected_descriptions = set()
        expected_descriptions.add("API v4 has logged 1 total requests.")
        expected_descriptions.add(
            f"User '{self.user.username}' has placed their 1st API v4 request."
        )
        self.assertEqual(event_descriptions, expected_descriptions)

    # Set the api prefix so that other tests
    # run in parallel do not affect this one.
    @mock.patch(
        "cl.api.utils.get_logging_prefix",
        side_effect=lambda *args, **kwargs: f"{get_logging_prefix(*args, **kwargs)}-Test",
    )
    async def test_api_logged_correctly(self, mock_logging_prefix) -> None:
        # Global stats
        self.assertEqual(mock_logging_prefix.called, 0)
        await self.hit_the_api("v3")
        self.assertEqual(mock_logging_prefix.called, 1)
        self.assertEqual(int(self.r.get("api:v3-Test.count")), 1)

        # User stats
        self.assertEqual(
            self.r.zscore("api:v3-Test.user.counts", self.user.pk), 1.0
        )

        # IP address
        keys = self.r.keys("api:v3-Test.d:*")
        ip_key = [k for k in keys if k.endswith("ip_map")][0]
        self.assertEqual(self.r.hlen(ip_key), 1)

        # Endpoints
        self.assertEqual(
            self.r.zscore("api:v3-Test.endpoint.counts", self.endpoint_name), 1
        )

        # Timings
        self.assertAlmostEqual(
            int(self.r.get("api:v3-Test.timing")), 10, delta=2000
        )

    @mock.patch(
        "cl.api.utils.get_logging_prefix",
        side_effect=lambda *args, **kwargs: f"{get_logging_prefix(*args, **kwargs)}-Test",
    )
    async def test_api_logged_correctly_v4(self, mock_logging_prefix) -> None:
        # Global stats
        self.assertEqual(mock_logging_prefix.called, 0)
        await self.hit_the_api("v4")

        self.assertEqual(mock_logging_prefix.called, 1)
        self.assertEqual(int(self.r.get("api:v4-Test.count")), 1)

        # User stats
        self.assertEqual(
            self.r.zscore("api:v4-Test.user.counts", self.user.pk), 1.0
        )

        # IP address
        keys = self.r.keys("api:v4-Test.d:*")
        ip_key = [k for k in keys if k.endswith("ip_map")][0]
        self.assertEqual(self.r.hlen(ip_key), 1)

        # Endpoints
        self.assertEqual(
            self.r.zscore("api:v4-Test.endpoint.counts", self.endpoint_name), 1
        )

        # Timings
        self.assertAlmostEqual(
            int(self.r.get("api:v4-Test.timing")), 10, delta=2000
        )


@override_settings(BLOCK_NEW_V3_USERS=True)
@mock.patch(
    "cl.api.utils.get_logging_prefix",
    return_value="api-block-test:v3",
)
class BlockV3APITests(TestCase):
    """Check that V3 API is restricted for anonymous and new users."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_1 = UserFactory()
        cls.user_2 = UserFactory()
        cls.client_1 = make_client(cls.user_1.pk)
        cls.client_2 = make_client(cls.user_2.pk)

        cls.audio_path_v3 = reverse("audio-list", kwargs={"version": "v3"})
        cls.audio_path_v4 = reverse("audio-list", kwargs={"version": "v4"})
        cls.debt_path_v4 = reverse("debt-list", kwargs={"version": "v4"})
        cls.debt_path_v3 = reverse("debt-list", kwargs={"version": "v3"})

    def setUp(self) -> None:
        self.r = get_redis_interface("STATS")
        self.flush_stats()

    def tearDown(self) -> None:
        self.flush_stats()

    def flush_stats(self) -> None:
        keys = self.r.keys("api-block-test:*")
        if keys:
            self.r.delete(*keys)

        v3_user_list = self.r.keys("v3-users-list")
        if v3_user_list:
            self.r.delete(*v3_user_list)

        v3_user_blocked_list = self.r.keys("v3-blocked-users-list")
        if v3_user_blocked_list:
            self.r.delete(*v3_user_blocked_list)

    def create_v3_user_list(self) -> None:
        v3_stats_members = self.r.zrange(
            "api-block-test:v3.user.counts", 0, -1
        )
        if v3_stats_members:
            self.r.sadd("v3-users-list", *v3_stats_members)

    async def test_block_v3_for_new_users(self, mock_api_prefix) -> None:
        """Confirm new v3 API users are blocked"""

        # A new user request is not detected because we only check some
        # requests. In this case, it's not checked.
        with mock.patch.object(
            V3APIPermission, "check_request", return_value=False
        ):
            response = await self.client_1.get(
                self.audio_path_v3, format="json"
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)

        # Now check the request and block the request and user.
        with mock.patch.object(
            V3APIPermission, "check_request", return_value=True
        ):
            response = await self.client_1.get(
                self.audio_path_v3, format="json"
            )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(
            response.json()["detail"],
            "As a new user, you don't have permission to access V3 of the API. Please use V4 instead.",
        )

        # Once the user is caught, they are added to the V3 blocked list, so
        # every consecutive request from the user is blocked.
        response = await self.client_1.get(self.audio_path_v3, format="json")
        self.assertEqual(
            response.status_code,
            HTTPStatus.FORBIDDEN,
            msg="Consecutive request.",
        )
        self.assertEqual(
            response.json()["detail"],
            "As a new user, you don't have permission to access V3 of the API. Please use V4 instead.",
        )

    async def test_allow_v3_for_existing_users(self, mock_api_prefix) -> None:
        """Confirm that existing v3 API users are granted access to use it"""

        # Simulate v3 existing user and create v3 user list.
        self.r.zincrby("api-block-test:v3.user.counts", 1, self.user_2.pk)
        self.create_v3_user_list()
        with mock.patch.object(
            V3APIPermission, "check_request", return_value=True
        ):
            response = await self.client_2.get(
                self.audio_path_v3, format="json"
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    async def test_block_v3_for_anonymous_users(self, mock_api_prefix) -> None:
        """Confirm anonymous v3 API users are blocked"""
        with mock.patch.object(
            V3APIPermission, "check_request", return_value=True
        ):
            response = await self.async_client.get(self.audio_path_v3)
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(
            response.json()["detail"],
            "Anonymous users don't have permission to access V3 of the API. Please use V4 instead.",
        )

    async def test_allow_v4_for_new_users(self, mock_api_prefix) -> None:
        """Confirm new API users are allowed to use V4 of the API"""
        with mock.patch.object(
            V3APIPermission, "check_request", return_value=True
        ):
            response = await self.client_2.get(
                self.audio_path_v4, format="json"
            )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    async def test_allow_v4_for_anonymous_users(self, mock_api_prefix) -> None:
        """Confirm V4 anonymous API users are allowed to use V4 of the API"""
        with mock.patch.object(
            V3APIPermission, "check_request", return_value=True
        ):
            response = await self.async_client.get(self.audio_path_v4)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    async def test_confirm_v4_post_requests_are_not_allowed(
        self, mock_api_prefix
    ) -> None:
        """Confirm V4 users are not allowed to POST requests."""
        response = await self.client_2.post(self.debt_path_v4, {})
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    async def test_confirm_v3_post_requests_are_not_allowed(
        self, mock_api_prefix
    ) -> None:
        """Confirm V3 users are not allowed to POST requests."""
        response = await self.client_2.post(self.debt_path_v3, {})
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    async def test_confirm_anonymous_post_requests_are_not_allowed(
        self, mock_api_prefix
    ) -> None:
        """Confirm anonymous users are not allowed to POST requests."""
        response = await self.async_client.post(self.debt_path_v4, {})
        self.assertEqual(response.status_code, HTTPStatus.UNAUTHORIZED)


class DRFOrderingTests(TestCase):
    """Does ordering work generally and specifically?"""

    fixtures = ["judge_judy.json", "test_objects_search.json"]

    async def test_position_ordering(self):
        path = reverse("position-list", kwargs={"version": "v3"})
        r = await self.async_client.get(path, {"order_by": "date_start"})
        self.assertLess(
            r.data["results"][0]["date_start"],
            r.data["results"][-1]["date_start"],
        )
        r = await self.async_client.get(path, {"order_by": "-date_start"})
        self.assertGreater(
            r.data["results"][0]["date_start"],
            r.data["results"][-1]["date_start"],
        )

    async def test_opinion_ordering_by_id(self):
        path = reverse("opinion-list", kwargs={"version": "v3"})
        r = await self.async_client.get(path, {"order_by": "id"})
        self.assertLess(
            r.data["results"][0]["resource_uri"],
            r.data["results"][-1]["resource_uri"],
        )
        r = await self.async_client.get(path, {"order_by": "-id"})
        self.assertGreater(
            r.data["results"][0]["resource_uri"],
            r.data["results"][-1]["resource_uri"],
        )


class FilteringCountTestCase:
    """Mixin for adding an additional test assertion."""

    # noinspection PyPep8Naming
    async def assertCountInResults(self, expected_count):
        """Do we get the correct number of API results from the endpoint?"""
        print(f"Path and q are: {self.path}, {self.q}")
        r = await self.async_client.get(self.path, self.q)
        self.assertLess(
            r.status_code,
            400,
            msg=f"Status code of {r.status_code} is higher than 400. Here's "
            f"the JSON: \n{r.json()}",
        )
        got = len(r.data["results"])
        try:
            path = r.request.get("path")
            query_string = r.request.get("query_string")
            url = f"{path}?{query_string}"
        except AttributeError:
            url = self.path
        self.assertEqual(
            got,
            expected_count,
            msg=f"Expected {expected_count}, but got {got} in {url}\n\nr.data was: {r.data}",
        )
        return r


class DRFCourtApiFilterTests(TestCase, FilteringCountTestCase):
    @classmethod
    def setUpTestData(cls):
        Court.objects.all().delete()

        cls.parent_court = CourtFactory(
            id="parent1",
            full_name="Parent Court",
            short_name="PC",
            citation_string="PC",
            in_use=True,
            has_opinion_scraper=True,
            has_oral_argument_scraper=False,
            position=1,
            start_date=date(2000, 1, 1),
            end_date=None,
            jurisdiction=Court.FEDERAL_APPELLATE,
            date_modified=datetime(2021, 1, 1, tzinfo=timezone.utc),
        )

        cls.child_court1 = CourtFactory(
            id="child1",
            parent_court=cls.parent_court,
            full_name="Child Court 1",
            short_name="CC1",
            citation_string="CC1",
            in_use=False,
            has_opinion_scraper=False,
            has_oral_argument_scraper=True,
            position=2,
            start_date=date(2010, 6, 15),
            end_date=date(2020, 12, 31),
            jurisdiction=Court.STATE_SUPREME,
            date_modified=datetime(2022, 6, 15, tzinfo=timezone.utc),
        )
        cls.child_court2 = CourtFactory(
            id="child2",
            parent_court=cls.parent_court,
            full_name="Child Court 2",
            short_name="CC2",
            citation_string="CC2",
            in_use=True,
            has_opinion_scraper=False,
            has_oral_argument_scraper=False,
            position=3,
            start_date=date(2015, 5, 20),
            end_date=None,
            jurisdiction=Court.STATE_TRIAL,
            date_modified=datetime(2023, 3, 10, tzinfo=timezone.utc),
        )

        cls.orphan_court = CourtFactory(
            id="orphan",
            full_name="Orphan Court",
            short_name="OC",
            citation_string="OC",
            in_use=True,
            has_opinion_scraper=False,
            has_oral_argument_scraper=False,
            position=4,
            start_date=date(2012, 8, 25),
            end_date=None,
            jurisdiction=Court.FEDERAL_DISTRICT,
            date_modified=datetime(2023, 5, 5, tzinfo=timezone.utc),
        )

    @async_to_sync
    async def setUp(self):
        self.path = reverse("court-list", kwargs={"version": "v4"})
        self.q: Dict[str, Any] = {}

    async def test_parent_court_filter(self):
        """Can we filter courts by parent_court id?"""
        self.q["parent_court"] = "parent1"
        # Should return child1 and child2:
        response = await self.assertCountInResults(2)

        # Verify the returned court IDs
        court_ids = [court["id"] for court in response.data["results"]]
        self.assertEqual(set(court_ids), {"child1", "child2"})

        # Filter for courts with parent_court id='orphan' (none should match)
        self.q = {"parent_court": "orphan"}
        await self.assertCountInResults(0)

    async def test_no_parent_court_filter(self):
        """Do we get all courts when using no filters?"""
        self.q = {}
        await self.assertCountInResults(4)  # Should return all four courts

    async def test_invalid_parent_court_filter(self):
        """Do we handle invalid parent_court values correctly?"""
        self.q["parent_court"] = "nonexistent"
        await self.assertCountInResults(0)

    async def test_id_filter(self):
        """Can we filter courts by id?"""
        self.q["id"] = "child1"
        response = await self.assertCountInResults(1)
        self.assertEqual(response.data["results"][0]["id"], "child1")

    async def test_in_use_filter(self):
        """Can we filter courts by in_use field?"""
        self.q = {"in_use": "true"}
        await self.assertCountInResults(3)  # parent1, child2, orphan
        self.q = {"in_use": "false"}
        await self.assertCountInResults(1)  # child1

    async def test_has_opinion_scraper_filter(self):
        """Can we filter courts by has_opinion_scraper field?"""
        self.q = {"has_opinion_scraper": "true"}
        await self.assertCountInResults(1)  # parent1
        self.q = {"has_opinion_scraper": "false"}
        await self.assertCountInResults(3)  # child1, child2, orphan

    async def test_has_oral_argument_scraper_filter(self):
        """Can we filter courts by has_oral_argument_scraper field?"""
        self.q = {"has_oral_argument_scraper": "true"}
        await self.assertCountInResults(1)  # child1
        self.q = {"has_oral_argument_scraper": "false"}
        await self.assertCountInResults(3)  # parent1, child2, orphan

    async def test_position_filter(self):
        """Can we filter courts by position with integer lookups?"""
        self.q = {"position__gt": "2"}
        await self.assertCountInResults(2)  # child2 (3), orphan (4)
        self.q = {"position__lte": "2"}
        await self.assertCountInResults(2)  # parent1 (1), child1 (2)

    async def test_start_date_filter(self):
        """Can we filter courts by start_date with date lookups?"""
        self.q = {"start_date__year": "2015"}
        await self.assertCountInResults(1)  # child2 (2015-05-20)
        self.q = {"start_date__gte": "2010-01-01"}
        await self.assertCountInResults(3)  # child1, child2, orphan

    async def test_end_date_filter(self):
        """Can we filter courts by end_date with date lookups?"""
        self.q = {"end_date__day": "31"}
        await self.assertCountInResults(1)  # parent1, child2, orphan
        self.q = {"end_date__year": "2024"}
        await self.assertCountInResults(0)

    async def test_short_name_filter(self):
        """Can we filter courts by short_name with text lookups?"""
        self.q = {"short_name__iexact": "Cc1"}
        await self.assertCountInResults(1)  # child1
        self.q = {"short_name__icontains": "cc"}
        await self.assertCountInResults(2)  # child1, child2

    async def test_full_name_filter(self):
        """Can we filter courts by full_name with text lookups?"""
        self.q = {"full_name__istartswith": "Child"}
        await self.assertCountInResults(2)  # child1, child2
        self.q = {"full_name__iendswith": "Court"}
        await self.assertCountInResults(2)  # parent1, orphan

    async def test_citation_string_filter(self):
        """Can we filter courts by citation_string with text lookups?"""
        self.q = {"citation_string": "OC"}
        await self.assertCountInResults(1)  # orphan
        self.q = {"citation_string__icontains": "2"}
        await self.assertCountInResults(1)  # child2

    async def test_jurisdiction_filter(self):
        """Can we filter courts by jurisdiction?"""
        self.q = {
            "jurisdiction": [
                Court.FEDERAL_APPELLATE,
                Court.FEDERAL_DISTRICT,
            ]
        }
        await self.assertCountInResults(2)  # parent1 and orphan

    async def test_combined_filters(self):
        """Can we filter courts with multiple filters applied?"""
        self.q = {
            "in_use": "true",
            "has_opinion_scraper": "false",
            "position__gt": "2",
        }
        await self.assertCountInResults(2)  # child2 and orphan


class DRFJudgeApiFilterTests(
    SimpleUserDataMixin, TestCase, FilteringCountTestCase
):
    """Do the filters work properly?"""

    fixtures = ["judge_judy.json"]

    @async_to_sync
    async def setUp(self) -> None:
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        self.q: Dict[Any, Any] = {}

    async def test_judge_filtering_by_first_name(self) -> None:
        """Can we filter by first name?"""
        self.path = reverse("person-list", kwargs={"version": "v3"})

        # Filtering with good values brings back 1 result.
        self.q = {"name_first__istartswith": "judith"}
        await self.assertCountInResults(1)

        # Filtering with bad values brings back no results.
        self.q = {"name_first__istartswith": "XXX"}
        await self.assertCountInResults(0)

    async def test_judge_filtering_by_date(self) -> None:
        """Do the various date filters work properly?"""
        self.path = reverse("person-list", kwargs={"version": "v3"})

        # Exact match for her birthday
        correct_date = date(1942, 10, 21)
        self.q = {"date_dob": correct_date.isoformat()}
        await self.assertCountInResults(1)

        # People born after the day before her birthday
        before = correct_date - timedelta(days=1)
        self.q = {"date_dob__gt": before.isoformat()}
        await self.assertCountInResults(1)

        # Flip the logic. This should return no results.
        self.q = {"date_dob__lt": before.isoformat()}
        await self.assertCountInResults(0)

    async def test_nested_judge_filtering(self) -> None:
        """Can we filter across various relations?

        Each of these assertions adds another parameter making our final test
        a pretty complex combination.
        """
        self.path = reverse("person-list", kwargs={"version": "v3"})

        # No results for a bad query
        self.q["educations__degree_level"] = "cert"
        await self.assertCountInResults(0)

        # One result for a good query
        self.q["educations__degree_level"] = "jd"
        await self.assertCountInResults(1)

        # Again, no results
        self.q["educations__degree_year"] = 1400
        await self.assertCountInResults(0)

        # But with the correct year...one result
        self.q["educations__degree_year"] = 1965
        await self.assertCountInResults(1)

        # Judy went to "New York Law School"
        self.q["educations__school__name__istartswith"] = "New York Law"
        await self.assertCountInResults(1)

        # Moving on to careers. Bad value, then good.
        self.q["positions__job_title__icontains"] = "XXX"
        await self.assertCountInResults(0)
        self.q["positions__job_title__icontains"] = "lawyer"
        await self.assertCountInResults(1)

        # Moving on to titles...bad value, then good.
        self.q["positions__position_type"] = "act-jud"
        await self.assertCountInResults(0)
        self.q["positions__position_type"] = "prac"
        await self.assertCountInResults(1)

        # Political affiliation filtering...bad, then good.
        self.q["political_affiliations__political_party"] = "r"
        await self.assertCountInResults(0)
        self.q["political_affiliations__political_party"] = "d"
        await self.assertCountInResults(2)

        # Sources
        about_now = "2015-12-17T00:00:00Z"
        self.q["sources__date_modified__gt"] = about_now
        await self.assertCountInResults(0)
        self.q.pop("sources__date_modified__gt")  # Next key doesn't overwrite.
        self.q["sources__date_modified__lt"] = about_now
        await self.assertCountInResults(2)

        # ABA Ratings
        self.q["aba_ratings__rating"] = "q"
        await self.assertCountInResults(0)
        self.q["aba_ratings__rating"] = "nq"
        await self.assertCountInResults(2)

    async def test_education_filtering(self) -> None:
        """Can we filter education objects?"""
        self.path = reverse("education-list", kwargs={"version": "v3"})

        # Filter by degree
        self.q["degree_level"] = "cert"
        await self.assertCountInResults(0)
        self.q["degree_level"] = "jd"
        await self.assertCountInResults(1)

        # Filter by degree's related field, School
        self.q["school__name__istartswith"] = "XXX"
        await self.assertCountInResults(0)
        self.q["school__name__istartswith"] = "New York"
        await self.assertCountInResults(1)

    async def test_title_filtering(self) -> None:
        """Can Judge Titles be filtered?"""
        self.path = reverse("position-list", kwargs={"version": "v3"})

        # Filter by title_name
        self.q["position_type"] = "act-jud"
        await self.assertCountInResults(0)
        self.q["position_type"] = "c-jud"
        await self.assertCountInResults(1)

    async def test_reverse_filtering(self) -> None:
        """Can we filter Source objects by judge name?"""
        # I want any source notes about judge judy.
        self.path = reverse("source-list", kwargs={"version": "v3"})
        self.q = {"person": 2}
        await self.assertCountInResults(1)

    async def test_position_filters(self) -> None:
        """Can we filter on positions"""
        self.path = reverse("position-list", kwargs={"version": "v3"})

        # I want positions to do with judge #2 (Judy)
        self.q["person"] = 2
        await self.assertCountInResults(2)

        # Retention events
        self.q["retention_events__retention_type"] = "reapp_gov"
        await self.assertCountInResults(1)

        # Appointer was Bill, id of 1
        self.q["appointer"] = 1
        await self.assertCountInResults(1)
        self.q["appointer"] = 3
        await self.assertCountInResults(0)

    async def test_racial_filters(self) -> None:
        """Can we filter by race?"""
        self.path = reverse("person-list", kwargs={"version": "v3"})
        self.q = {"race": "w"}
        await self.assertCountInResults(2)

        # Do an OR. This returns judges that are either black or white (not
        # that it matters, MJ)
        self.q["race"] = ["w", "b"]
        await self.assertCountInResults(3)

    async def test_circular_relationships(self) -> None:
        """Do filters configured using strings instead of classes work?"""
        self.path = reverse("education-list", kwargs={"version": "v3"})

        # Traverse person, position
        self.q["person__positions__job_title__icontains"] = "xxx"
        await self.assertCountInResults(0)
        self.q["person__positions__job_title__icontains"] = "lawyer"
        await self.assertCountInResults(2)

        # Just traverse to the judge table
        self.q["person__name_first"] = "Judy"  # Nope.
        await self.assertCountInResults(0)
        self.q["person__name_first"] = "Judith"  # Yep.
        await self.assertCountInResults(2)

    async def test_exclusion_filters(self) -> None:
        """Can we exclude using !'s?"""
        self.path = reverse("position-list", kwargs={"version": "v3"})

        # I want positions to do with any judge other than judge #1
        # Note the exclamation mark. In a URL this would look like
        # "?judge!=1". Fun stuff.
        self.q["person!"] = 2
        await self.assertCountInResults(1)  # Bill


class DRFRecapApiFilterTests(TestCase, FilteringCountTestCase):
    fixtures = ["recap_docs.json"]

    @classmethod
    def setUpTestData(cls) -> None:
        # Add the permissions to the user.
        up = UserProfileWithParentsFactory.create(
            user__username="recap-user",
            user__password=make_password("password"),
        )
        ps = Permission.objects.filter(codename="has_recap_api_access")
        up.user.user_permissions.add(*ps)

        cls.docket = Docket.objects.get(pk=1)
        cls.docket_2 = DocketFactory()
        firm = AttorneyOrganizationFactory(
            name="Lawyers LLP", lookup_key="6201in816"
        )
        cls.attorney = AttorneyFactory(
            name="Juneau",
            contact_raw="Juneau\r\nAlaska",
            phone="555-555-5555",
            fax="555-555-5555",
            email="j@me.com",
            date_created="2017-04-25T23:52:43.497Z",
            date_modified="2017-04-25T23:52:43.497Z",
            organizations=[firm],
            docket=cls.docket,
        )
        cls.attorney_2 = AttorneyFactory(
            organizations=[firm], docket=cls.docket_2
        )
        cls.party = PartyFactory(
            name="Honker",
            extra_info="",
            docket=cls.docket,
            attorneys=[cls.attorney],
            date_created="2017-04-25T23:53:11.745Z",
            date_modified="2017-04-25T23:53:11.745Z",
        )
        PartyTypeFactory.create(
            party=cls.party,
            name="Defendant",
            extra_info="Klaxon",
            docket=cls.docket,
        )

    @async_to_sync
    async def setUp(self) -> None:
        self.assertTrue(
            await self.async_client.alogin(
                username="recap-user", password="password"
            )
        )
        self.q: Dict[Any, Any] = {}

    async def test_docket_entry_to_docket_filters(self) -> None:
        """Do a variety of docket entry filters work?"""
        self.path = reverse("docketentry-list", kwargs={"version": "v3"})

        # Docket filters...
        self.q["docket__id"] = 1
        await self.assertCountInResults(1)
        self.q["docket__id"] = 10000000000
        await self.assertCountInResults(0)
        self.q = {"docket__id!": 100000000}
        await self.assertCountInResults(1)

    async def test_docket_tag_filters(self) -> None:
        """Can we filter dockets by tags?"""
        self.path = reverse("docket-list", kwargs={"version": "v3"})

        self.q = {"docket_entries__recap_documents__tags": 1}
        await self.assertCountInResults(1)
        self.q = {"docket_entries__recap_documents__tags": 2}
        await self.assertCountInResults(0)

    async def test_docket_entry_docket_court_filters(self) -> None:
        self.path = reverse("docketentry-list", kwargs={"version": "v3"})

        # Across docket to court...
        self.q["docket__court__id"] = "ca1"
        await self.assertCountInResults(1)
        self.q["docket__court__id"] = "foo"
        await self.assertCountInResults(0)

    async def test_nested_recap_document_filters(self) -> None:
        self.path = reverse("docketentry-list", kwargs={"version": "v3"})

        self.q["id"] = 1
        await self.assertCountInResults(1)
        self.q = {"recap_documents__id": 1}
        await self.assertCountInResults(1)
        self.q = {"recap_documents__id": 2}
        await self.assertCountInResults(0)

        self.q = {"recap_documents__tags": 1}
        await self.assertCountInResults(1)
        self.q = {"recap_documents__tags": 2}
        await self.assertCountInResults(0)

        # Something wacky...
        self.q = {"recap_documents__docket_entry__docket__id": 1}
        await self.assertCountInResults(1)
        self.q = {"recap_documents__docket_entry__docket__id": 2}
        await self.assertCountInResults(0)

    async def test_recap_document_filters(self) -> None:
        self.path = reverse("recapdocument-list", kwargs={"version": "v3"})

        self.q["id"] = 1
        await self.assertCountInResults(1)
        self.q["id"] = 2
        await self.assertCountInResults(0)

        self.q = {"pacer_doc_id": 17711118263}
        await self.assertCountInResults(1)
        self.q = {"pacer_doc_id": "17711118263-nope"}
        await self.assertCountInResults(0)

        self.q = {"docket_entry__id": 1}
        await self.assertCountInResults(1)
        self.q = {"docket_entry__id": 2}
        await self.assertCountInResults(0)

        self.q = {"tags": 1}
        await self.assertCountInResults(1)
        self.q = {"tags": 2}
        await self.assertCountInResults(0)
        self.q = {"tags__name": "test"}
        await self.assertCountInResults(1)
        self.q = {"tags__name": "test2"}
        await self.assertCountInResults(0)

    async def test_attorney_filters(self) -> None:
        self.path = reverse("attorney-list", kwargs={"version": "v3"})

        self.q["id"] = self.attorney.pk
        await self.assertCountInResults(1)
        self.q["id"] = self.attorney_2.pk
        await self.assertCountInResults(1)

        self.q = {"docket__id": self.docket.pk}
        await self.assertCountInResults(1)
        self.q = {"docket__id": self.docket_2.pk}
        await self.assertCountInResults(0)

        self.q = {"parties_represented__id": self.party.pk}
        await self.assertCountInResults(1)
        self.q = {"parties_represented__id": 9999}
        await self.assertCountInResults(0)
        self.q = {"parties_represented__name__contains": "Honker"}
        await self.assertCountInResults(1)
        self.q = {"parties_represented__name__contains": "Honker-Nope"}
        await self.assertCountInResults(0)

        # Adds extra role to the existing attorney
        docket = await Docket.objects.afirst()
        attorney = await Attorney.objects.afirst()
        party = await sync_to_async(PartyFactory)(
            docket=self.docket_2,
            attorneys=[attorney],
        )
        await sync_to_async(PartyTypeFactory.create)(
            party=party,
            docket=self.docket_2,
        )
        self.q = {"docket__date_created__range": "2017-04-14,2017-04-15"}
        await self.assertCountInResults(1)
        self.q = {"docket__date_created__range": "2017-04-15,2017-04-16"}
        await self.assertCountInResults(0)

        # Initial request: Fetch all related records
        self.q = {"docket__id": self.docket.pk}
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify record has expected number of parties
        self.assertEqual(
            len(results[0]["parties_represented"]),
            2,
            msg=f"Expected 2, but got {len(results[0]['parties_represented'])}.\n\nr.data was: {r.data}",
        )

        # Fetch attorney records for docket (repeat request with "filter_nested_results")
        self.q = {"docket__id": self.docket.pk, "filter_nested_results": True}
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify top-level record has single party (due to filter)
        self.assertEqual(
            len(results[0]["parties_represented"]),
            1,
            msg=f"Expected 1, but got {len(results[0]['parties_represented'])}.\n\nr.data was: {r.data}",
        )
        # Verify expected party is present in the parties_represented list
        self.assertIn(
            str(self.party.pk), results[0]["parties_represented"][0]["party"]
        )

        # Request using parties_represented lookup: Fetch all related records
        self.q = {"parties_represented__docket__id": self.docket_2.pk}
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify record has expected number of parties
        self.assertEqual(
            len(results[0]["parties_represented"]),
            2,
            msg=f"Expected 2, but got {len(results[0]['parties_represented'])}.\n\nr.data was: {r.data}",
        )

        # Fetch attorney records for parties associated with docket_2 (repeat with "filter_nested_results")
        self.q = {
            "parties_represented__docket__id": self.docket_2.pk,
            "filter_nested_results": True,
        }
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify record has expected number of parties
        self.assertEqual(
            len(results[0]["parties_represented"]),
            1,
            msg=f"Expected 1, but got {len(results[0]['parties_represented'])}.\n\nr.data was: {r.data}",
        )
        # Verify expected party is present in the parties_represented list
        self.assertIn(
            str(party.pk), results[0]["parties_represented"][0]["party"]
        )

    async def test_party_filters(self) -> None:
        self.path = reverse("party-list", kwargs={"version": "v3"})

        self.q["id"] = self.party.pk
        await self.assertCountInResults(1)
        self.q["id"] = 999_999
        await self.assertCountInResults(0)

        # This represents dockets that the party was a part of.
        self.q = {"docket__id": self.docket.id}
        await self.assertCountInResults(1)
        self.q = {"docket__id": self.docket_2.id}
        await self.assertCountInResults(0)

        # Contrasted with this, which joins based on their attorney.
        self.q = {"attorney__docket__id": self.docket.pk}
        await self.assertCountInResults(1)
        self.q = {"attorney__docket__id": self.docket_2.pk}
        await self.assertCountInResults(0)

        self.q = {"name": "Honker"}
        await self.assertCountInResults(1)
        self.q = {"name__icontains": "Honk"}
        await self.assertCountInResults(1)

        self.q = {"name": "Cardinal Bonds"}
        await self.assertCountInResults(0)

        self.q = {"attorney__name__icontains": "Juneau"}
        await self.assertCountInResults(1)
        self.q = {"attorney__name__icontains": "Juno"}
        await self.assertCountInResults(0)

        # Add another attorney to the party record but linked to another docket
        await sync_to_async(RoleFactory.create)(
            party=self.party, docket=self.docket_2, attorney=self.attorney_2
        )

        # Fetch all party records for docket
        self.q = {"docket__id": self.docket.pk}
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify record has expected number of attorneys
        self.assertEqual(
            len(results[0]["attorneys"]),
            2,
            msg=f"Expected 2, but got {len(results[0]['attorneys'])}.\n\nr.data was: {r.data}",
        )

        # Fetch top-level record for docket (repeat with "filter_nested_results")
        self.q = {"docket__id": self.docket.pk, "filter_nested_results": True}
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify the record has only one attorney (due to filter)
        self.assertEqual(
            len(results[0]["attorneys"]),
            1,
            msg=f"Expected 1, but got {len(results[0]['attorneys'])}.\n\nr.data was: {r.data}",
        )
        # Check if retrieved attorney matches expected record
        self.assertEqual(
            results[0]["attorneys"][0]["attorney_id"], self.attorney.pk
        )

        # Add another party type to the party record but linked to a different docket
        await sync_to_async(PartyTypeFactory.create)(
            party=self.party, docket=self.docket_2
        )

        # Fetch all party records for docket
        self.q = {"docket__id": self.docket.pk}
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify record has expected number of attorneys
        self.assertEqual(
            len(results[0]["attorneys"]),
            2,
            msg=f"Expected 2, but got {len(results[0]['attorneys'])}.\n\nr.data was: {r.data}",
        )
        # Verify record has expected number of party types
        self.assertEqual(
            len(results[0]["party_types"]),
            2,
            msg=f"Expected 2, but got {len(results[0]['party_types'])}.\n\nr.data was: {r.data}",
        )

        # Fetch top-level record for docket (repeat with "filter_nested_results")
        self.q = {"docket__id": self.docket.pk, "filter_nested_results": True}
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify the record has only one attorney and one party type (due to filter)
        self.assertEqual(
            len(results[0]["attorneys"]),
            1,
            msg=f"Expected 1, but got {len(results[0]['attorneys'])}.\n\nr.data was: {r.data}",
        )
        self.assertEqual(
            len(results[0]["party_types"]),
            1,
            msg=f"Expected 1, but got {len(results[0]['party_types'])}.\n\nr.data was: {r.data}",
        )
        # Check if retrieved party type matches expected record
        self.assertNotEqual(
            results[0]["party_types"][0]["docket_id"], self.docket_2.pk
        )

        # Fetch party details based on attorney lookup
        self.q = {"attorney__docket__id": self.docket_2.pk}
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Verify record has expected number of attorneys
        self.assertEqual(
            len(results[0]["attorneys"]),
            2,
            msg=f"Expected 2, but got {len(results[0]['attorneys'])}.\n\nr.data was: {r.data}",
        )

        # Apply additional filter to refine previous request
        self.q = {
            "attorney__docket__id": self.docket_2.pk,
            "filter_nested_results": True,
        }
        r = await self.async_client.get(self.path, self.q)
        results = r.data["results"]
        self.assertEqual(
            len(results),
            1,
            msg=f"Expected 1, but got {len(results)}.\n\nr.data was: {r.data}",
        )
        # Ensure only attorney_2 is associated with the filtered party
        self.assertEqual(
            len(results[0]["attorneys"]),
            1,
            msg=f"Expected 1, but got {len(results[0]['attorneys'])}.\n\nr.data was: {r.data}",
        )
        self.assertEqual(
            results[0]["attorneys"][0]["attorney_id"], self.attorney_2.pk
        )


class DRFSearchAppAndAudioAppApiFilterTest(
    TestCase, AudioTestCase, FilteringCountTestCase
):
    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
    ]

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        UserProfileWithParentsFactory.create(
            user__username="recap-user",
            user__password=make_password("password"),
        )

    @async_to_sync
    async def setUp(self) -> None:
        self.assertTrue(
            await self.async_client.alogin(
                username="recap-user", password="password"
            )
        )
        self.q: Dict[Any, Any] = {}

    async def test_cluster_filters(self) -> None:
        """Do a variety of cluster filters work?"""
        self.path = reverse("opinioncluster-list", kwargs={"version": "v3"})

        # Related filters
        self.q["panel__id"] = 2
        await self.assertCountInResults(1)
        self.q["non_participating_judges!"] = 1  # Exclusion filter.
        await self.assertCountInResults(1)
        self.q["sub_opinions__author"] = 2
        await self.assertCountInResults(4)

        # Citation filters
        self.q = {
            "citations__volume": 56,
            "citations__reporter": "F.2d",
            "citations__page": "9",
        }
        await self.assertCountInResults(1)

        # Integer lookups
        self.q = {"scdb_votes_majority__gt": 10}
        await self.assertCountInResults(0)
        self.q["scdb_votes_majority__gt"] = 1
        await self.assertCountInResults(1)

    async def test_opinion_filter(self) -> None:
        """Do a variety of opinion filters work?"""
        self.path = reverse("opinion-list", kwargs={"version": "v3"})

        # Simple filters
        self.q["sha1"] = "asdfasdfasdfasdfasdfasddf-nope"
        await self.assertCountInResults(0)
        self.q["sha1"] = "asdfasdfasdfasdfasdfasddf"
        await self.assertCountInResults(6)

        # Boolean filter
        self.q["per_curiam"] = False
        await self.assertCountInResults(6)

        # Related filters
        self.q["cluster__panel"] = 1
        await self.assertCountInResults(0)
        self.q["cluster__panel"] = 2
        await self.assertCountInResults(4)

        self.q = {"author__name_first__istartswith": "Nope"}
        await self.assertCountInResults(0)
        self.q["author__name_first__istartswith"] = "jud"
        await self.assertCountInResults(6)

        self.q = {"joined_by__name_first__istartswith": "Nope"}
        await self.assertCountInResults(0)
        self.q["joined_by__name_first__istartswith"] = "jud"
        await self.assertCountInResults(1)

        types = [Opinion.COMBINED]
        self.q = {"type": types}
        await self.assertCountInResults(5)
        types.append(Opinion.LEAD)
        await self.assertCountInResults(6)

    async def test_docket_filters(self) -> None:
        """Do a variety of docket filters work?"""
        self.path = reverse("docket-list", kwargs={"version": "v3"})

        # Simple filter
        self.q["docket_number"] = "14-1165-nope"
        await self.assertCountInResults(0)
        self.q["docket_number"] = "docket number 1 005"
        await self.assertCountInResults(1)

        # Related filters
        self.q["court"] = "test"
        await self.assertCountInResults(1)

        self.q["clusters__panel__name_first__istartswith"] = "jud-nope"
        await self.assertCountInResults(0)
        self.q["clusters__panel__name_first__istartswith"] = "jud"
        await self.assertCountInResults(1)

        self.q["audio_files__sha1"] = (
            "de8cff186eb263dc06bdc5340860eb6809f898d3-nope"
        )
        await self.assertCountInResults(0)
        self.q["audio_files__sha1"] = (
            "de8cff186eb263dc06bdc5340860eb6809f898d3"
        )
        await self.assertCountInResults(1)

    async def test_audio_filters(self) -> None:
        self.path = reverse("audio-list", kwargs={"version": "v3"})

        # Simple filter
        self.q["sha1"] = "de8cff186eb263dc06bdc5340860eb6809f898d3-nope"
        await self.assertCountInResults(0)
        self.q["sha1"] = "de8cff186eb263dc06bdc5340860eb6809f898d3"
        await self.assertCountInResults(1)

        # Related filter
        self.q["docket__court"] = "test"
        await self.assertCountInResults(1)

        # Multiple choice filter

        sources = [SOURCES.COURT_WEBSITE]
        self.q = {"source": sources}
        await self.assertCountInResults(2)
        sources.append(SOURCES.COURT_M_RESOURCE)
        await self.assertCountInResults(3)

    async def test_opinion_cited_filters(self) -> None:
        """Do the filters on the opinions_cited work?"""
        self.path = reverse("opinionscited-list", kwargs={"version": "v3"})

        # Simple related filter
        self.q["citing_opinion__sha1"] = "asdf-nope"
        await self.assertCountInResults(0)
        self.q["citing_opinion__sha1"] = "asdfasdfasdfasdfasdfasddf"
        await self.assertCountInResults(4)

        # Fancy filter: Citing Opinions written by judges with first name
        # istartingwith "jud"
        self.q["citing_opinion__author__name_first__istartswith"] = "jud-nope"
        await self.assertCountInResults(0)
        self.q["citing_opinion__author__name_first__istartswith"] = "jud"
        await self.assertCountInResults(4)


class DRFFieldSelectionTest(SimpleUserDataMixin, TestCase):
    """Test selecting only certain fields"""

    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
    ]

    async def test_only_some_fields_returned(self) -> None:
        """Can we return only some of the fields?"""

        # First check the Judge endpoint, one of our more complicated ones.
        path = reverse("person-list", kwargs={"version": "v3"})
        fields_to_return = ["educations", "date_modified", "slug"]
        q = {"fields": ",".join(fields_to_return)}
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        r = await self.async_client.get(path, q)
        self.assertEqual(
            len(r.data["results"][0].keys()), len(fields_to_return)
        )

        # One more check for good measure.
        path = reverse("opinioncluster-list", kwargs={"version": "v3"})
        fields_to_return = ["per_curiam", "slug"]
        r = await self.async_client.get(path, q)
        self.assertEqual(
            len(r.data["results"][0].keys()), len(fields_to_return)
        )


class ExamplePagination(VersionBasedPagination):
    page_size = 5
    max_pagination_depth = 10


class V3DRFPaginationTest(SimpleTestCase):
    # Liberally borrows from drf.tests.test_pagination.py

    def setUp(self) -> None:
        self.pagination = ExamplePagination()
        self.queryset = range(1, 101)

    def paginate_queryset(self, request: Request):
        return list(self.pagination.paginate_queryset(self.queryset, request))

    def test_page_one(self) -> None:
        request = Request(APIRequestFactory().get("/"))
        request.version = "v3"
        queryset = self.paginate_queryset(request)
        self.assertEqual(queryset, [1, 2, 3, 4, 5])

    def test_page_two(self) -> None:
        request = Request(APIRequestFactory().get("/", {"page": 2}))
        request.version = "v3"
        queryset = self.paginate_queryset(request)
        self.assertEqual(queryset, [6, 7, 8, 9, 10])

    def test_deep_pagination(self) -> None:
        with self.assertRaises(NotFound):
            request = Request(APIRequestFactory().get("/", {"page": 20}))
            request.version = "v3"
            self.paginate_queryset(request)


# Mock handle_database_cursor_pagination helpers
original_handle_database_cursor_pagination = (
    VersionBasedPagination.handle_database_cursor_pagination
)


def handle_database_cursor_pagination_wrapper(*args, **kwargs):
    handle_database_cursor_pagination_wrapper.call_count += 1
    handle_database_cursor_pagination_wrapper.call_args = args
    return original_handle_database_cursor_pagination(*args, **kwargs)


class V4DRFPaginationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_1 = UserProfileWithParentsFactory.create(
            user__username="recap-user",
            user__password=make_password("password"),
        )
        ps = Permission.objects.filter(codename="has_recap_api_access")
        ps_upload = Permission.objects.filter(
            codename="has_recap_upload_access"
        )
        cls.user_1.user.user_permissions.add(*ps)
        cls.user_1.user.user_permissions.add(*ps_upload)
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        for i in range(10):
            DocketFactory(
                court=cls.court,
                source=Docket.HARVARD,
                pacer_case_id=str(i),
            )

    def setUp(self) -> None:
        class SimplePagination(VersionBasedPagination):
            page_size = 5
            max_pagination_depth = 10
            ordering = "-id"

        self.pagination = SimplePagination()
        # Required to use a Model to support CursorPagination
        self.queryset = Docket.objects.all().order_by("-id")

    def paginate_queryset(self, request: Request):
        return list(self.pagination.paginate_queryset(self.queryset, request))

    async def _compare_page_results(self, results, sort_key, start, end):
        page_2_expected = []
        async for pk in (
            Docket.objects.all()
            .order_by(sort_key)[start:end]
            .values_list("pk", flat=True)
        ):
            page_2_expected.append(pk)
        self.assertEqual(
            results,
            list(page_2_expected),
            msg=f"Error comparing {sort_key} results from: {start} to {end} ",
        )

    async def _api_v4_request(self, endpoint, params, method="get"):
        url = reverse(endpoint, kwargs={"version": "v4"})
        api_client = await sync_to_async(make_client)(self.user_1.user.pk)
        if method == "get":
            return await api_client.get(url, params)
        if method == "post":
            return await api_client.post(url, params)

    async def _base_test_for_v4_endpoints(
        self,
        endpoint,
        default_ordering,
        secondary_cursor_key,
        non_cursor_key,
        viewset,
    ):
        """Base test for V4 endpoints for cursor and page number pagination."""

        cursor_paginator = CursorPagination()
        cursor_paginator.base_url = "/"

        def generate_test_cursor(ordering_key: str) -> str | None:
            """Generates a valid cursor for testing according to the ordering
            key type.
            :param ordering_key: The ordering key of the cursor.
            :return: A valid cursor for testing.
            """
            position = 10 if "id" in ordering_key else now()
            cursor = Cursor(offset=1, reverse=False, position=position)  # type: ignore
            encoded_cursor = cursor_paginator.encode_cursor(cursor)
            parsed_url = urlparse(encoded_cursor)
            query_params = parse_qs(parsed_url.query)
            return query_params.get("cursor", [None])[0]

        # Mock handle_database_cursor_pagination
        # Initialize call count and call arguments tracking
        handle_database_cursor_pagination_wrapper.call_count = 0
        handle_database_cursor_pagination_wrapper.call_args = None
        with mock.patch.object(
            VersionBasedPagination,
            "handle_database_cursor_pagination",
            new=handle_database_cursor_pagination_wrapper,
        ) as mock_cursor_pagination:
            cursor_value = generate_test_cursor(default_ordering)
            # Confirm the default sorting key works with cursor pagination
            response = await self._api_v4_request(
                endpoint, {"cursor": cursor_value}
            )
        self.assertEqual(
            response.status_code,
            200,
            msg="Wrong status code primary cursor key.",
        )
        self.assertEqual(
            mock_cursor_pagination.call_count,
            1,
            msg="Wrong number of cursor calls",
        )
        args = mock_cursor_pagination.call_args
        requested_ordering = args[2]
        self.assertEqual(
            requested_ordering, default_ordering, msg="Wrong ordering key"
        )

        # Try a different cursor sorting key.
        cursor_value = generate_test_cursor(secondary_cursor_key)
        params = {"order_by": secondary_cursor_key, "cursor": cursor_value}
        handle_database_cursor_pagination_wrapper.call_count = 0
        handle_database_cursor_pagination_wrapper.call_args = None
        with mock.patch.object(
            VersionBasedPagination,
            "handle_database_cursor_pagination",
            new=handle_database_cursor_pagination_wrapper,
        ) as mock_cursor_pagination:
            response = await self._api_v4_request(endpoint, params)

        self.assertEqual(
            response.status_code,
            200,
            msg="Wrong status code secondary cursor key.",
        )

        # Confirm cursor pagination is also applied in this request for secondary_cursor_key
        self.assertEqual(
            mock_cursor_pagination.call_count,
            1,
            msg="Wrong number of cursor calls for secondary key",
        )
        args = mock_cursor_pagination.call_args
        requested_ordering = args[2]
        self.assertEqual(
            requested_ordering, secondary_cursor_key, msg="Wrong ordering key"
        )

        if non_cursor_key:
            # Try a non-cursor sorting key and avoid deep pagination
            params = {"order_by": non_cursor_key, "page": 20}
            with mock.patch.object(
                viewset, "pagination_class", ExamplePagination
            ):
                response = await self._api_v4_request(endpoint, params)
            self.assertEqual(
                response.status_code,
                404,
                msg="Wrong status code page number pagination.",
            )
            self.assertEqual(
                response.json()["detail"],
                "Invalid page: Deep API pagination is not allowed. Please review API documentation.",
            )

    async def _test_v4_non_cursor_endpoints(
        self,
        endpoint,
        additional_params,
        secondary_non_cursor_key,
        viewset,
    ):
        """Base test for V4 endpoints for cursor and page number pagination."""
        # Mock handle_database_cursor_pagination
        handle_database_cursor_pagination_wrapper.call_count = 0
        handle_database_cursor_pagination_wrapper.call_args = None
        with mock.patch.object(
            VersionBasedPagination,
            "handle_database_cursor_pagination",
            new=handle_database_cursor_pagination_wrapper,
        ) as mock_cursor_pagination:
            # Confirm the default sorting doesn't work with cursor pagination
            response = await self._api_v4_request(endpoint, additional_params)
        self.assertEqual(
            response.status_code,
            200,
            msg="Wrong status code primary cursor key.",
        )
        self.assertEqual(
            mock_cursor_pagination.call_count,
            0,
            msg="Wrong number of cursor calls",
        )

        # Confirm a secondary sorting key doesn't work with cursor pagination
        params = {"order_by": secondary_non_cursor_key}
        params.update(additional_params)
        handle_database_cursor_pagination_wrapper.call_count = 0
        handle_database_cursor_pagination_wrapper.call_args = None
        with mock.patch.object(
            VersionBasedPagination,
            "handle_database_cursor_pagination",
            new=handle_database_cursor_pagination_wrapper,
        ) as mock_cursor_pagination:
            response = await self._api_v4_request(endpoint, params)
        self.assertEqual(
            response.status_code,
            200,
            msg="Wrong status code primary cursor key.",
        )
        self.assertEqual(
            mock_cursor_pagination.call_count,
            0,
            msg="Wrong number of cursor calls",
        )

        # Confirm we can avoid deep pagination
        params.update({"page": 20})
        with mock.patch.object(viewset, "pagination_class", ExamplePagination):
            response = await self._api_v4_request(endpoint, params)
        self.assertEqual(
            response.status_code,
            404,
            msg="Wrong status code page number pagination.",
        )
        self.assertEqual(
            response.json()["detail"],
            "Invalid page: Deep API pagination is not allowed. Please review API documentation.",
        )

    def test_generic_page_one(self) -> None:
        """Confirm the content of a generic V4 page one."""
        request = Request(APIRequestFactory().get("/"))
        request.version = "v4"
        queryset = self.paginate_queryset(request)
        page_1_expected = Docket.objects.all().order_by("-id")[:5]
        self.assertEqual(queryset, list(page_1_expected))

    async def test_next_page_cursor_default_sorting(self) -> None:
        """Confirm cursor pagination is used as default pagination class on
        the default sorting key ID"""

        # Request then first page and compare the results.
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"})
            )
        results = response.json()["results"]
        self.assertEqual(len(results), 5)
        ids = [result["id"] for result in results]
        await self._compare_page_results(ids, "-id", 0, 5)

        # Go to the next page and compare the results.
        next_page_url = response.json()["next"]
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(next_page_url)
        results = response.json()["results"]
        ids = [result["id"] for result in results]
        self.assertEqual(len(results), 5)
        await self._compare_page_results(ids, "-id", 5, 10)

    async def test_next_page_cursor_date_created_sorting(self) -> None:
        """Confirm cursor pagination is used as pagination class when
        sorting by date_created which also supports cursor pagination.
        """

        params = {"order_by": "date_created"}
        # Request then first page and compare the results.
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )
        results = response.json()["results"]
        self.assertEqual(len(results), 5)
        ids = [result["id"] for result in results]
        await self._compare_page_results(ids, "date_created", 0, 5)

        # Go to the next page and compare the results.
        next_page_url = response.json()["next"]
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(next_page_url)
        results = response.json()["results"]
        ids = [result["id"] for result in results]
        self.assertEqual(len(results), 5)
        await self._compare_page_results(ids, "date_created", 5, 10)

        # Inverse sorting:
        params = {"order_by": "-date_created"}
        # Request then first page and compare the results.
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )
        results = response.json()["results"]
        self.assertEqual(len(results), 5)
        ids = [result["id"] for result in results]
        await self._compare_page_results(ids, "-date_created", 0, 5)

        # Go to the next page and compare the results.
        next_page_url = response.json()["next"]
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(next_page_url)
        results = response.json()["results"]
        ids = [result["id"] for result in results]
        self.assertEqual(len(results), 5)
        await self._compare_page_results(ids, "-date_created", 5, 10)

    async def test_next_page_date_filed_sorting(self) -> None:
        """Confirm normal pagination is used as the pagination class when
        sorting by keys other than ID and date_created, which don’t support
        cursor pagination, such as date_filed.
        """

        for i in range(5):
            await sync_to_async(DocketFactory)(
                court=self.court,
                source=Docket.HARVARD,
                pacer_case_id=f"1234{i+1}",
                date_filed=date(2015, 8, i + 1),
            )

        params: dict[str, str | int] = {"order_by": "date_filed"}
        # Request then first page and compare the results. In this sorting key
        # results where date_filed is not None are shown first.
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )
        results = response.json()["results"]
        self.assertEqual(len(results), 5)
        ids = [result["id"] for result in results]
        await self._compare_page_results(ids, "date_filed", 0, 5)

        # Go to the next page and compare the results. The exact order of the
        # results in this page is not checked because it is not guaranteed.
        # Due to None values.
        next_page_url = response.json()["next"]
        self.assertIn("page", next_page_url)
        params.update({"page": 2})
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )
        results = response.json()["results"]
        self.assertEqual(len(results), 5)

        # Inverse order. Here results with None date_filed are shown first.
        # The exact order of the  results is not checked because it is not
        # guaranteed. Due to None values.
        params = {"order_by": "-date_filed"}
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )

        self.assertEqual(response.status_code, 200, msg="Wrong status code")
        results = response.json()["results"]
        self.assertEqual(len(results), 5)
        next_page_url = response.json()["next"]
        self.assertIn("page", next_page_url)

        params.update({"page": 3})
        # Go to the last page. Confirm the results with date_filed are
        # properly ordered.
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        ids = [result["id"] for result in results]
        await self._compare_page_results(ids, "-date_filed", 10, 15)
        self.assertEqual(len(results), 5)

    async def test_ignore_cursor_or_page_params(self) -> None:
        """Confirm that the cursor or page param is ignored on a request that
        belongs to a sorting cursor-only or page-only key."""

        for i in range(5):
            await sync_to_async(DocketFactory)(
                court=self.court,
                source=Docket.HARVARD,
                pacer_case_id=f"1235{i + 1}",
                date_filed=date(2015, 8, i + 1),
            )

        params: dict[str, str | int] = {"order_by": "date_created"}
        # Start requesting the first page of date_created which uses cursor
        # pagination.
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )
        self.assertEqual(response.status_code, 200, msg="Wrong status code")
        results = response.json()["results"]
        self.assertEqual(len(results), 5)

        # Change the sorting key to date_filed which doesn't support cursor
        # pagination and go to the next page.
        next_page_url = response.json()["next"]
        next_page_url = next_page_url.replace(
            "order_by=date_created", "order_by=date_filed"
        )
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(next_page_url)

        # It should return the first page sorting results by date_filed, ignoring
        # the cursor param.
        self.assertEqual(response.status_code, 200, msg="Wrong status code")
        next_page_url = response.json()["next"]
        self.assertIn("page=2", next_page_url)
        results = response.json()["results"]
        self.assertEqual(len(results), 5)
        ids = [result["id"] for result in results]
        await self._compare_page_results(ids, "date_filed", 0, 5)

        # Request then second page sorting by ID, it should use cursor pagination
        # while the page param should be ignored.
        params = {"page": 2}
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )
        results = response.json()["results"]
        self.assertEqual(len(results), 5)
        ids = [result["id"] for result in results]
        await self._compare_page_results(ids, "-id", 0, 5)

    async def test_next_page_invalid_cursor_request(self) -> None:
        """Confirm that an invalid cursor error message is raised if the
        sorting key is changed to an incompatible one from the current cursor.
        """

        # Request the first page sorting by date_created
        params = {"order_by": "date_created"}
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(
                reverse("docket-list", kwargs={"version": "v4"}), params
            )

        self.assertEqual(response.status_code, 200, msg="Wrong status code")
        results = response.json()["results"]
        self.assertEqual(len(results), 5)

        # Change the sorting key to ID and go to the next page.
        # A 404 status code and Invalid cursor message should be raised.
        next_page_url = response.json()["next"]
        next_page_url = next_page_url.replace(
            "order_by=date_created", "order_by=id"
        )
        with mock.patch.object(
            DocketViewSet, "pagination_class", ExamplePagination
        ):
            response = await self.async_client.get(next_page_url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Invalid cursor")

    async def test_alerts_endpoint(self):
        """Test the V4 Alerts endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="alert-list",
            default_ordering="-date_created",
            secondary_cursor_key="date_created",
            non_cursor_key="name",
            viewset=SearchAlertViewSet,
        )

    async def test_docket_entries_endpoint(self):
        """Test the V4 Docket Entries endpoint confirming that their cursor
        and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="docketentry-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="date_filed",
            viewset=DocketEntryViewSet,
        )

    async def test_originatingcourtinformation_endpoint(self):
        """Test the V4 Originating Court Information endpoint confirming that
        their cursor and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="originatingcourtinformation-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="date_filed",
            viewset=OriginatingCourtInformationViewSet,
        )

    async def test_recapdocument_endpoint(self):
        """Test the V4 RECAPDocument endpoint confirming that their cursor
        and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="recapdocument-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="date_upload",
            viewset=RECAPDocumentViewSet,
        )

    async def test_audio_endpoint(self):
        """Test the V4 Audio endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="audio-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="date_blocked",
            viewset=AudioViewSet,
        )

    async def test_opinioncluster_endpoint(self):
        """Test the V4 OpinionCluster endpoint confirming that their cursor
        and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="opinioncluster-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="date_filed",
            viewset=OpinionClusterViewSet,
        )

    async def test_opinion_endpoint(self):
        """Test the V4 Opinion endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="opinion-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key=None,
            viewset=OpinionViewSet,
        )

    async def test_opinions_cited_endpoint(self):
        """Test the V4 OpinionsCited endpoint confirming that their cursor
        and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="opinionscited-list",
            default_ordering="-id",
            secondary_cursor_key="id",
            non_cursor_key="citing_opinion",
            viewset=OpinionsCitedViewSet,
        )

    async def test_tag_endpoint(self):
        """Test the V4 Tag endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="tag-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="name",
            viewset=TagViewSet,
        )

    async def test_people_endpoint(self):
        """Test the V4 People endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="person-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="date_dob",
            viewset=PersonViewSet,
        )

    async def test_disclosuretypeahead_endpoint(self):
        """Test the V4 PersonDisclosure endpoint confirming that their
        cursor and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="disclosuretypeahead-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="name_last",
            viewset=PersonDisclosureViewSet,
        )

    async def test_positions_endpoint(self):
        """Test the V4 Positions endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="position-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="date_elected",
            viewset=PositionViewSet,
        )

    async def test_retention_events_endpoint(self):
        """Test the V4 Retention Events endpoint confirming that their cursor
        and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="retentionevent-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="date_retention",
            viewset=RetentionEventViewSet,
        )

    async def test_educations_endpoint(self):
        """Test the V4 Educations endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="education-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key=None,
            viewset=EducationViewSet,
        )

    async def test_schools_endpoint(self):
        """Test the V4 Schools endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="school-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="name",
            viewset=SchoolViewSet,
        )

    async def test_political_affiliations_endpoint(self):
        """Test the V4 Political Affiliations endpoint confirming that their
        cursor and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="politicalaffiliation-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="date_start",
            viewset=PoliticalAffiliationViewSet,
        )

    async def test_sources_endpoint(self):
        """Test the V4 Sources endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="source-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="date_accessed",
            viewset=SourceViewSet,
        )

    async def test_aba_ratings_endpoint(self):
        """Test the V4 ABA Ratings endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="abarating-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key="year_rated",
            viewset=ABARatingViewSet,
        )

    async def test_party_endpoint(self):
        """Test the V4 Party endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="party-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key=None,
            viewset=PartyViewSet,
        )

    async def test_attorney_endpoint(self):
        """Test the V4 Attorney endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="attorney-list",
            default_ordering="-id",
            secondary_cursor_key="date_created",
            non_cursor_key=None,
            viewset=AttorneyViewSet,
        )

    async def test_processingqueue_endpoint(self):
        """Test the V4 ProcessingQueue endpoint confirming that their cursor
        and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="processingqueue-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=PacerProcessingQueueViewSet,
        )

    async def test_emailprocessingqueue_endpoint(self):
        """Test the V4 EmailProcessingQueue endpoint confirming that their
        cursor and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="emailprocessingqueue-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=EmailProcessingQueueViewSet,
        )

    async def test_pacerfetchqueue_endpoint(self):
        """Test the V4 PacerFetchQueue endpoint confirming that their cursor
        and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="pacerfetchqueue-list",
            default_ordering="-id",
            secondary_cursor_key="date_completed",
            non_cursor_key="",
            viewset=PacerFetchRequestViewSet,
        )

    async def test_fjcintegrateddatabase_endpoint(self):
        """Test the V4 FJCIntegratedDatabase endpoint confirming that their
        cursor and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="fjcintegrateddatabase-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="date_filed",
            viewset=FjcIntegratedDatabaseViewSet,
        )

    async def test_usertag_endpoint(self):
        """Test the V4 User Tag endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="UserTag-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="name",
            viewset=UserTagViewSet,
        )

    async def test_dockettag_endpoint(self):
        """Test the V4 DocketTag endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="DocketTag-list",
            default_ordering="-id",
            secondary_cursor_key="id",
            non_cursor_key="docket",
            viewset=DocketTagViewSet,
        )

    async def test_jsonversion_endpoint(self):
        """Test the V4 JSONVersion endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="jsonversion-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=JSONViewSet,
        )

    async def test_scotusmap_endpoint(self):
        """Test the V4 SCOTUSMap endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="scotusmap-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="user",
            viewset=VisualizationViewSet,
        )

    async def test_agreement_endpoint(self):
        """Test the V4 Agreement endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="agreement-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=AgreementViewSet,
        )

    async def test_debt_endpoint(self):
        """Test the V4 Debt endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="debt-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=DebtViewSet,
        )

    async def test_financialdisclosure_endpoint(self):
        """Test the V4 Financial Disclosure endpoint confirming that their
        cursor and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="financialdisclosure-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=FinancialDisclosureViewSet,
        )

    async def test_gift_endpoint(self):
        """Test the V4 Gift endpoint confirming that their cursor and page
        number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="gift-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=GiftViewSet,
        )

    async def test_investment_endpoint(self):
        """Test the V4 Investment endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="investment-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=InvestmentViewSet,
        )

    async def test_noninvestmentincome_endpoint(self):
        """Test the V4 Non-Investment Income endpoint confirming that their
        cursor and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="noninvestmentincome-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=NonInvestmentIncomeViewSet,
        )

    async def test_disclosureposition_endpoint(self):
        """Test the V4 Disclosure Position endpoint confirming that their
        cursor and page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="disclosureposition-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=PositionViewSet,
        )

    async def test_reimbursement_endpoint(self):
        """Test the V4 Reimbursement endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="reimbursement-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=ReimbursementViewSet,
        )

    async def test_spouseincome_endpoint(self):
        """Test the V4 Spouse Income endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="spouseincome-list",
            default_ordering="-id",
            secondary_cursor_key="date_modified",
            non_cursor_key="",
            viewset=SpouseIncomeViewSet,
        )

    async def test_docket_alert_endpoint(self):
        """Test the V4 DocketAlert endpoint confirming that their cursor and
        page number pagination works properly."""

        await self._base_test_for_v4_endpoints(
            endpoint="docket-alert-list",
            default_ordering="-date_created",
            secondary_cursor_key="date_created",
            non_cursor_key="",
            viewset=DocketAlertViewSet,
        )

    # non-cursor pagination endpoints
    async def test_courts_endpoint(self):
        """Test the V4 Courts endpoint confirming page number pagination works
        properly."""

        await self._test_v4_non_cursor_endpoints(
            endpoint="court-list",
            additional_params={},
            secondary_non_cursor_key="end_date",
            viewset=CourtViewSet,
        )

    async def test_recap_query_endpoint(self):
        """Test the V4 RECAPQuery endpoint confirming page number pagination
        works properly."""

        await self._test_v4_non_cursor_endpoints(
            endpoint="fast-recapdocument-list",
            additional_params={"pacer_doc_id": "1"},
            secondary_non_cursor_key="pacer_doc_id",
            viewset=PacerDocIdLookupViewSet,
        )

    async def test_membership_webhooks_endpoint(self):
        """Test membership-webhooks endpoint works on V4"""
        r = await self._api_v4_request("membership-webhooks-list", {}, "post")
        data = json.loads(r.content)
        self.assertIn("This field is required.", data["eventTrigger"])
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_citation_lookup_endpoint(self):
        """Test CitationLookup endpoint works on V4"""

        r = await self._api_v4_request(
            "citation-lookup-list", {"text": "this is a text"}, "post"
        )
        data = json.loads(r.content)
        # The response should be an empty json object and a success HTTP code.
        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertEqual(len(data), 0)


class DRFRecapPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # Add the permissions to the user.
        up = UserProfileWithParentsFactory.create(
            user__username="recap-user",
            user__password=make_password("password"),
        )
        ps = Permission.objects.filter(codename="has_recap_api_access")
        up.user.user_permissions.add(*ps)

        UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )

        cls.paths = [
            reverse(path, kwargs={"version": "v3"})
            for path in [
                "recapdocument-list",
                "docketentry-list",
                "attorney-list",
                "party-list",
            ]
        ]

    async def test_has_access(self) -> None:
        """Does the RECAP user have access to all of the RECAP endpoints?"""
        self.assertTrue(
            await self.async_client.alogin(
                username="recap-user", password="password"
            )
        )
        for path in self.paths:
            print(f"Access allowed to recap user at: {path}... ", end="")
            r = await self.async_client.get(path)
            self.assertEqual(r.status_code, HTTPStatus.OK)
            print("✓")

    async def test_lacks_access(self) -> None:
        """Does a normal user lack access to the RECPAP endpoints?"""
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        for path in self.paths:
            print(f"Access denied to non-recap user at: {path}... ", end="")
            r = await self.async_client.get(path)
            self.assertEqual(r.status_code, HTTPStatus.FORBIDDEN)
            print("✓")


class WebhooksProxySecurityTest(TestCase):
    """Test Webhook proxy security"""

    @classmethod
    def setUpTestData(cls):
        cls.user_profile = UserProfileWithParentsFactory()
        cls.webhook_https = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://127.0.0.1:3000",
            enabled=True,
        )

        cls.webhook_http = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="http://127.0.0.1:3000",
            enabled=True,
        )
        cls.webhook_0_0_0_0 = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="http://0.0.0.0:5050",
            enabled=True,
        )

    def test_avoid_sending_webhooks_to_internal_ips(self):
        """Can we avoid sending webhooks to internal IPs?"""

        webhook_event = WebhookEventFactory(
            webhook=self.webhook_https,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
        )
        send_webhook_event(webhook_event)
        webhook_event.refresh_from_db()
        self.assertNotEqual(
            webhook_event.response,
            "",
            msg="Empty response from insecure webhook post. Is cl-webhook-sentry up?",
        )
        self.assertIn("IP 127.0.0.1 is blocked", webhook_event.response)
        self.assertEqual(
            webhook_event.status_code,
            HTTPStatus.FORBIDDEN,
        )

        webhook_event_2 = WebhookEventFactory(
            webhook=self.webhook_http,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
        )
        send_webhook_event(webhook_event_2)
        webhook_event_2.refresh_from_db()
        self.assertNotEqual(
            webhook_event.response,
            "",
            msg="Empty response from insecure webhook post. Is cl-webhook-sentry up?",
        )
        self.assertIn("IP 127.0.0.1 is blocked", webhook_event_2.response)
        self.assertEqual(
            webhook_event_2.status_code,
            HTTPStatus.FORBIDDEN,
        )

        webhook_event_3 = WebhookEventFactory(
            webhook=self.webhook_0_0_0_0,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
        )
        send_webhook_event(webhook_event_3)
        webhook_event_3.refresh_from_db()
        self.assertNotEqual(
            webhook_event.response,
            "",
            msg="Empty response from insecure webhook post. Is cl-webhook-sentry up?",
        )
        self.assertIn("IP 0.0.0.0 is blocked", webhook_event_3.response)
        self.assertEqual(
            webhook_event_3.status_code,
            HTTPStatus.FORBIDDEN,
        )


class WebhooksMilestoneEventsTest(TestCase):
    """Test Webhook milestone events tracking"""

    @classmethod
    def setUpTestData(cls):
        cls.user_profile_1 = UserProfileWithParentsFactory()
        cls.user_profile_2 = UserProfileWithParentsFactory()
        cls.webhook_user_1 = WebhookFactory(
            user=cls.user_profile_1.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        cls.webhook_user_2 = WebhookFactory(
            user=cls.user_profile_2.user,
            event_type=WebhookEventType.RECAP_FETCH,
            url="https://example.com/",
            enabled=True,
        )

    def setUp(self) -> None:
        self.r = get_redis_interface("STATS")
        self.flush_stats()

    def tearDown(self) -> None:
        self.flush_stats()

    def flush_stats(self) -> None:
        # Flush existing stats
        keys = self.r.keys("webhook:*")
        if keys:
            self.r.delete(*keys)

    @mock.patch(
        "cl.api.utils.get_webhook_logging_prefix",
        return_value="webhook:test_1",
    )
    async def test_webhook_milestone_events_creation(self, mock_prefix):
        """Are webhook events properly tracked and milestone events created?"""

        webhook_event_1 = await sync_to_async(WebhookEventFactory)(
            webhook=self.webhook_user_1,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
        )
        # Send one webhook event for user_1.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            await sync_to_async(send_webhook_event)(webhook_event_1)

        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(await webhook_events.acount(), 1)
        webhook_events_first = await webhook_events.afirst()
        self.assertEqual(
            webhook_events_first.event_status, WEBHOOK_EVENT_STATUS.SUCCESSFUL
        )

        total_events = Event.objects.filter(user=None).order_by("date_created")
        user_1_events = Event.objects.filter(
            user=self.webhook_user_1.user
        ).order_by("date_created")

        # Confirm one webhook global event and a webhook user event are created
        self.assertEqual(await total_events.acount(), 1)
        self.assertEqual(await user_1_events.acount(), 1)
        global_description = (
            f"User '{self.webhook_user_1.user.username}' "
            f"has placed their {intcomma(ordinal(1))} webhook event."
        )
        user_1_events_first = await user_1_events.afirst()
        self.assertEqual(user_1_events_first.description, global_description)
        user_description = "Webhooks have logged 1 total successful events."
        total_events_first = await total_events.afirst()
        self.assertEqual(total_events_first.description, user_description)

        # Send 4 more new webhook events for user_1:
        for _ in range(4):
            webhook_event = await sync_to_async(WebhookEventFactory)(
                webhook=self.webhook_user_1,
                content="{'message': 'ok_1'}",
                event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
            )
            with mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ):
                await sync_to_async(send_webhook_event)(webhook_event)

        self.assertEqual(await webhook_events.acount(), 5)

        # Confirm new global and user webhook events are created.
        self.assertEqual(await total_events.acount(), 2)
        self.assertEqual(await user_1_events.acount(), 2)
        # Confirm the new events counter were properly increased.
        user_description = (
            f"User '{self.webhook_user_1.user.username}' "
            f"has placed their {intcomma(ordinal(5))} webhook event."
        )
        user_1_events_last = await user_1_events.alast()
        self.assertEqual(user_1_events_last.description, user_description)
        global_description = "Webhooks have logged 5 total successful events."
        total_events_last = await total_events.alast()
        self.assertEqual(total_events_last.description, global_description)

        # Send 5 new webhook events for user_2
        for _ in range(5):
            webhook_event_2 = await sync_to_async(WebhookEventFactory)(
                webhook=self.webhook_user_2,
                content="{'message': 'ok_2'}",
                event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
            )
            with mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ):
                await sync_to_async(send_webhook_event)(webhook_event_2)

        user_2_events = Event.objects.filter(
            user=self.webhook_user_2.user
        ).order_by("date_created")

        # Confirm 5 webhook milestone event for user_2
        user_description = (
            f"User '{self.webhook_user_2.user.username}' "
            f"has placed their {intcomma(ordinal(5))} webhook event."
        )
        user_2_events_last = await user_2_events.alast()
        self.assertEqual(user_2_events_last.description, user_description)

        # Confirm 10 global webhook milestone event
        global_description = "Webhooks have logged 10 total successful events."
        total_events_last = await total_events.alast()
        self.assertEqual(total_events_last.description, global_description)

    @mock.patch(
        "cl.api.utils.get_webhook_logging_prefix",
        return_value="webhook:test_2",
    )
    async def test_avoid_logging_not_successful_webhook_events(
        self, mock_prefix
    ):
        """Can we avoid logging debug and failing webhook events?"""

        webhook_event_1 = await sync_to_async(WebhookEventFactory)(
            webhook=self.webhook_user_1,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
        )
        # Send a webhook event that fails to be delivered.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                500, mock_raw=True
            ),
        ):
            await sync_to_async(send_webhook_event)(webhook_event_1)

        webhook_events = WebhookEvent.objects.all()
        await webhook_event_1.arefresh_from_db()
        self.assertEqual(
            webhook_event_1.event_status, WEBHOOK_EVENT_STATUS.ENQUEUED_RETRY
        )
        self.assertEqual(await webhook_events.acount(), 1)
        # Confirm no milestone event should be created.
        milestone_events = Event.objects.all()
        self.assertEqual(await milestone_events.acount(), 0)

        webhook_event_2 = await sync_to_async(WebhookEventFactory)(
            webhook=self.webhook_user_1,
            content="{'message': 'ok_1'}",
            event_status=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
            debug=True,
        )
        # Send a debug webhook event.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            await sync_to_async(send_webhook_event)(webhook_event_2)

        await webhook_event_2.arefresh_from_db()
        self.assertEqual(
            webhook_event_2.event_status, WEBHOOK_EVENT_STATUS.SUCCESSFUL
        )
        self.assertEqual(await webhook_events.acount(), 2)
        # Confirm no milestone event should be created.
        self.assertEqual(await milestone_events.acount(), 0)


class CountParameterTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_1 = UserProfileWithParentsFactory.create(
            user__username="recap-user",
            user__password=make_password("password"),
        )
        permissions = Permission.objects.filter(
            codename__in=["has_recap_api_access", "has_recap_upload_access"]
        )
        cls.user_1.user.user_permissions.add(*permissions)

        cls.court_canb = CourtFactory(id="canb")
        cls.court_cand = CourtFactory(id="cand")

        cls.url = reverse("docket-list", kwargs={"version": "v4"})

        for i in range(7):
            DocketFactory(
                court=cls.court_canb,
                source=Docket.RECAP,
                pacer_case_id=str(100 + i),
            )
        for i in range(5):
            DocketFactory(
                court=cls.court_cand,
                source=Docket.HARVARD,
                pacer_case_id=str(200 + i),
            )

    def setUp(self):
        self.client = make_client(self.user_1.user.pk)

    async def test_count_on_returns_only_count(self):
        """
        Test that when 'count=on' is specified, the API returns only the count.
        """
        params = {"count": "on"}
        response = await self.client.get(self.url, params)

        self.assertEqual(response.status_code, 200)
        # The response should only contain the 'count' key
        self.assertEqual(list(response.data.keys()), ["count"])
        self.assertIsInstance(response.data["count"], int)
        # The count should match the total number of dockets
        expected_count = await Docket.objects.acount()
        self.assertEqual(response.data["count"], expected_count)

    async def test_standard_response_includes_count_url(self):
        """
        Test that the standard response includes a 'count' key with the count URL.
        """
        response = await self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("count", response.data)
        count_url = response.data["count"]
        self.assertIsInstance(count_url, str)
        self.assertIn("count=on", count_url)

    async def test_invalid_count_parameter(self):
        """
        Test that invalid 'count' parameter values are handled appropriately.
        """
        params = {"count": "invalid"}
        response = await self.client.get(self.url, params)

        self.assertEqual(response.status_code, 200)
        # The response should be the standard paginated response
        self.assertIn("results", response.data)
        self.assertIsInstance(response.data["results"], list)

    async def test_count_with_filters(self):
        """
        Test that the count returned matches the filters applied.
        """
        params = {"court": "canb", "source": Docket.RECAP, "count": "on"}
        response = await self.client.get(self.url, params)

        self.assertEqual(response.status_code, 200)
        expected_count = await Docket.objects.filter(
            court__id="canb",
            source=Docket.RECAP,
        ).acount()
        self.assertEqual(response.data["count"], expected_count)

    async def test_count_with_no_results(self):
        """
        Test that 'count=on' returns zero when no results match the filters.
        """
        params = {"court": "cand", "source": Docket.RECAP, "count": "on"}
        response = await self.client.get(self.url, params)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)


class TestApiUsage(SimpleTestCase):
    """Tests for combining v3 and v4 API usage data"""

    def setUp(self):
        """
        Set up test environment before each test.
        We create fresh mocks to avoid state bleeding between tests.
        """
        self.mock_redis = MagicMock()
        self.mock_pipeline = MagicMock()
        self.mock_redis.pipeline.return_value = self.mock_pipeline

    @patch("cl.api.utils.get_redis_interface")
    def test_single_date_combined_usage(self, mock_get_redis):
        """
        Test that for a single date:
        1. Both v3 and v4 usage is fetched
        2. Counts are properly combined
        3. The output format matches template expectations
        """
        mock_get_redis.return_value = self.mock_redis

        self.mock_pipeline.execute.return_value = [
            # First result: v3 API data
            [("1", 100.0), ("2", 50.0)],
            # Second result: v4 API data
            [("1", 50.0), ("2", 25.0)],
        ]

        results = invert_user_logs(
            start="2023-01-01", end="2023-01-01", add_usernames=False
        )

        expected = defaultdict(dict)
        expected[1] = OrderedDict({"2023-01-01": 150, "total": 150})
        expected[2] = OrderedDict({"2023-01-01": 75, "total": 75})

        self.assertEqual(results, expected)

    @patch("cl.api.utils.get_redis_interface")
    def test_multiple_dates_combined_usage(self, mock_get_redis):
        """
        Test that across multiple dates:
        1. API usage is correctly combined from both v3 and v4
        2. Totals accumulate properly across dates
        3. The data structure matches template expectations
        4. Date ordering is preserved
        """
        mock_get_redis.return_value = self.mock_redis
        self.mock_pipeline.execute.return_value = [
            # January 1st - v3 API
            [("1", 100.0), ("2", 50.0)],
            # January 1st - v4 API
            [("1", 50.0), ("2", 25.0)],
            # January 2nd - v3 API
            [("1", 200.0), ("2", 100.0)],
            # January 2nd - v4 API
            [("1", 100.0), ("2", 50.0)],
        ]

        results = invert_user_logs(
            start="2023-01-01", end="2023-01-02", add_usernames=False
        )

        # User 1:
        #   Jan 1: 150 (100 from v3 + 50 from v4)
        #   Jan 2: 300 (200 from v3 + 100 from v4)
        #   Total: 450
        # User 2:
        #   Jan 1: 75 (50 from v3 + 25 from v4)
        #   Jan 2: 150 (100 from v3 + 50 from v4)
        #   Total: 225
        expected = defaultdict(dict)
        expected[1] = OrderedDict(
            {"2023-01-01": 150, "2023-01-02": 300, "total": 450}
        )
        expected[2] = OrderedDict(
            {"2023-01-01": 75, "2023-01-02": 150, "total": 225}
        )

        self.assertEqual(results, expected)

    @patch("cl.api.utils.get_redis_interface")
    def test_anonymous_user_handling(self, mock_get_redis):
        """
        Test the handling of anonymous users, which have special requirements:
        1. Both 'None' and 'AnonymousUser' should be treated as the same user
        2. They should be combined under 'AnonymousUser' in the output
        3. Their usage should be summed correctly across both identifiers
        4. They should work with both API versions
        """
        mock_get_redis.return_value = self.mock_redis
        self.mock_pipeline.execute.return_value = [
            # January 1st - v3
            [
                ("None", 30.0),
                ("1", 100.0),
                ("AnonymousUser", 20.0),
            ],
            # January 1st - v4
            [
                ("AnonymousUser", 25.0),
                ("1", 50.0),
            ],
            # January 2nd - v3
            [("None", 40.0), ("1", 200.0)],
            # January 2nd - v4
            [
                ("1", 100.0),
                ("AnonymousUser", 35.0),
            ],
        ]

        results = invert_user_logs(
            start="2023-01-01", end="2023-01-02", add_usernames=False
        )

        expected = defaultdict(dict)
        # Expected results:
        # Anonymous user on Jan 1:
        #   - v3: 30 (None) + 20 (AnonymousUser) = 50
        #   - v4: 25 (AnonymousUser) = 25
        #   - Total for Jan 1: 75
        # Anonymous user on Jan 2:
        #   - v3: 40 (None) = 40
        #   - v4: 35 (AnonymousUser) = 35
        #   - Total for Jan 2: 75
        # Anonymous total across all dates: 150
        expected["AnonymousUser"] = OrderedDict(
            {
                "2023-01-01": 75,
                "2023-01-02": 75,
                "total": 150,
            }
        )
        expected[1] = OrderedDict(
            {
                "2023-01-01": 150,
                "2023-01-02": 300,
                "total": 450,
            }
        )

        self.assertEqual(results, expected)

        self.assertNotIn("None", results)

        self.assertIn("AnonymousUser", results)

        # Verify ordering is maintained even with anonymous users
        anonymous_data = results["AnonymousUser"]
        dates = list(anonymous_data.keys())
        dates.remove("total")
        self.assertEqual(dates, ["2023-01-01", "2023-01-02"])
