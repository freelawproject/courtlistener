import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.http import HttpRequest, JsonResponse
from django.test import Client, RequestFactory, override_settings
from django.urls import ResolverMatch, reverse
from django.utils.timezone import now
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN

from cl.api.utils import BulkJsonHistory
from cl.api.views import coverage_data
from cl.audio.api_views import AudioViewSet
from cl.audio.models import Audio
from cl.lib.redis_utils import make_redis_interface
from cl.lib.storage import clobbering_get_name
from cl.lib.test_helpers import IndexedSolrTestCase
from cl.scrapers.management.commands.cl_scrape_oral_arguments import (
    Command as OralArgumentCommand,
)
from cl.scrapers.test_assets import test_oral_arg_scraper
from cl.search.models import (
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    OpinionsCited,
)
from cl.stats.models import Event
from cl.tests.cases import SimpleTestCase, TestCase, TransactionTestCase


class BasicAPIPageTest(TestCase):
    """Test the basic views"""

    fixtures = [
        "judge_judy.json",
        "test_court.json",
        "test_objects_search.json",
    ]

    def setUp(self) -> None:
        self.client = Client()

    def test_api_root(self) -> None:
        r = self.client.get(
            reverse("api-root", kwargs={"version": "v3"}),
            HTTP_ACCEPT="text/html",
        )
        self.assertEqual(r.status_code, 200)

    def test_api_index(self) -> None:
        r = self.client.get(reverse("api_index"))
        self.assertEqual(r.status_code, 200)

    def test_swagger_interface(self) -> None:
        r = self.client.get(reverse("swagger_schema"))
        self.assertEqual(r.status_code, 200)

    def test_options_request(self) -> None:
        r = self.client.options(reverse("court_index"))
        self.assertEqual(r.status_code, 200)

    def test_court_index(self) -> None:
        r = self.client.get(reverse("court_index"))
        self.assertEqual(r.status_code, 200)

    def test_rest_docs(self) -> None:
        r = self.client.get(reverse("rest_docs"))
        self.assertEqual(r.status_code, 200)

    def test_bulk_data_index(self) -> None:
        r = self.client.get(reverse("bulk_data_index"))
        self.assertEqual(r.status_code, 200)

    def test_coverage_api(self) -> None:
        r = self.client.get(
            reverse("coverage_data", kwargs={"version": 2, "court": "ca1"})
        )
        self.assertEqual(r.status_code, 200)

    def test_coverage_api_via_url(self) -> None:
        r = self.client.get("/api/rest/v2/coverage/ca1/")
        self.assertEqual(r.status_code, 200)

    def test_api_info_page_displays_latest_rest_docs_by_default(self) -> None:
        response = self.client.get(reverse("rest_docs"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "rest-docs-vlatest.html")

    def test_api_info_page_can_display_different_versions_of_rest_docs(
        self,
    ) -> None:
        for version in ["v1", "v2"]:
            response = self.client.get(
                reverse("rest_docs", kwargs={"version": version})
            )
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, f"rest-docs-{version}.html")
            header = f"REST API &ndash; {version.upper()}"
            self.assertContains(response, header)


class CoverageTests(IndexedSolrTestCase):
    def test_coverage_data_view_provides_court_data(self) -> None:
        response = coverage_data(HttpRequest(), "v2", "ca1")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        self.assertContains(response, "annual_counts")
        self.assertContains(response, "total")

    def test_coverage_data_all_courts(self) -> None:
        r = self.client.get(
            reverse("coverage_data", kwargs={"version": "3", "court": "all"})
        )
        j = json.loads(r.content)
        self.assertTrue(len(j["annual_counts"].keys()) > 0)
        self.assertIn("total", j)

    def test_coverage_data_specific_court(self) -> None:
        r = self.client.get(
            reverse("coverage_data", kwargs={"version": "3", "court": "ca1"})
        )
        j = json.loads(r.content)
        self.assertTrue(len(j["annual_counts"].keys()) > 0)
        self.assertIn("total", j)


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
        "user_with_recap_api_access.json",
        "test_objects_audio.json",
        "recap_processing_queue_query_counts.json",
    ]

    def setUp(self) -> None:
        # Add the permissions to the user.
        u = User.objects.get(pk=6)
        ps = Permission.objects.filter(codename="has_recap_api_access")
        u.user_permissions.add(*ps)

        self.assertTrue(
            self.client.login(username="recap-user", password="password")
        )

    def tearDown(self) -> None:
        cache.clear()

    def test_audio_api_query_counts(self) -> None:
        with self.assertNumQueries(4):
            path = reverse("audio-list", kwargs={"version": "v3"})
            self.client.get(path)

    def test_search_api_query_counts(self) -> None:
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

    def test_party_api_query_counts(self) -> None:
        with self.assertNumQueries(9):
            path = reverse("party-list", kwargs={"version": "v3"})
            self.client.get(path)

        with self.assertNumQueries(6):
            path = reverse("attorney-list", kwargs={"version": "v3"})
            self.client.get(path)

    def test_recap_api_query_counts(self) -> None:
        with self.assertNumQueries(3):
            path = reverse("processingqueue-list", kwargs={"version": "v3"})
            self.client.get(path)

        with self.assertNumQueries(5):
            path = reverse("fast-recapdocument-list", kwargs={"version": "v3"})
            self.client.get(path, {"pacer_doc_id": "17711118263"})

    def test_recap_api_required_filter(self) -> None:
        path = reverse("fast-recapdocument-list", kwargs={"version": "v3"})
        r = self.client.get(path, {"pacer_doc_id": "17711118263"})
        self.assertEqual(HTTP_200_OK, r.status_code)
        r = self.client.get(path, {"pacer_doc_id__in": "17711118263,asdf"})
        self.assertEqual(HTTP_200_OK, r.status_code)


class ApiEventCreationTestCase(TestCase):
    """Check that events are created properly."""

    fixtures = ["user_with_recap_api_access.json"]

    @staticmethod
    def flush_stats():
        # Flush existing stats (else previous tests cause issues)
        r = make_redis_interface("STATS")
        r.flushdb()

    def setUp(self) -> None:
        # Add the permissions to the user.
        self.user = User.objects.get(pk=6)
        ps = Permission.objects.filter(codename="has_recap_api_access")
        self.user.user_permissions.add(*ps)
        self.flush_stats()

    def tearDown(self) -> None:
        Event.objects.all().delete()
        self.flush_stats()

    def hit_the_api(self):
        path = reverse("audio-list", kwargs={"version": "v3"})
        request = RequestFactory().get(path)

        # Create the view and change the milestones to be something we can test
        # (Otherwise, we need to make 1,000 requests in this test)
        view = AudioViewSet.as_view({"get": "list"})
        view.milestones = [1]

        # Set the attributes needed in the absence of middleware
        request.user = self.user
        request.resolver_match = ResolverMatch(
            view, {"version": "v3"}, "audio-list"
        )

        view(request)

    def test_are_events_created_properly(self) -> None:
        """Are event objects created as API requests are made?"""
        self.hit_the_api()

        expected_event_count = 1
        self.assertEqual(expected_event_count, Event.objects.count())


class DRFOrderingTests(TestCase):
    """Does ordering work generally and specifically?"""

    fixtures = [
        "judge_judy.json",
        "authtest_data.json",
        "test_objects_search.json",
    ]

    def test_position_ordering(self):
        path = reverse("position-list", kwargs={"version": "v3"})
        r = self.client.get(path, {"order_by": "date_start"})
        self.assertLess(
            r.data["results"][0]["date_start"],
            r.data["results"][-1]["date_start"],
        )
        r = self.client.get(path, {"order_by": "-date_start"})
        self.assertGreater(
            r.data["results"][0]["date_start"],
            r.data["results"][-1]["date_start"],
        )

    def test_opinion_ordering_by_id(self):
        path = reverse("opinion-list", kwargs={"version": "v3"})
        r = self.client.get(path, {"order_by": "id"})
        self.assertLess(
            r.data["results"][0]["resource_uri"],
            r.data["results"][-1]["resource_uri"],
        )
        r = self.client.get(path, {"order_by": "-id"})
        self.assertGreater(
            r.data["results"][0]["resource_uri"],
            r.data["results"][-1]["resource_uri"],
        )


class FilteringCountTestCase(object):
    """Mixin for adding an additional test assertion."""

    # noinspection PyPep8Naming
    def assertCountInResults(self, expected_count):
        """Do we get the correct number of API results from the endpoint?"""
        print(f"Path and q are: {self.path}, {self.q}")
        r = self.client.get(self.path, self.q)
        self.assertLess(r.status_code, 400)  # A valid status code?
        got = len(r.data["results"])
        self.assertEqual(
            got,
            expected_count,
            msg=f"Expected {expected_count}, but got {got}.\n\nr.data was: {r.data}",
        )


class DRFJudgeApiFilterTests(TestCase, FilteringCountTestCase):
    """Do the filters work properly?"""

    fixtures = ["judge_judy.json", "authtest_data.json"]

    def setUp(self) -> None:
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        self.q: Dict[Any, Any] = dict()

    def test_judge_filtering_by_first_name(self) -> None:
        """Can we filter by first name?"""
        self.path = reverse("person-list", kwargs={"version": "v3"})

        # Filtering with good values brings back 1 result.
        self.q = {"name_first__istartswith": "judith"}
        self.assertCountInResults(1)

        # Filtering with bad values brings back no results.
        self.q = {"name_first__istartswith": "XXX"}
        self.assertCountInResults(0)

    def test_judge_filtering_by_date(self) -> None:
        """Do the various date filters work properly?"""
        self.path = reverse("person-list", kwargs={"version": "v3"})

        # Exact match for her birthday
        correct_date = date(1942, 10, 21)
        self.q = {"date_dob": correct_date.isoformat()}
        self.assertCountInResults(1)

        # People born after the day before her birthday
        before = correct_date - timedelta(days=1)
        self.q = {"date_dob__gt": before.isoformat()}
        self.assertCountInResults(5)

        # Flip the logic. This should return no results.
        self.q = {"date_dob__lt": before.isoformat()}
        self.assertCountInResults(11)

    def test_nested_judge_filtering(self) -> None:
        """Can we filter across various relations?

        Each of these assertions adds another parameter making our final test
        a pretty complex combination.
        """
        self.path = reverse("person-list", kwargs={"version": "v3"})

        # No results for a bad query
        self.q["educations__degree_level"] = "cert"
        self.assertCountInResults(0)

        # One result for a good query
        self.q["educations__degree_level"] = "jd"
        self.assertCountInResults(1)

        # Again, no results
        self.q["educations__degree_year"] = 1400
        self.assertCountInResults(0)

        # But with the correct year...one result
        self.q["educations__degree_year"] = 1965
        self.assertCountInResults(1)

        # Judy went to "New York Law School"
        self.q["educations__school__name__istartswith"] = "New York Law"
        self.assertCountInResults(1)

        # Moving on to careers. Bad value, then good.
        self.q["positions__job_title__icontains"] = "XXX"
        self.assertCountInResults(0)
        self.q["positions__job_title__icontains"] = "lawyer"
        self.assertCountInResults(1)

        # Moving on to titles...bad value, then good.
        self.q["positions__position_type"] = "act-jud"
        self.assertCountInResults(0)
        self.q["positions__position_type"] = "prac"
        self.assertCountInResults(1)

        # Political affiliation filtering...bad, then good.
        self.q["political_affiliations__political_party"] = "r"
        self.assertCountInResults(0)
        self.q["political_affiliations__political_party"] = "d"
        self.assertCountInResults(2)

        # Sources
        about_now = "2015-12-17T00:00:00Z"
        self.q["sources__date_modified__gt"] = about_now
        self.assertCountInResults(0)
        self.q.pop("sources__date_modified__gt")  # Next key doesn't overwrite.
        self.q["sources__date_modified__lt"] = about_now
        self.assertCountInResults(2)

        # ABA Ratings
        self.q["aba_ratings__rating"] = "q"
        self.assertCountInResults(0)
        self.q["aba_ratings__rating"] = "nq"
        self.assertCountInResults(2)

    def test_education_filtering(self) -> None:
        """Can we filter education objects?"""
        self.path = reverse("education-list", kwargs={"version": "v3"})

        # Filter by degree
        self.q["degree_level"] = "cert"
        self.assertCountInResults(0)
        self.q["degree_level"] = "jd"
        self.assertCountInResults(1)

        # Filter by degree's related field, School
        self.q["school__name__istartswith"] = "XXX"
        self.assertCountInResults(0)
        self.q["school__name__istartswith"] = "New York"
        self.assertCountInResults(1)

    def test_title_filtering(self) -> None:
        """Can Judge Titles be filtered?"""
        self.path = reverse("position-list", kwargs={"version": "v3"})

        # Filter by title_name
        self.q["position_type"] = "act-jud"
        self.assertCountInResults(0)
        self.q["position_type"] = "c-jud"
        self.assertCountInResults(1)

    def test_reverse_filtering(self) -> None:
        """Can we filter Source objects by judge name?"""
        # I want any source notes about judge judy.
        self.path = reverse("source-list", kwargs={"version": "v3"})
        self.q = {"person": 2}
        self.assertCountInResults(1)

    def test_position_filters(self) -> None:
        """Can we filter on positions"""
        self.path = reverse("position-list", kwargs={"version": "v3"})

        # I want positions to do with judge #2 (Judy)
        self.q["person"] = 2
        self.assertCountInResults(2)

        # Retention events
        self.q["retention_events__retention_type"] = "reapp_gov"
        self.assertCountInResults(1)

        # Appointer was Bill, id of 1
        self.q["appointer"] = 1
        self.assertCountInResults(1)
        self.q["appointer"] = 3
        self.assertCountInResults(0)

    def test_racial_filters(self) -> None:
        """Can we filter by race?"""
        self.path = reverse("person-list", kwargs={"version": "v3"})
        self.q = {"race": "w"}
        self.assertCountInResults(2)

        # Do an OR. This returns judges that are either black or white (not
        # that it matters, MJ)
        self.q["race"] = ["w", "b"]
        self.assertCountInResults(3)

    def test_circular_relationships(self) -> None:
        """Do filters configured using strings instead of classes work?"""
        self.path = reverse("education-list", kwargs={"version": "v3"})

        # Traverse person, position
        self.q["person__positions__job_title__icontains"] = "xxx"
        self.assertCountInResults(0)
        self.q["person__positions__job_title__icontains"] = "lawyer"
        self.assertCountInResults(2)

        # Just traverse to the judge table
        self.q["person__name_first"] = "Judy"  # Nope.
        self.assertCountInResults(0)
        self.q["person__name_first"] = "Judith"  # Yep.
        self.assertCountInResults(2)

    def test_exclusion_filters(self) -> None:
        """Can we exclude using !'s?"""
        self.path = reverse("position-list", kwargs={"version": "v3"})

        # I want positions to do with any judge other than judge #1
        # Note the exclamation mark. In a URL this would look like
        # "?judge!=1". Fun stuff.
        self.q["person!"] = 2
        self.assertCountInResults(1)  # Bill


class DRFRecapApiFilterTests(TestCase, FilteringCountTestCase):
    fixtures = [
        "recap_docs.json",
        "attorney_party.json",
        "user_with_recap_api_access.json",
    ]

    def setUp(self) -> None:
        # Add the permissions to the user.
        u = User.objects.get(pk=6)
        ps = Permission.objects.filter(codename="has_recap_api_access")
        u.user_permissions.add(*ps)

        self.assertTrue(
            self.client.login(username="recap-user", password="password")
        )
        self.q: Dict[Any, Any] = dict()

    def test_docket_entry_to_docket_filters(self) -> None:
        """Do a variety of docket entry filters work?"""
        self.path = reverse("docketentry-list", kwargs={"version": "v3"})

        # Docket filters...
        self.q["docket__id"] = 1
        self.assertCountInResults(1)
        self.q["docket__id"] = 10000000000
        self.assertCountInResults(0)
        self.q = {"docket__id!": 100000000}
        self.assertCountInResults(1)

    def test_docket_tag_filters(self) -> None:
        """Can we filter dockets by tags?"""
        self.path = reverse("docket-list", kwargs={"version": "v3"})

        self.q = {"docket_entries__recap_documents__tags": 1}
        self.assertCountInResults(1)
        self.q = {"docket_entries__recap_documents__tags": 2}
        self.assertCountInResults(0)

    def test_docket_entry_docket_court_filters(self) -> None:
        self.path = reverse("docketentry-list", kwargs={"version": "v3"})

        # Across docket to court...
        self.q["docket__court__id"] = "ca1"
        self.assertCountInResults(1)
        self.q["docket__court__id"] = "foo"
        self.assertCountInResults(0)

    def test_nested_recap_document_filters(self) -> None:
        self.path = reverse("docketentry-list", kwargs={"version": "v3"})

        self.q["id"] = 1
        self.assertCountInResults(1)
        self.q = {"recap_documents__id": 1}
        self.assertCountInResults(1)
        self.q = {"recap_documents__id": 2}
        self.assertCountInResults(0)

        self.q = {"recap_documents__tags": 1}
        self.assertCountInResults(1)
        self.q = {"recap_documents__tags": 2}
        self.assertCountInResults(0)

        # Something wacky...
        self.q = {"recap_documents__docket_entry__docket__id": 1}
        self.assertCountInResults(1)
        self.q = {"recap_documents__docket_entry__docket__id": 2}
        self.assertCountInResults(0)

    def test_recap_document_filters(self) -> None:
        self.path = reverse("recapdocument-list", kwargs={"version": "v3"})

        self.q["id"] = 1
        self.assertCountInResults(1)
        self.q["id"] = 2
        self.assertCountInResults(0)

        self.q = {"pacer_doc_id": 17711118263}
        self.assertCountInResults(1)
        self.q = {"pacer_doc_id": "17711118263-nope"}
        self.assertCountInResults(0)

        self.q = {"docket_entry__id": 1}
        self.assertCountInResults(1)
        self.q = {"docket_entry__id": 2}
        self.assertCountInResults(0)

        self.q = {"tags": 1}
        self.assertCountInResults(1)
        self.q = {"tags": 2}
        self.assertCountInResults(0)
        self.q = {"tags__name": "test"}
        self.assertCountInResults(1)
        self.q = {"tags__name": "test2"}
        self.assertCountInResults(0)

    def test_attorney_filters(self) -> None:
        self.path = reverse("attorney-list", kwargs={"version": "v3"})

        self.q["id"] = 1
        self.assertCountInResults(1)
        self.q["id"] = 2
        self.assertCountInResults(0)

        self.q = {"docket__id": 1}
        self.assertCountInResults(1)
        self.q = {"docket__id": 2}
        self.assertCountInResults(0)

        self.q = {"parties_represented__id": 1}
        self.assertCountInResults(1)
        self.q = {"parties_represented__id": 2}
        self.assertCountInResults(0)
        self.q = {"parties_represented__name__contains": "Honker"}
        self.assertCountInResults(1)
        self.q = {"parties_represented__name__contains": "Honker-Nope"}
        self.assertCountInResults(0)

    def test_party_filters(self) -> None:
        self.path = reverse("party-list", kwargs={"version": "v3"})

        self.q["id"] = 1
        self.assertCountInResults(1)
        self.q["id"] = 2
        self.assertCountInResults(0)

        # This represents dockets that the party was a part of.
        self.q = {"docket__id": 1}
        self.assertCountInResults(1)
        self.q = {"docket__id": 2}
        self.assertCountInResults(0)

        # Contrasted with this, which joins based on their attorney.
        self.q = {"attorney__docket__id": 1}
        self.assertCountInResults(1)
        self.q = {"attorney__docket__id": 2}
        self.assertCountInResults(0)

        self.q = {"name": "Honker"}
        self.assertCountInResults(1)
        self.q = {"name": "Cardinal Bonds"}
        self.assertCountInResults(0)

        self.q = {"attorney__name__icontains": "Juneau"}
        self.assertCountInResults(1)
        self.q = {"attorney__name__icontains": "Juno"}
        self.assertCountInResults(0)


class DRFSearchAppAndAudioAppApiFilterTest(TestCase, FilteringCountTestCase):
    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
        "test_objects_audio.json",
        "authtest_data.json",
        "user_with_recap_api_access.json",
    ]

    def setUp(self) -> None:
        self.assertTrue(
            self.client.login(username="recap-user", password="password")
        )
        self.q: Dict[Any, Any] = dict()

    def test_cluster_filters(self) -> None:
        """Do a variety of cluster filters work?"""
        self.path = reverse("opinioncluster-list", kwargs={"version": "v3"})

        # Related filters
        self.q["panel__id"] = 2
        self.assertCountInResults(1)
        self.q["non_participating_judges!"] = 1  # Exclusion filter.
        self.assertCountInResults(1)
        self.q["sub_opinions__author"] = 2
        self.assertCountInResults(4)

        # Citation filters
        self.q = {
            "citations__volume": 56,
            "citations__reporter": "F.2d",
            "citations__page": "9",
        }
        self.assertCountInResults(1)

        # Integer lookups
        self.q = dict()
        self.q["scdb_votes_majority__gt"] = 10
        self.assertCountInResults(0)
        self.q["scdb_votes_majority__gt"] = 1
        self.assertCountInResults(1)

    def test_opinion_filter(self) -> None:
        """Do a variety of opinion filters work?"""
        self.path = reverse("opinion-list", kwargs={"version": "v3"})

        # Simple filters
        self.q["sha1"] = "asdfasdfasdfasdfasdfasddf-nope"
        self.assertCountInResults(0)
        self.q["sha1"] = "asdfasdfasdfasdfasdfasddf"
        self.assertCountInResults(6)

        # Boolean filter
        self.q["per_curiam"] = False
        self.assertCountInResults(6)

        # Related filters
        self.q["cluster__panel"] = 1
        self.assertCountInResults(0)
        self.q["cluster__panel"] = 2
        self.assertCountInResults(4)

        self.q = dict()
        self.q["author__name_first__istartswith"] = "Nope"
        self.assertCountInResults(0)
        self.q["author__name_first__istartswith"] = "jud"
        self.assertCountInResults(6)

        self.q = dict()
        self.q["joined_by__name_first__istartswith"] = "Nope"
        self.assertCountInResults(0)
        self.q["joined_by__name_first__istartswith"] = "jud"
        self.assertCountInResults(1)

        self.q = dict()
        types = [Opinion.COMBINED]
        self.q["type"] = types
        self.assertCountInResults(5)
        types.append(Opinion.LEAD)
        self.assertCountInResults(6)

    def test_docket_filters(self) -> None:
        """Do a variety of docket filters work?"""
        self.path = reverse("docket-list", kwargs={"version": "v3"})

        # Simple filter
        self.q["docket_number"] = "14-1165-nope"
        self.assertCountInResults(0)
        self.q["docket_number"] = "docket number 1 005"
        self.assertCountInResults(1)

        # Related filters
        self.q["court"] = "test"
        self.assertCountInResults(1)

        self.q["clusters__panel__name_first__istartswith"] = "jud-nope"
        self.assertCountInResults(0)
        self.q["clusters__panel__name_first__istartswith"] = "jud"
        self.assertCountInResults(1)

        self.q[
            "audio_files__sha1"
        ] = "de8cff186eb263dc06bdc5340860eb6809f898d3-nope"
        self.assertCountInResults(0)
        self.q[
            "audio_files__sha1"
        ] = "de8cff186eb263dc06bdc5340860eb6809f898d3"
        self.assertCountInResults(1)

    def test_audio_filters(self) -> None:
        self.path = reverse("audio-list", kwargs={"version": "v3"})

        # Simple filter
        self.q["sha1"] = "de8cff186eb263dc06bdc5340860eb6809f898d3-nope"
        self.assertCountInResults(0)
        self.q["sha1"] = "de8cff186eb263dc06bdc5340860eb6809f898d3"
        self.assertCountInResults(1)

        # Related filter
        self.q["docket__court"] = "test"
        self.assertCountInResults(1)

        # Multiple choice filter
        self.q = dict()
        sources = ["C"]
        self.q["source"] = sources
        self.assertCountInResults(2)
        sources.append("CR")
        self.assertCountInResults(3)

    def test_opinion_cited_filters(self) -> None:
        """Do the filters on the opinions_cited work?"""
        self.path = reverse("opinionscited-list", kwargs={"version": "v3"})

        # Simple related filter
        self.q["citing_opinion__sha1"] = "asdf-nope"
        self.assertCountInResults(0)
        self.q["citing_opinion__sha1"] = "asdfasdfasdfasdfasdfasddf"
        self.assertCountInResults(4)

        # Fancy filter: Citing Opinions written by judges with first name
        # istartingwith "jud"
        self.q["citing_opinion__author__name_first__istartswith"] = "jud-nope"
        self.assertCountInResults(0)
        self.q["citing_opinion__author__name_first__istartswith"] = "jud"
        self.assertCountInResults(4)


class DRFFieldSelectionTest(TestCase):
    """Test selecting only certain fields"""

    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
        "authtest_data.json",
    ]

    def test_only_some_fields_returned(self):
        """Can we return only some of the fields?"""

        # First check the Judge endpoint, one of our more complicated ones.
        path = reverse("person-list", kwargs={"version": "v3"})
        fields_to_return = ["educations", "date_modified", "slug"]
        q = {"fields": ",".join(fields_to_return)}
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        r = self.client.get(path, q)
        self.assertEqual(
            len(r.data["results"][0].keys()), len(fields_to_return)
        )

        # One more check for good measure.
        path = reverse("opinioncluster-list", kwargs={"version": "v3"})
        fields_to_return = ["per_curiam", "slug"]
        r = self.client.get(path, q)
        self.assertEqual(
            len(r.data["results"][0].keys()), len(fields_to_return)
        )


class DRFRecapPermissionTest(TestCase):
    fixtures = ["user_with_recap_api_access.json", "authtest_data.json"]

    def setUp(self) -> None:
        # Add the permissions to the user.
        u = User.objects.get(pk=6)
        ps = Permission.objects.filter(codename="has_recap_api_access")
        u.user_permissions.add(*ps)

        self.paths = [
            reverse(path, kwargs={"version": "v3"})
            for path in [
                "recapdocument-list",
                "docketentry-list",
                "attorney-list",
                "party-list",
            ]
        ]

    def test_has_access(self) -> None:
        """Does the RECAP user have access to all of the RECAP endpoints?"""
        self.assertTrue(
            self.client.login(username="recap-user", password="password")
        )
        for path in self.paths:
            print(f"Access allowed to recap user at: {path}... ", end="")
            r = self.client.get(path)
            self.assertEqual(r.status_code, HTTP_200_OK)
            print("✓")

    def test_lacks_access(self) -> None:
        """Does a normal user lack access to the RECPAP endpoints?"""
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        for path in self.paths:
            print(f"Access denied to non-recap user at: {path}... ", end="")
            r = self.client.get(path)
            self.assertEqual(r.status_code, HTTP_403_FORBIDDEN)
            print("✓")


class BulkJsonHistoryTest(SimpleTestCase):
    def setUp(self) -> None:
        self.history = BulkJsonHistory("test", settings.BULK_DATA_DIR)

    def tearDown(self) -> None:
        self.history.delete_from_disk()

    def test_load_the_file(self) -> None:
        data = self.history.load_json_file()
        self.assertEqual({}, data)

    def test_load_date_when_none(self) -> None:
        d = self.history.get_last_good_date()
        self.assertIsNone(d)

    def test_set_date_then_load_it(self) -> None:
        self.history.add_current_attempt_and_save()
        self.history.mark_success_and_save()
        d = self.history.get_last_good_date()
        self.assertAlmostEqual(
            # The date serialized is within ten seconds of now.
            d,
            now(),
            delta=timedelta(seconds=10),
        )

    def test_add_current_attempt(self) -> None:
        self.history.add_current_attempt_and_save()
        d = self.history.get_last_attempt()
        self.assertAlmostEqual(d, now(), delta=timedelta(seconds=10))


class BulkDataTest(TestCase):
    tmp_data_dir = "/tmp/bulk-dir/"

    def setUp(self) -> None:
        docket = Docket(
            case_name="foo",
            court=Court.objects.get(pk="test"),
            source=Docket.DEFAULT,
        )
        docket.save()
        # Must be more than a year old for all tests to be runnable.
        last_month = now().date() - timedelta(days=400)
        self.doc_cluster = OpinionCluster(
            case_name="foo", docket=docket, date_filed=last_month
        )
        self.doc_cluster.save(index=False)
        opinion = Opinion(cluster=self.doc_cluster, type="Lead Opinion")
        opinion.save(index=False)

        opinion2 = Opinion(cluster=self.doc_cluster, type="Concurrence")
        opinion2.save(index=False)

        OpinionsCited.objects.create(
            citing_opinion=opinion2, cited_opinion=opinion
        )

        # Scrape the audio "site" and add its contents
        site = test_oral_arg_scraper.Site().parse()
        with mock.patch(
            "cl.lib.storage.get_name_by_incrementing",
            side_effect=clobbering_get_name,
        ):
            OralArgumentCommand().scrape_court(site, full_crawl=True)

    def tearDown(self) -> None:
        OpinionCluster.objects.all().delete()
        Docket.objects.all().delete()
        Audio.objects.all().delete()
        try:
            shutil.rmtree(self.tmp_data_dir)
        except OSError:
            pass

    @override_settings(BULK_DATA_DIR=tmp_data_dir)
    def test_make_all_bulk_files(self) -> None:
        """Can we successfully generate all bulk files?"""
        call_command("cl_make_bulk_data")

    def test_database_has_objects_for_bulk_export(self) -> None:
        # This is a very weird test. It's essentially just testing the
        # setUp function, which...OK?
        self.assertTrue(Opinion.objects.count() > 0, "No opinions exist")
        self.assertTrue(
            OpinionsCited.objects.count() > 0, "No citations exist"
        )
        self.assertTrue(Audio.objects.count() > 0, "No audio exist")
        self.assertTrue(Docket.objects.count() > 0, "No docket exist")
        self.assertTrue(Court.objects.count() > 0, "No courts exist")
        self.assertEqual(
            Court.objects.get(pk="test").full_name, "Testing Supreme Court"
        )
