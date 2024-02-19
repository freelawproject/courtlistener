import datetime
from unittest import mock

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.db.models import F
from django.http import HttpRequest
from django.test import AsyncRequestFactory, override_settings
from django.urls import reverse
from elasticsearch_dsl import Q
from factory import RelatedFactory
from lxml import etree, html
from rest_framework.status import HTTP_200_OK

from cl.lib.redis_utils import make_redis_interface
from cl.lib.test_helpers import (
    CourtTestCase,
    EmptySolrTestCase,
    IndexedSolrTestCase,
    PeopleTestCase,
    SearchTestCase,
)
from cl.people_db.factories import PersonFactory
from cl.search.constants import o_type_index_map
from cl.search.documents import (
    ES_CHILD_ID,
    OpinionClusterDocument,
    OpinionDocument,
)
from cl.search.factories import (
    CitationWithParentsFactory,
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionFactory,
    OpinionWithChildrenFactory,
)
from cl.search.feeds import JurisdictionFeed
from cl.search.management.commands.cl_index_parent_and_child_docs import (
    compose_redis_key,
)
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Opinion,
    OpinionCluster,
    OpinionsCited,
)
from cl.search.tasks import (
    es_save_document,
    index_related_cites_fields,
    update_children_docs_by_query,
    update_es_document,
)
from cl.search.views import do_search
from cl.tests.cases import (
    CountESTasksTestCase,
    ESIndexTestCase,
    TestCase,
    TransactionTestCase,
)
from cl.users.factories import UserProfileWithParentsFactory


class OpinionAPISolrSearchTest(IndexedSolrTestCase):
    @classmethod
    def setUpTestData(cls):
        court = CourtFactory(
            id="canb",
            jurisdiction="FB",
            full_name="court of the Medical Worries",
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Washington.",
            case_name_full="Strickland v. Washington.",
            docket=DocketFactory(court=court, docket_number="1:21-cv-1234"),
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                html_columbia="<p>Code, &#167; 1-815</p>",
            ),
            date_filed=datetime.date(2020, 8, 15),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            syllabus="some rando syllabus",
            procedural_history="some rando history",
            source="C",
            judges="",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            citation_count=1,
            scdb_votes_minority=3,
            scdb_votes_majority=6,
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Lorem.",
            case_name_full="Strickland v. Lorem.",
            date_filed=datetime.date(2020, 8, 15),
            docket=DocketFactory(court=court, docket_number="123456"),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            syllabus="some rando syllabus",
            procedural_history="some rando history",
            source="C",
            judges="",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            citation_count=1,
            scdb_votes_minority=3,
            scdb_votes_majority=6,
        )
        super().setUpTestData()

    async def _test_api_results_count(
        self, params, expected_count, field_name
    ):
        """Get the result count in a API query response"""
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v3"}), params
        )
        got = len(r.data["results"])
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of search results in API with %s "
            "filter applied.\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            "Params were: %s" % (field_name, expected_count, got, params),
        )
        return r

    async def test_can_perform_a_regular_text_query(self) -> None:
        search_params = {"q": "supreme"}

        r = await self._test_api_results_count(search_params, 1, "text_query")
        self.assertIn("Honda", r.content.decode())

    async def test_can_search_with_white_spaces_only(self) -> None:
        """Does everything work when whitespace is in various fields?"""
        search_params = {"q": " ", "judge": " ", "case_name": " "}

        # API, 2 results expected since the query shows published clusters by default
        r = await self._test_api_results_count(
            search_params, 4, "white_spaces"
        )
        self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_the_case_name(self) -> None:
        search_params = {"q": "*", "case_name": "honda"}

        r = await self._test_api_results_count(search_params, 1, "case_name")
        self.assertIn("Honda", r.content.decode())

    async def test_can_query_with_an_old_date(self) -> None:
        """Do we have any recurrent issues with old dates and strftime (issue
        220)?"""
        search_params = {"q": "*", "filed_after": "1890"}

        r = await self._test_api_results_count(search_params, 4, "filed_after")
        self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_filed_range(self) -> None:
        """Does querying by date work?"""
        search_params = {
            "q": "*",
            "filed_after": "1895-06",
            "filed_before": "1896-01",
        }

        r = await self._test_api_results_count(search_params, 1, "filed_range")
        self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_a_docket_number(self) -> None:
        """Can we query by docket number?"""
        search_params = {"q": "*", "docket_number": "2"}

        r = await self._test_api_results_count(
            search_params, 1, "docket_number"
        )
        self.assertIn("Honda", r.content.decode())

    async def test_can_filter_by_citation_number(self) -> None:
        """Can we query by citation number?"""
        get_dicts = [{"q": "*", "citation": "33"}, {"q": "citation:33"}]
        for get_dict in get_dicts:
            r = await self._test_api_results_count(
                get_dict, 1, "citation_count"
            )
            self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_neutral_citation(self) -> None:
        """Can we query by neutral citation numbers?"""
        search_params = {"q": "*", "neutral_cite": "22"}

        r = await self._test_api_results_count(
            search_params, 1, "citation_number"
        )
        self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_judge_name(self) -> None:
        """Can we query by judge name?"""
        search_array = [{"q": "*", "judge": "david"}, {"q": "judge:david"}]
        for search_params in search_array:
            r = await self._test_api_results_count(
                search_params, 1, "judge_name"
            )
            self.assertIn("Honda", r.content.decode())

    async def test_can_filter_by_nature_of_suit(self) -> None:
        """Can we query by nature of suit?"""
        search_params = {"q": 'suitNature:"copyright"'}

        r = await self._test_api_results_count(search_params, 1, "suit_nature")
        self.assertIn("Honda", r.content.decode())

    async def test_can_filtering_by_citation_count(self) -> None:
        """Can we find Documents by citation filtering?"""
        search_params = {"q": "*", "cited_lt": 7, "cited_gt": 5}

        r = await self._test_api_results_count(
            search_params, 1, "citation_count"
        )
        self.assertIn("Honda", r.content.decode())

        search_params = {"q": "*", "cited_lt": 100, "cited_gt": 80}

        r = self._test_api_results_count(search_params, 0, "citation_count")

    async def test_citation_ordering_by_citation_count(self) -> None:
        """Can the results be re-ordered by citation count?"""
        search_params = {"q": "*", "order_by": "citeCount desc"}
        most_cited_name = "case name cluster 3"
        less_cited_name = "Howard v. Honda"

        r = await self._test_api_results_count(
            search_params, 4, "citeCount desc"
        )
        self.assertTrue(
            r.content.decode().index(most_cited_name)
            < r.content.decode().index(less_cited_name),
            msg="'%s' should come BEFORE '%s' when ordered by descending "
            "citeCount." % (most_cited_name, less_cited_name),
        )

        search_params = {"q": "*", "order_by": "citeCount asc"}

        r = await self._test_api_results_count(
            search_params, 4, "citeCount asc"
        )
        self.assertTrue(
            r.content.decode().index(most_cited_name)
            > r.content.decode().index(less_cited_name),
            msg="'%s' should come AFTER '%s' when ordered by ascending "
            "citeCount." % (most_cited_name, less_cited_name),
        )

    async def test_random_ordering(self) -> None:
        """Can the results be ordered randomly?

        This test is difficult since we can't check that things actually get
        ordered randomly, but we can at least make sure the query succeeds.
        """
        search_params = {"q": "*", "order_by": "random_123 desc"}

        await self._test_api_results_count(search_params, 4, "order random")

    async def test_issue_635_leading_zeros(self) -> None:
        """Do queries with leading zeros work equal to ones without?"""
        search_params = {"docket_number": "005", "stat_Errata": "on"}
        expected = 1

        await self._test_api_results_count(
            search_params, expected, "docket_number"
        )

        search_params["docket_number"] = "5"
        await self._test_api_results_count(
            search_params, expected, "docket_number"
        )

    async def test_issue_1193_docket_numbers_as_phrase(self) -> None:
        """Are docket numbers searched as a phrase?"""
        # Search for the full docket number. Does it work?
        search_params = {
            "docket_number": "docket number 1 005",
            "stat_Errata": "on",
        }
        await self._test_api_results_count(search_params, 1, "docket_number")

        # Twist up the docket numbers. Do we get no results?
        search_params["docket_number"] = "docket 005 number"
        await self._test_api_results_count(search_params, 0, "docket_number")

    async def test_can_use_docket_number_proximity(self) -> None:
        """Test docket_number proximity query, so that docket numbers like
        1:21-cv-1234 can be matched by queries like: 21-1234
        """
        # Query 21-1234, return results for 1:21-bk-1234
        search_params = {"type": SEARCH_TYPES.OPINION, "q": "21-1234"}

        r = await self._test_api_results_count(
            search_params, 1, "docket number proximity"
        )
        self.assertIn("Washington", r.content.decode())

        # Query 1:21-cv-1234
        search_params["q"] = "1:21-cv-1234"

        r = await self._test_api_results_count(
            search_params, 1, "docket number proximity"
        )
        self.assertIn("Washington", r.content.decode())

        # docket_number box filter: 21-1234, return results for 1:21-bk-1234
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "docket_number": "21-1234",
        }

        r = await self._test_api_results_count(
            search_params, 1, "docket number proximity"
        )
        self.assertIn("Washington", r.content.decode())

    async def test_can_filter_with_docket_number_suffixes(self) -> None:
        """Test docket_number with suffixes can be found."""
        # Indexed: 1:21-cv-1234 -> Search: 1:21-cv-1234-ABC
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"1:21-cv-1234-ABC",
        }

        r = await self._test_api_results_count(
            search_params, 1, "docket number box"
        )
        self.assertIn("Washington", r.content.decode())

        # Other kind of formats can still be searched -> 123456
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "123456",
        }

        r = await self._test_api_results_count(
            search_params, 1, "docket number box"
        )
        self.assertIn("Lorem", r.content.decode())

    async def test_results_api_fields(self) -> None:
        """Confirm fields in RECAP Search API results."""
        search_params = {"q": "Honda"}
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_to_check = [
            "absolute_url",
            "attorney",
            "author_id",
            "caseName",
            "caseNameShort",
            "citation",
            "citeCount",
            "cites",
            "cluster_id",
            "court",
            "court_citation_string",
            "court_exact",
            "court_id",
            "dateArgued",
            "dateFiled",
            "dateReargued",
            "dateReargumentDenied",
            "docketNumber",
            "docket_id",
            "download_url",
            "id",
            "joined_by_ids",
            "judge",
            "lexisCite",
            "local_path",
            "neutralCite",
            "non_participating_judge_ids",
            "pagerank",
            "panel_ids",
            "per_curiam",
            "scdb_id",
            "sibling_ids",
            "snippet",
            "source",
            "status",
            "status_exact",
            "suitNature",
            "timestamp",
            "type",
        ]
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, len(keys_to_check))
        for key in keys_to_check:
            self.assertTrue(
                key in r.data["results"][0],
                msg=f"Key {key} not found in the result object.",
            )


class OpinionsESSearchTest(
    ESIndexTestCase, CourtTestCase, PeopleTestCase, SearchTestCase, TestCase
):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        court = CourtFactory(
            id="canb",
            jurisdiction="FB",
            full_name="court of the Medical Worries",
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Washington.",
            case_name_full="Strickland v. Washington.",
            docket=DocketFactory(court=court, docket_number="1:21-cv-1234"),
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                html_columbia="<p>Code, &#167; 1-815</p>",
                type=Opinion.REMITTUR,
            ),
            date_filed=datetime.date(2020, 8, 15),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            syllabus="some rando syllabus",
            procedural_history="some rando history",
            source="C",
            judges="",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            citation_count=1,
            scdb_votes_minority=3,
            scdb_votes_majority=6,
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Lorem.",
            case_name_full="Strickland v. Lorem.",
            date_filed=datetime.date(2020, 8, 15),
            docket=DocketFactory(court=court, docket_number="123456"),
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                type=Opinion.ADDENDUM,
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            syllabus="This is a opinion syllabus",
            posture="This is a opinion posture",
            procedural_history="This is a opinion procedural history",
            source="C",
            judges="",
            attorneys="B. B. Giles, Lindley W. Barnes, and John A. Boyhin",
            slug="case-name-cluster",
            citation_count=1,
            scdb_votes_minority=3,
            scdb_votes_majority=6,
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    async def _test_article_count(self, params, expected_count, field_name):
        r = await self.async_client.get("/", params)
        tree = html.fromstring(r.content.decode())
        got = len(tree.xpath("//article"))
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of search results in Frontend with %s "
            "filter applied.\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            "Params were: %s" % (field_name, expected_count, got, params),
        )
        return r

    async def _test_api_results_count(
        self, params, expected_count, field_name
    ):
        """Get the result count in a API query response"""
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v3"}), params
        )
        got = len(r.data["results"])
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of search results in API with %s "
            "filter applied.\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            "Params were: %s" % (field_name, expected_count, got, params),
        )
        return r

    async def test_can_perform_a_regular_text_query(self) -> None:
        # Frontend
        search_params = {"q": "supreme"}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("Honda", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        # Search by court_id
        search_params = {"q": "ca1"}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("case name cluster 3", r.content.decode())

        # Search by court name
        search_params = {"q": "First Circuit"}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("case name cluster 3", r.content.decode())

        # Search by Citation
        search_params = {"q": '"33 state"'}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("docket number 2", r.content.decode())

        # Search by Judge
        search_params = {"q": "David"}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("docket number 2", r.content.decode())

        # Search by caseName
        search_params = {"q": '"Howard v. Honda"'}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("docket number 2", r.content.decode())

        # Search by caseNameFull
        search_params = {"q": "Antonin"}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("docket number 2", r.content.decode())

        # Search by suitNature
        search_params = {"q": "copyright"}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("docket number 2", r.content.decode())

        # Search by attorney
        search_params = {"q": "Lindley W. Barnes"}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("123456", r.content.decode())

        # Search by procedural_history
        search_params = {"q": '"This is a opinion procedural"'}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("123456", r.content.decode())

        # Search by posture
        search_params = {"q": '"This is a opinion posture"'}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("123456", r.content.decode())

        # Search by syllabus
        search_params = {"q": '"This is a opinion  syllabus"'}
        r = await self._test_article_count(search_params, 1, "text_query")
        self.assertIn("123456", r.content.decode())

    async def test_homepage(self) -> None:
        """Is the homepage loaded when no GET parameters are provided?"""
        response = await self.async_client.get(reverse("show_results"))
        self.assertIn(
            'id="homepage"',
            response.content.decode(),
            msg="Did not find the #homepage id when attempting to "
            "load the homepage",
        )

    async def test_fail_gracefully(self) -> None:
        """Do we fail gracefully when an invalid search is created?"""
        response = await self.async_client.get(
            reverse("show_results"), {"filed_after": "-"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "an error",
            response.content.decode(),
            msg="Invalid search did not result in an error.",
        )

    async def test_can_search_with_white_spaces_only(self) -> None:
        """Does everything work when whitespace is in various fields?"""
        search_params = {"q": " ", "judge": " ", "case_name": " "}

        # Frontend
        r = await self._test_article_count(search_params, 4, "white_spaces")
        self.assertIn("Honda", r.content.decode())
        self.assertNotIn("an error", r.content.decode())

    async def test_can_filter_using_the_case_name(self) -> None:
        # Frontend
        search_params = {"q": "*", "case_name": "honda"}
        r = await self._test_article_count(search_params, 1, "case_name")
        self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_court(self) -> None:
        # Frontend
        search_params = {"court": self.court_1.pk}

        r = await self._test_article_count(search_params, 1, "court")
        self.assertIn("case name cluster 3", r.content.decode())

    async def test_can_query_with_an_old_date(self) -> None:
        """Do we have any recurrent issues with old dates and strftime (issue
        220)?"""
        search_params = {"q": "*", "filed_after": "1890"}

        # Frontend
        r = await self._test_article_count(search_params, 4, "filed_after")
        self.assertEqual(200, r.status_code)

    async def test_can_filter_using_filed_range(self) -> None:
        """Does querying by date work?"""
        search_params = {
            "q": "*",
            "filed_after": "1895-06",
            "filed_before": "1896-01",
        }
        # Frontend
        r = await self._test_article_count(search_params, 1, "filed_range")
        self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_a_docket_number(self) -> None:
        """Can we query by docket number?"""
        search_params = {"q": "*", "docket_number": "2"}

        # Frontend
        r = await self._test_article_count(search_params, 1, "docket_number")
        self.assertIn(
            "Honda", r.content.decode(), "Result not found by docket number!"
        )

    async def test_can_filter_by_citation_number(self) -> None:
        """Can we query by citation number?"""
        get_dicts = [{"q": "*", "citation": "33"}, {"q": "citation:33"}]
        for get_dict in get_dicts:
            # Frontend
            r = await self._test_article_count(get_dict, 1, "citation_count")
            self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_neutral_citation(self) -> None:
        """Can we query by neutral citation numbers?"""
        search_params = {"q": "*", "neutral_cite": "22"}
        # Frontend
        r = await self._test_article_count(search_params, 1, "citation_number")
        self.assertIn("Honda", r.content.decode())

    async def test_can_filter_using_judge_name(self) -> None:
        """Can we query by judge name?"""
        search_array = [{"q": "*", "judge": "david"}, {"q": "judge:david"}]
        for search_params in search_array:
            # Frontend
            r = await self._test_article_count(search_params, 1, "judge_name")
            self.assertIn("Honda", r.content.decode())

    async def test_can_filter_by_nature_of_suit(self) -> None:
        """Can we query by nature of suit?"""
        search_params = {"q": 'suitNature:"copyright"'}
        # Frontend
        r = await self._test_article_count(search_params, 1, "suit_nature")
        self.assertIn("Honda", r.content.decode())

    async def test_can_filtering_by_citation_count(self) -> None:
        """Can we find Documents by citation filtering?"""
        search_params = {"q": "*", "cited_lt": 7, "cited_gt": 5}
        # Frontend
        r = await self._test_article_count(search_params, 1, "citation_count")
        self.assertIn(
            "Honda",
            r.content.decode(),
            msg="Did not get case back when filtering by citation count.",
        )

        search_params = {"q": "*", "cited_lt": 100, "cited_gt": 80}
        # Frontend
        r = await self._test_article_count(search_params, 0, "citation_count")
        self.assertIn(
            "had no results",
            r.content.decode(),
            msg="Got case back when filtering by crazy citation count.",
        )

    async def test_faceted_queries(self) -> None:
        """Does querying in a given court return the document? Does querying
        the wrong facets exclude it?
        """
        r = await self.async_client.get(
            reverse("show_results"), {"q": "*", "court_test": "on"}
        )
        self.assertIn("Honda", r.content.decode())

        r = await self.async_client.get(
            reverse("show_results"), {"q": "*", "stat_Errata": "on"}
        )
        self.assertNotIn("Honda", r.content.decode())
        self.assertIn("Debbas", r.content.decode())

    async def test_facet_fields_counts(self) -> None:
        """Confirm that the facet fields contain the correct aggregation
        counts, regardless of the selected status.
        """

        def assert_facet_fields(facet_fields, expected_vals):
            for field in facet_fields:
                field_name = field.name
                if field_name in expected_vals:
                    field_count = field.count
                    self.assertEqual(
                        field_count,
                        expected_vals[field_name],
                        f"Count for {field_name} did not match. Expected: {expected_vals[field_name]}, Found: {field_count}",
                    )

        # Match all query
        r = await self.async_client.get(
            reverse("show_results"), {"q": "*", "stat_Errata": "on"}
        )
        expected_values = {
            "stat_Published": 4,
            "stat_Unpublished": 0,
            "stat_Errata": 1,
            "stat_Separate": 0,
            "stat_In-chambers": 0,
            "stat_Relating-to": 0,
            "stat_Unknown": 0,
        }
        assert_facet_fields(r.context["facet_fields"], expected_values)

        # Filter query
        r = await self.async_client.get(
            reverse("show_results"),
            {"case_name": "Debbas v. Franklin", "stat_Errata": "on"},
        )
        expected_values = {
            "stat_Published": 0,
            "stat_Unpublished": 0,
            "stat_Errata": 1,
            "stat_Separate": 0,
            "stat_In-chambers": 0,
            "stat_Relating-to": 0,
            "stat_Unknown": 0,
        }
        assert_facet_fields(r.context["facet_fields"], expected_values)

        # Text query
        r = await self.async_client.get(
            reverse("show_results"),
            {"q": "some rando syllabus", "stat_Errata": "on"},
        )
        expected_values = {
            "stat_Published": 3,
            "stat_Unpublished": 0,
            "stat_Errata": 1,
            "stat_Separate": 0,
            "stat_In-chambers": 0,
            "stat_Relating-to": 0,
            "stat_Unknown": 0,
        }
        assert_facet_fields(r.context["facet_fields"], expected_values)

        # Text query + Filter
        r = await self.async_client.get(
            reverse("show_results"),
            {
                "q": "some rando syllabus",
                "cited_lt": 9,
                "cited_gt": 5,
                "stat_Errata": "on",
            },
        )
        expected_values = {
            "stat_Published": 2,
            "stat_Unpublished": 0,
            "stat_Errata": 0,
            "stat_Separate": 0,
            "stat_In-chambers": 0,
            "stat_Relating-to": 0,
            "stat_Unknown": 0,
        }
        assert_facet_fields(r.context["facet_fields"], expected_values)

    async def test_citation_ordering_by_citation_count(self) -> None:
        """Can the results be re-ordered by citation count?"""
        search_params = {"q": "*", "order_by": "citeCount desc"}
        most_cited_name = "case name cluster 3"
        less_cited_name = "Howard v. Honda"

        # Frontend
        r = await self._test_article_count(search_params, 4, "citeCount desc")
        self.assertTrue(
            r.content.decode().index(most_cited_name)
            < r.content.decode().index(less_cited_name),
            msg="'%s' should come BEFORE '%s' when ordered by descending "
            "citeCount." % (most_cited_name, less_cited_name),
        )

        search_params = {"q": "*", "order_by": "citeCount asc"}
        # Frontend
        r = await self._test_article_count(search_params, 4, "citeCount asc")
        self.assertTrue(
            r.content.decode().index(most_cited_name)
            > r.content.decode().index(less_cited_name),
            msg="'%s' should come AFTER '%s' when ordered by ascending "
            "citeCount." % (most_cited_name, less_cited_name),
        )

    async def test_random_ordering(self) -> None:
        """Can the results be ordered randomly?

        This test is difficult since we can't check that things actually get
        ordered randomly, but we can at least make sure the query succeeds.
        """
        search_params = {"q": "*", "order_by": "random_123 desc"}
        # Frontend
        r = await self._test_article_count(
            search_params, 4, "order random desc"
        )
        self.assertNotIn("an error", r.content.decode())

    async def test_issue_635_leading_zeros(self) -> None:
        """Do queries with leading zeros work equal to ones without?"""
        search_params = {"docket_number": "005", "stat_Errata": "on"}
        expected = 1
        # Frontend
        await self._test_article_count(
            search_params, expected, "docket_number"
        )

        search_params["docket_number"] = "5"
        # Frontend
        await self._test_article_count(
            search_params, expected, "docket_number"
        )

    async def test_issue_1193_docket_numbers_as_phrase(self) -> None:
        """Are docket numbers searched as a phrase?"""
        # Search for the full docket number. Does it work?
        search_params = {
            "docket_number": "docket number 1 005",
            "stat_Errata": "on",
        }
        # Frontend
        await self._test_article_count(search_params, 1, "docket_number")

        # Twist up the docket numbers. Do we get no results?
        search_params["docket_number"] = "docket 005 number"
        # Frontend
        await self._test_article_count(search_params, 0, "docket_number")

    async def test_issue_1296_abnormal_citation_type_queries(self) -> None:
        """Does search work OK when there are supra, id, or non-opinion
        citations in the query?
        """
        params = (
            {"type": SEARCH_TYPES.OPINION, "q": "42 U.S.C. § ·1383a(a)(3)(A)"},
            {"type": SEARCH_TYPES.OPINION, "q": "supra, at 22"},
        )
        for param in params:
            r = await self.async_client.get(reverse("show_results"), param)
            self.assertEqual(
                r.status_code,
                HTTP_200_OK,
                msg=f"Didn't get good status code with params: {param}",
            )

    async def test_can_render_unicode_o_character(self) -> None:
        """Does unicode HTML unicode is properly rendered in search results?"""
        r = await self.async_client.get(
            reverse("show_results"), {"q": "*", "case_name": "Washington"}
        )
        self.assertIn("Code, §", r.content.decode())

    async def test_can_use_docket_number_proximity(self) -> None:
        """Test docket_number proximity query, so that docket numbers like
        1:21-cv-1234 can be matched by queries like: 21-1234
        """

        # Query 21-1234, return results for 1:21-bk-1234
        search_params = {"type": SEARCH_TYPES.OPINION, "q": "21-1234"}
        # Frontend
        r = await self._test_article_count(
            search_params, 1, "docket number proximity"
        )
        self.assertIn("Washington", r.content.decode())

        # Query 1:21-cv-1234
        search_params["q"] = "1:21-cv-1234"
        # Frontend
        r = await self._test_article_count(
            search_params, 1, "docket number proximity"
        )
        self.assertIn("Washington", r.content.decode())

        # docket_number box filter: 21-1234, return results for 1:21-bk-1234
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "docket_number": "21-1234",
        }
        # Frontend
        r = await self._test_article_count(
            search_params, 1, "docket number box"
        )
        self.assertIn("Washington", r.content.decode())

    async def test_can_filter_with_docket_number_suffixes(self) -> None:
        """Test docket_number with suffixes can be found."""

        # Indexed: 1:21-cv-1234 -> Search: 1:21-cv-1234-ABC
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"1:21-cv-1234-ABC",
        }
        # Frontend
        r = await self._test_article_count(
            search_params, 1, "docket number box"
        )
        self.assertIn("Washington", r.content.decode())

        # Other kind of formats can still be searched -> 123456
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "123456",
        }
        # Frontend
        r = await self._test_article_count(
            search_params, 1, "docket number box"
        )
        self.assertIn("Lorem", r.content.decode())

    async def test_can_use_intersection_in_query(self) -> None:
        """Does AND queries work"""
        search_params = {"q": "Howard AND Honda"}
        r = await self._test_article_count(
            search_params, 1, "intersection query"
        )
        self.assertIn("Howard", r.content.decode())
        self.assertIn("Honda", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    async def test_can_use_union_query(self) -> None:
        """Does OR queries work"""
        search_params = {"q": "Howard OR Lissner"}
        r = await self._test_article_count(search_params, 2, "union query")
        self.assertIn("Howard", r.content.decode())
        self.assertIn("Lissner", r.content.decode())
        self.assertIn("2 Opinions", r.content.decode())

    async def test_can_use_negation_in_queries(self) -> None:
        """Does negation query work"""
        search_params = {"q": "Howard"}
        r = await self._test_article_count(search_params, 1, "simple query")
        self.assertIn("Howard", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        search_params["q"] = "Howard NOT Honda"
        r = await self._test_article_count(search_params, 0, "negation query")
        self.assertIn("had no results", r.content.decode())

        search_params["q"] = "Howard !Honda"
        r = await self._test_article_count(search_params, 0, "negation query")
        self.assertIn("had no results", r.content.decode())

        search_params["q"] = "Howard -Honda"
        r = await self._test_article_count(search_params, 0, "negation query")
        self.assertIn("had no results", r.content.decode())

    async def test_can_use_phrases_to_query(self) -> None:
        """Can we query by phrase"""
        search_params = {"q": '"Harvey Howard v. Antonin Honda"'}
        r = await self._test_article_count(search_params, 1, "phrases query")
        self.assertIn("Harvey Howard", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        search_params["q"] = '"Antonin Honda v. Harvey Howard"'
        r = await self._test_article_count(search_params, 0, "phrases query")
        self.assertIn("had no results", r.content.decode())

    async def test_can_use_grouped_and_sub_queries(self) -> None:
        """Does grouped and sub queries work"""
        search_params = {"q": "(Lissner OR Honda) AND Howard"}
        r = await self._test_article_count(search_params, 1, "grouped query")
        self.assertIn("Howard", r.content.decode())
        self.assertIn("Honda", r.content.decode())
        self.assertIn("Lissner", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    async def test_query_fielded(self) -> None:
        """Does fielded queries work"""
        search_params = {"q": f'status:"published"'}
        r = await self._test_article_count(search_params, 4, "status")
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("4 Opinions", r.content.decode())

        search_params = {"q": f'status:"errata"', "stat_Errata": "on"}
        r = await self._test_article_count(search_params, 1, "status")
        self.assertIn("docket number 1 005", r.content.decode())

    async def test_query_by_type(self) -> None:
        """Does fielded queries work"""
        search_params = {"q": f"type:{o_type_index_map.get(Opinion.REMITTUR)}"}
        r = await self._test_article_count(search_params, 1, "type")
        self.assertIn("1:21-cv-1234", r.content.decode())

    async def test_a_wildcard_query(self) -> None:
        """Does a wildcard query work"""
        search_params = {"q": "Was*"}
        r = await self._test_article_count(search_params, 1, "wildcard query")
        self.assertIn("Strickland", r.content.decode())
        self.assertIn("Washington", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        search_params["q"] = "?ash*"
        r = await self._test_article_count(search_params, 1, "wildcard query")
        self.assertIn("21-cv-1234", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    async def test_a_fuzzy_query(self) -> None:
        """Does a fuzzy query work"""
        search_params = {"q": "ond~"}
        r = await self._test_article_count(search_params, 4, "fuzzy query")
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("4 Opinions", r.content.decode())

    async def test_proximity_query(self) -> None:
        """Does a proximity query work"""
        search_params = {"q": '"Testing Court"~3'}
        r = await self._test_article_count(search_params, 1, "proximity query")
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    async def test_can_filter_using_citation_range(self) -> None:
        """Does a range query work"""
        search_params = {"q": "citation:([22 TO 33])"}
        r = await self._test_article_count(
            search_params, 2, "citation range query"
        )
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("2 Opinions", r.content.decode())

    async def test_cites_query(self) -> None:
        """Does a cites:(*) query work?"""

        search_params = {"q": f"cites:({self.opinion_1.pk})"}
        r = await self._test_article_count(search_params, 1, "cites:() query")

        # Confirm "cite" cluster legend is within the results' header.
        h2_element = html.fromstring(r.content.decode()).xpath(
            '//h2[@id="result-count"]'
        )
        h2_content = html.tostring(
            h2_element[0], method="text", encoding="unicode"
        )
        self.assertIn("cite", h2_content)
        self.assertIn("Debbas", h2_content)
        self.assertIn("Franklin", h2_content)
        self.assertIn("1 reference to this case", r.content.decode())

    async def test_can_filter_using_date_ranges(self) -> None:
        """Does a date query work"""
        search_params = {
            "q": "dateFiled:[2015-01-01T00:00:00Z TO 2015-12-31T00:00:00Z]"
        }
        r = await self._test_article_count(
            search_params, 1, "citation range query"
        )
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        search_params["q"] = (
            "dateFiled:[1895-01-01T00:00:00Z TO 2015-12-31T00:00:00Z]"
        )
        r = await self._test_article_count(
            search_params, 2, "citation range query"
        )
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("2 Opinions", r.content.decode())

    async def test_results_highlights(self) -> None:
        """Confirm highlights are shown properly"""

        # Highlight case name.
        params = {"q": "'Howard v. Honda'"}

        r = await self._test_article_count(params, 1, "highlights case name")
        self.assertIn("<mark>Howard v. Honda</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Howard v. Honda</mark>"), 1
        )

        # Highlight Citation. Multiple HL fields are properly merged.
        params = {"q": "citation:(22 AL) OR citation:(33 state)"}
        r = await self._test_article_count(params, 1, "highlights case name")
        self.assertIn("<mark>22</mark>", r.content.decode())
        self.assertIn("<mark>AL</mark>", r.content.decode())
        self.assertIn("<mark>33</mark>", r.content.decode())
        self.assertIn("<mark>state</mark>", r.content.decode())

        params = {"q": '"22 AL 339"'}
        r = await self._test_article_count(params, 1, "highlights case name")
        self.assertIn("<mark>22 AL 339</mark>", r.content.decode())

        params = {"q": '22 AL OR "Yeates 1"'}
        r = await self._test_article_count(params, 1, "highlights case name")
        self.assertIn("<mark>22</mark>", r.content.decode())
        self.assertIn("<mark>AL</mark>", r.content.decode())
        self.assertIn("<mark>Yeates 1</mark>", r.content.decode())

        # Highlight docketNumber.
        params = {"q": 'docketNumber:"docket number 2"'}
        r = await self._test_article_count(params, 1, "highlights case name")
        self.assertIn("<mark>docket number 2</mark>", r.content.decode())

        # Highlight suitNature.
        params = {"q": '"copyright"'}
        r = await self._test_article_count(params, 1, "highlights case name")
        self.assertIn("<mark>copyright</mark>", r.content.decode())

        # Highlight plain text.
        params = {"q": "word queries"}
        r = await self._test_article_count(params, 2, "highlights plain_text")
        self.assertIn("<mark>word</mark>", r.content.decode())
        self.assertIn("<mark>queries</mark>", r.content.decode())


class RelatedSearchTest(
    ESIndexTestCase, CourtTestCase, PeopleTestCase, SearchTestCase, TestCase
):
    def setUp(self) -> None:
        # Do this in two steps to avoid triggering profile creation signal
        admin = UserProfileWithParentsFactory.create(
            user__username="admin",
            user__password=make_password("password"),
        )
        admin.user.is_superuser = True
        admin.user.is_staff = True
        admin.user.save()

        super(RelatedSearchTest, self).setUp()
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def get_article_count(self, r):
        """Get the article count in a query response"""
        return len(html.fromstring(r.content.decode()).xpath("//article"))

    def test_more_like_this_opinion(self) -> None:
        """Does the MoreLikeThis query return the correct number and order of
        articles."""
        seed_pk = self.opinion_1.pk  # Paul Debbas v. Franklin
        expected_article_count = 3
        expected_first_pk = self.opinion_cluster_2.pk  # Howard v. Honda
        expected_second_pk = self.opinion_cluster_3.pk  # case name cluster 3

        params = {
            "type": "o",
            "q": "related:%i" % seed_pk,
        }

        # enable all status filters (otherwise results do not match detail page)
        params.update(
            {f"stat_{s}": "on" for s, v in PRECEDENTIAL_STATUS.NAMES}
        )

        r = self.client.get(reverse("show_results"), params)
        self.assertEqual(r.status_code, HTTP_200_OK)

        self.assertEqual(expected_article_count, self.get_article_count(r))
        self.assertTrue(
            r.content.decode().index("/opinion/%i/" % expected_first_pk)
            < r.content.decode().index("/opinion/%i/" % expected_second_pk),
            msg="'Howard v. Honda' should come AFTER 'case name cluster 3'.",
        )
        # Confirm "related to" cluster legend is within the results' header.
        h2_element = html.fromstring(r.content.decode()).xpath(
            '//h2[@id="result-count"]'
        )
        h2_content = html.tostring(
            h2_element[0], method="text", encoding="unicode"
        )
        self.assertIn("related to", h2_content)
        self.assertIn("Debbas", h2_content)
        self.assertIn("Franklin", h2_content)

    async def test_more_like_this_opinion_detail_detail(self) -> None:
        """MoreLikeThis query on opinion detail page with status filter"""
        seed_pk = self.opinion_cluster_3.pk  # case name cluster 3

        # Login as staff user (related items are by default disabled for guests)
        self.assertTrue(
            await sync_to_async(self.async_client.login)(
                username="admin", password="password"
            )
        )

        r = await self.async_client.get("/opinion/%i/asdf/" % seed_pk)
        self.assertEqual(r.status_code, 200)

        tree = html.fromstring(r.content.decode())

        recomendations_actual = [
            (a.get("href"), a.text_content().strip())
            for a in tree.xpath("//*[@id='recommendations']/ul/li/a")
        ]

        recommendations_expected = [
            (
                f"/opinion/{self.opinion_cluster_2.pk}/{self.opinion_cluster_2.slug}/?",
                "Howard v. Honda",
            )
        ]

        # Test if related opinion exist in expected order
        self.assertEqual(
            recommendations_expected,
            recomendations_actual,
            msg="Unexpected opinion recommendations.",
        )
        await sync_to_async(self.async_client.logout)()

    @override_settings(RELATED_FILTER_BY_STATUS=None)
    async def test_more_like_this_opinion_detail_no_filter(self) -> None:
        """MoreLikeThis query on opinion detail page (without filter)"""
        seed_pk = self.opinion_cluster_1.pk  # Paul Debbas v. Franklin

        # Login as staff user (related items are by default disabled for guests)
        self.assertTrue(
            await sync_to_async(self.async_client.login)(
                username="admin", password="password"
            )
        )

        r = await self.async_client.get("/opinion/%i/asdf/" % seed_pk)
        self.assertEqual(r.status_code, 200)

        tree = html.fromstring(r.content.decode())

        recomendations_actual = [
            (a.get("href"), a.text_content().strip())
            for a in tree.xpath("//*[@id='recommendations']/ul/li/a")
        ]

        recommendations_expected = [
            (
                f"/opinion/{self.opinion_cluster_2.pk}/{self.opinion_cluster_2.slug}/?",
                "Howard v. Honda",
            ),
            (
                f"/opinion/{self.opinion_cluster_3.pk}/{self.opinion_cluster_3.slug}/?",
                "case name cluster 3",
            ),
        ]

        # Test if related opinion exist in expected order
        self.assertEqual(
            recommendations_expected,
            recomendations_actual,
            msg="Unexpected opinion recommendations.",
        )

        await sync_to_async(self.async_client.logout)()


class GroupedSearchTest(EmptySolrTestCase):
    @classmethod
    def setUpTestData(cls):
        court = CourtFactory(id="ca1", jurisdiction="F")

        docket = DocketFactory.create(
            date_reargument_denied=datetime.date(2015, 8, 15),
            date_reargued=datetime.date(2015, 8, 15),
            court_id=court.pk,
            case_name_full="Voutila v. Bonvini",
            date_argued=datetime.date(2015, 8, 15),
            case_name="case name docket 10",
            case_name_short="short name for Voutila v. Bonvini",
            docket_number="1337-np",
            slug="case-name",
            pacer_case_id="666666",
            blocked=False,
            source=0,
            date_blocked=None,
        )

        grouped_cluster = OpinionClusterFactory.create(
            case_name_full="Reference to Voutila v. Bonvini",
            case_name_short="Case name in short for Voutila v. Bonvini",
            syllabus="some rando syllabus",
            date_filed=datetime.date(2015, 12, 20),
            procedural_history="some rando history",
            source="C",
            judges="",
            case_name="Voutila v. Bonvini",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=1,
            posture="",
            scdb_id="",
            nature_of_suit="",
            docket=docket,
        )

        OpinionFactory.create(
            extracted_by_ocr=False,
            author=None,
            plain_text="This is a lead opinion too.",
            cluster=grouped_cluster,
            local_path="txt/2015/12/28/opinion_text.txt",
            per_curiam=False,
            type="020lead",
        )

        OpinionFactory.create(
            extracted_by_ocr=False,
            author=None,
            plain_text="This is a combined opinion.",
            cluster=grouped_cluster,
            local_path="doc/2005/05/04/state_of_indiana_v._charles_barker.doc",
            per_curiam=False,
            type=Opinion.COMBINED,
        )
        super().setUpTestData()

    def setUp(self) -> None:
        # Set up some handy variables
        super(GroupedSearchTest, self).setUp()
        args = [
            "--type",
            "search.Opinion",
            "--solr-url",
            f"{settings.SOLR_HOST}/solr/{self.core_name_opinion}",
            "--update",
            "--everything",
            "--do-commit",
            "--noinput",
        ]
        call_command("cl_update_index", *args)
        self.factory = AsyncRequestFactory()

    def test_grouped_queries(self) -> None:
        """When we have a cluster with multiple opinions, do results get
        grouped?
        """
        request = self.factory.get(reverse("show_results"), {"q": "Voutila"})
        response = do_search(request.GET.copy())
        result_count = response["results"].object_list.result.numFound
        num_expected = 1
        self.assertEqual(
            result_count,
            num_expected,
            msg="Found %s items, but should have found %s if the items were "
            "grouped properly." % (result_count, num_expected),
        )


class IndexOpinionDocumentsCommandTest(
    ESIndexTestCase, CourtTestCase, PeopleTestCase, SearchTestCase, TestCase
):
    """cl_index_parent_and_child_docs command tests for Elasticsearch"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.OpinionCluster")
        super().setUpTestData()
        cls.delete_index("search.OpinionCluster")
        cls.create_index("search.OpinionCluster")

    def setUp(self) -> None:
        self.r = make_redis_interface("CACHE")
        keys = self.r.keys(compose_redis_key(SEARCH_TYPES.RECAP))
        if keys:
            self.r.delete(*keys)

    def test_cl_index_parent_and_child_docs_command(self):
        """Confirm the command can properly index Dockets and their
        RECAPDocuments into the ES."""

        s = OpinionClusterDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)
        # Call cl_index_parent_and_child_docs command.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion_cluster"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of Clusters returned."
        )

        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion"))
        self.assertEqual(
            s.count(), 6, msg="Wrong number of Opinions returned."
        )

        # RECAPDocuments are indexed.
        opinions_pks = [
            self.opinion_1.pk,
            self.opinion_2.pk,
            self.opinion_3.pk,
        ]
        for pk in opinions_pks:
            self.assertTrue(OpinionDocument.exists(id=ES_CHILD_ID(pk).OPINION))


class EsOpinionsIndexingTest(
    CountESTasksTestCase, ESIndexTestCase, TransactionTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rebuild_index("search.OpinionCluster")

    def setUp(self):
        self.court_1 = CourtFactory(
            id="ca1",
            full_name="First Circuit",
            jurisdiction="F",
            citation_string="1st Cir.",
            url="http://www.ca1.uscourts.gov/",
        )
        self.court_2 = CourtFactory(
            id="test",
            full_name="Testing Supreme Court",
            jurisdiction="F",
            citation_string="Test",
            url="https://www.courtlistener.com/",
        )
        self.docket = DocketFactory.create(
            date_reargument_denied=datetime.date(2015, 8, 15),
            court_id=self.court_2.pk,
            case_name_full="case name full docket 1",
            date_argued=datetime.date(2015, 8, 16),
            case_name="case name docket 1",
            case_name_short="case name short docket 1",
            docket_number="docket number 1 005",
            slug="case-name",
            pacer_case_id="666666",
            blocked=False,
            source=0,
        )
        self.person = PersonFactory.create(
            gender="f",
            name_first="Judith",
            name_last="Sheindlin",
            date_dob=datetime.date(1942, 10, 21),
            date_dod=datetime.date(2020, 11, 25),
            date_granularity_dob="%Y-%m-%d",
            date_granularity_dod="%Y-%m-%d",
            name_middle="Susan",
            dob_city="Brookyln",
            dob_state="NY",
        )
        self.person_2 = PersonFactory.create()
        super().setUp()

    def test_remove_parent_child_objects_from_index(self) -> None:
        """Confirm join child objects are removed from the index when the
        parent objects is deleted.
        """
        cluster = OpinionClusterFactory.create(
            case_name_full="Paul Debbas v. Franklin",
            case_name_short="Debbas",
            syllabus="some rando syllabus",
            date_filed=datetime.date(2015, 8, 14),
            procedural_history="some rando history",
            source="C",
            case_name="Debbas v. Franklin",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            precedential_status="Errata",
            citation_count=4,
            docket=self.docket,
        )
        opinion_1 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=self.person,
            plain_text="my plain text",
            cluster=cluster,
            local_path="test/search/opinion_doc1.doc",
            per_curiam=False,
            type=Opinion.COMBINED,
        )

        cluster_pk = cluster.pk
        opinion_pk = opinion_1.pk
        # Cluster instance is indexed.
        self.assertTrue(OpinionClusterDocument.exists(id=cluster_pk))
        # Opinion instance is indexed.
        self.assertTrue(
            OpinionDocument.exists(id=ES_CHILD_ID(opinion_pk).OPINION)
        )

        # Delete Cluster instance; it should be removed from the index along
        # with its child documents.
        cluster.delete()

        # Cluster document should be removed.
        self.assertFalse(OpinionClusterDocument.exists(id=cluster_pk))
        # Opinion document is removed.
        self.assertFalse(
            OpinionDocument.exists(id=ES_CHILD_ID(opinion_pk).OPINION)
        )

    def test_remove_nested_objects_from_index(self) -> None:
        """Confirm that child objects are removed from the index when they are
        deleted independently of their parent object
        """
        cluster = OpinionClusterFactory.create(
            case_name_full="Paul Debbas v. Franklin",
            case_name_short="Debbas",
            syllabus="some rando syllabus",
            date_filed=datetime.date(2015, 8, 14),
            procedural_history="some rando history",
            source="C",
            case_name="Debbas v. Franklin",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            precedential_status="Errata",
            citation_count=4,
            docket=self.docket,
        )
        opinion_1 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=self.person,
            plain_text="my plain text",
            cluster=cluster,
            local_path="test/search/opinion_doc1.doc",
            per_curiam=False,
            type=Opinion.COMBINED,
        )

        cluster_pk = cluster.pk
        opinion_pk = opinion_1.pk

        # Delete pos_1 and education, keep the parent person instance.
        opinion_1.delete()

        # Opinion cluster instance still exists.
        self.assertTrue(OpinionClusterDocument.exists(id=cluster_pk))

        # Opinion object is removed
        self.assertFalse(
            OpinionDocument.exists(id=ES_CHILD_ID(opinion_pk).OPINION)
        )
        cluster.delete()

    def test_child_document_update_properly(self) -> None:
        """Confirm that child fields are properly update when changing DB records"""

        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            opinion_cluster = OpinionClusterFactory.create(
                case_name_full="Paul Debbas v. Franklin",
                case_name_short="Debbas",
                syllabus="some rando syllabus",
                date_filed=datetime.date(2015, 8, 14),
                procedural_history="some rando history",
                source="C",
                case_name="Debbas v. Franklin",
                attorneys="a bunch of crooks!",
                slug="case-name-cluster",
                precedential_status="Errata",
                citation_count=4,
                docket=self.docket,
            )
            opinion = OpinionFactory.create(
                extracted_by_ocr=False,
                author=self.person,
                plain_text="my plain text secret word for queries",
                cluster=opinion_cluster,
                local_path="test/search/opinion_doc.doc",
                per_curiam=False,
                type="020lead",
            )

        # Two es_save_document task should be called on creation, one for
        # opinion and one for opinion_cluster
        self.reset_and_assert_task_count(expected=2)

        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            # Update the author field in the opinion record.
            opinion.author = self.person_2
            opinion.save()
        # One update_es_document task should be called on tracked field update.
        self.reset_and_assert_task_count(expected=1)

        # Update an opinion untracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            opinion.joined_by_str = "Joined Lorem"
            opinion.save()
        # update_es_document task shouldn't be called on save() for untracked
        # fields
        self.reset_and_assert_task_count(expected=0)

        es_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(es_doc.author_id, self.person_2.pk)

        # Update the type field in the opinion record.
        opinion.type = Opinion.COMBINED
        opinion.save()

        es_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(es_doc.type, o_type_index_map.get(Opinion.COMBINED))
        self.assertEqual(es_doc.type_text, "Combined Opinion")

        # Update the per_curiam field in the opinion record.
        opinion.per_curiam = True
        opinion.save()

        es_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(es_doc.per_curiam, True)

        # Update the text field in the opinion record.
        opinion.plain_text = "This is a test"
        opinion.save()

        es_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(es_doc.text, "This is a test")

        # Update cites field in the opinion record.
        person_2 = PersonFactory.create(
            gender="f",
            name_first="Judith",
            name_last="Sheindlin",
            date_dob=datetime.date(1942, 10, 21),
            date_dod=datetime.date(2020, 11, 25),
            date_granularity_dob="%Y-%m-%d",
            date_granularity_dod="%Y-%m-%d",
            name_middle="Susan",
            dob_city="Brookyln",
            dob_state="NY",
        )
        opinion_2 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=person_2,
            plain_text="my plain text secret word for queries",
            cluster=opinion_cluster,
            local_path="test/search/opinion_wpd.wpd",
            per_curiam=False,
            type=Opinion.COMBINED,
        )
        opinion_cluster_2 = OpinionClusterFactory.create(
            precedential_status="Errata",
            citation_count=5,
            docket=self.docket,
        )

        opinion_3 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=person_2,
            plain_text="my plain text secret word for queries",
            cluster=opinion_cluster_2,
            local_path="test/search/opinion_wpd.wpd",
            per_curiam=False,
            type=Opinion.COMBINED,
        )

        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            # Add OpinionsCited using save() as in add_manual_citations command
            cite = OpinionsCited(
                citing_opinion_id=opinion.pk,
                cited_opinion_id=opinion_2.pk,
            )
            cite.save()
        # One update_es_document task should be called tracked field update.
        self.reset_and_assert_task_count(expected=1)
        es_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(es_doc.cites, [opinion_2.pk])

        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            # Add OpinionsCited using bulk_create as in store_opinion_citations_and_update_parentheticals
            cite_2 = OpinionsCited(
                citing_opinion_id=opinion.pk,
                cited_opinion_id=opinion_3.pk,
            )
            OpinionsCited.objects.bulk_create([cite_2])

            # Increase the citation_count for multiple cluster using update()
            opinion_clusters_to_update = OpinionCluster.objects.filter(
                pk__in=[opinion_cluster.pk, opinion_cluster_2.pk]
            )
            opinion_clusters_to_update.update(
                citation_count=F("citation_count") + 1
            )
            cluster_ids_to_update = list(
                opinion_clusters_to_update.values_list("id", flat=True)
            )

        # No update_es_document task should be called on bulk creation or update
        self.reset_and_assert_task_count(expected=0)

        # Update changes in ES using index_related_cites_fields
        index_related_cites_fields.delay(
            OpinionsCited.__name__, opinion.pk, cluster_ids_to_update
        )

        # Confirm the cites and citeCount fields were properly updated in the
        # different documents.
        es_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        for cite in opinion.opinions_cited.all():
            self.assertIn(cite.pk, es_doc.cites)
        self.assertEqual(es_doc.citeCount, 5)

        es_doc_2 = OpinionDocument.get(ES_CHILD_ID(opinion_2.pk).OPINION)
        self.assertEqual(es_doc_2.citeCount, 5)
        es_doc_3 = OpinionDocument.get(ES_CHILD_ID(opinion_3.pk).OPINION)
        self.assertEqual(es_doc_3.citeCount, 6)

        cluster_1 = OpinionClusterDocument.get(opinion_cluster.pk)
        self.assertEqual(cluster_1.citeCount, 5)
        cluster_2 = OpinionClusterDocument.get(opinion_cluster_2.pk)
        self.assertEqual(cluster_2.citeCount, 6)

        # Update joined_by field in the opinion record.
        person_3 = PersonFactory.create(
            gender="f",
            name_first="Sheindlin",
            name_last="Judith",
            date_dob=datetime.date(1945, 11, 20),
            date_granularity_dob="%Y-%m-%d",
            name_middle="Olivia",
            dob_city="Queens",
            dob_state="NY",
        )
        opinion.joined_by.add(person_3)

        es_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        for judge in opinion.joined_by.all():
            self.assertIn(judge.pk, es_doc.joined_by_ids)

        opinion.delete()

    def test_parent_document_update_fields_properly(self) -> None:
        """Confirm that parent fields are properly update when changing DB records"""
        docket = DocketFactory(
            court_id=self.court_2.pk,
        )
        opinion_cluster = OpinionClusterFactory.create(
            case_name_full="Paul test v. Franklin",
            case_name_short="Debbas",
            syllabus="some rando syllabus",
            date_filed=datetime.date(2015, 8, 14),
            procedural_history="some rando history",
            source="C",
            case_name="Debbas v. Franklin",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            precedential_status="Errata",
            citation_count=4,
            docket=docket,
        )

        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            # Update the court field in the docket record.
            docket.court = self.court_1
            docket.save()
        # update_es_document task should be called 1 on tracked fields update
        self.reset_and_assert_task_count(expected=1)

        es_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        self.assertEqual(es_doc.court_exact, "ca1")

        # Update a opinion_cluster untracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            opinion_cluster.other_dates = "January 12"
            opinion_cluster.save()
        # update_es_document task shouldn't be called on save() for untracked
        # fields
        self.reset_and_assert_task_count(expected=0)

        # Update the absolute_url field in the cluster record.
        opinion_cluster.case_name = "Debbas v. test"
        opinion_cluster.save()

        es_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        self.assertEqual(
            es_doc.absolute_url,
            f"/opinion/{opinion_cluster.pk}/debbas-v-test/",
        )

        # Add a new non participating judge to the cluster record.
        person_3 = PersonFactory.create(
            gender="f",
            name_first="Sheindlin",
            name_last="Judith",
            date_dob=datetime.date(1945, 11, 20),
            date_granularity_dob="%Y-%m-%d",
            name_middle="Olivia",
            dob_city="Queens",
            dob_state="NY",
        )
        opinion_cluster.non_participating_judges.add(person_3)

        es_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        self.assertIn(person_3.pk, es_doc.non_participating_judge_ids)

        # Update the source field in the cluster record.
        opinion_cluster.source = "ZLCR"
        opinion_cluster.save()

        es_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        self.assertEqual(es_doc.source, "ZLCR")

        docket.delete()
        opinion_cluster.delete()

    def test_update_shared_fields_related_documents(self) -> None:
        """Confirm that related document are properly update using bulk approach"""
        docket = DocketFactory(
            court_id=self.court_2.pk,
        )
        opinion_cluster = OpinionClusterFactory.create(
            case_name_full="Paul test v. Franklin",
            case_name_short="Debbas",
            syllabus="some rando syllabus",
            date_filed=datetime.date(2015, 8, 14),
            procedural_history="some rando history",
            source="C",
            case_name="Debbas v. Franklin",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            precedential_status="Errata",
            citation_count=4,
            docket=docket,
        )
        opinion = OpinionFactory.create(
            extracted_by_ocr=False,
            author=self.person,
            plain_text="my plain text secret word for queries",
            cluster=opinion_cluster,
            local_path="test/search/opinion_doc.doc",
            per_curiam=False,
            type="020lead",
        )

        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            # update docket number in parent document
            docket.docket_number = "005"
            docket.save()

        # 2 update_es_document task should be called on tracked field update, one
        # for DocketDocument and one for OpinionClusterDocument.
        self.reset_and_assert_task_count(expected=2)
        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.docketNumber, "005")
        self.assertEqual(opinion_doc.docketNumber, "005")

        with mock.patch(
            "cl.lib.es_signal_processor.update_children_docs_by_query.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_children_docs_by_query, *args, **kwargs
            ),
        ):
            # update docket number in parent document
            docket.docket_number = "006"
            docket.save()

        # 1 update_children_docs_by_query task should be called on tracked
        # field update.
        self.reset_and_assert_task_count(expected=1)
        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.docketNumber, "006")
        self.assertEqual(opinion_doc.docketNumber, "006")

        # update the case name in the opinion cluster record
        opinion_cluster.case_name = "Debbas v. Franklin2"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.caseName, "Debbas v. Franklin2")
        self.assertEqual(opinion_doc.caseName, "Debbas v. Franklin2")

        opinion_cluster.case_name = ""
        opinion_cluster.case_name_full = "Franklin v. Debbas"
        opinion_cluster.case_name_short = "Franklin"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.caseName, "Franklin v. Debbas")
        self.assertEqual(cluster_doc.caseNameFull, "Franklin v. Debbas")
        self.assertEqual(opinion_doc.caseName, "Franklin v. Debbas")
        self.assertEqual(opinion_doc.caseNameFull, "Franklin v. Debbas")

        opinion_cluster.case_name_full = ""
        opinion_cluster.case_name_short = "Franklin50"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.caseName, "Franklin50")
        self.assertEqual(opinion_doc.caseName, "Franklin50")

        # update the attorneys field in the cluster record
        opinion_cluster.judges = "first judge, second judge"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.judge, "first judge, second judge")
        self.assertEqual(opinion_doc.judge, "first judge, second judge")

        # update the attorneys field in the cluster record
        opinion_cluster.attorneys = "first attorney, second attorney"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(
            cluster_doc.attorney, "first attorney, second attorney"
        )
        self.assertEqual(
            opinion_doc.attorney, "first attorney, second attorney"
        )

        # update the nature_of_suit field in the cluster record
        opinion_cluster.nature_of_suit = "test nature"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.suitNature, "test nature")
        self.assertEqual(opinion_doc.suitNature, "test nature")

        # update the precedential_status field in the cluster record
        opinion_cluster.precedential_status = "Separate"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.status, "Separate")
        self.assertEqual(opinion_doc.status, "Separate")

        # update the procedural_history field in the cluster record
        opinion_cluster.procedural_history = "random history"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.procedural_history, "random history")
        self.assertEqual(opinion_doc.procedural_history, "random history")

        # update the posture in the opinion cluster record
        opinion_cluster.posture = "random procedural posture"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.posture, "random procedural posture")
        self.assertEqual(opinion_doc.posture, "random procedural posture")

        # update the syllabus in the opinion cluster record
        opinion_cluster.syllabus = "random text for test"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.syllabus, "random text for test")
        self.assertEqual(opinion_doc.syllabus, "random text for test")

        # Update the scdb_id field in the cluster record.
        opinion_cluster.scdb_id = "test"
        opinion_cluster.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.scdb_id, "test")
        self.assertEqual(opinion_doc.scdb_id, "test")

        # Add a new judge to the cluster record.
        opinion_cluster.panel.add(self.person)

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertIn(self.person.pk, cluster_doc.panel_ids)
        self.assertIn(self.person.pk, opinion_doc.panel_ids)

        # Add a new opinion to the cluster record.
        opinion_1 = OpinionFactory.create(
            extracted_by_ocr=False,
            plain_text="my plain text secret word for queries",
            cluster=opinion_cluster,
            type="020lead",
        )

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertIn(opinion_1.pk, cluster_doc.sibling_ids)
        self.assertIn(opinion_1.pk, opinion_doc.sibling_ids)
        self.assertIn(opinion.pk, opinion_doc.sibling_ids)
        opinion_1_doc = OpinionDocument.get(ES_CHILD_ID(opinion_1.pk).OPINION)
        self.assertIn(opinion_1.pk, opinion_1_doc.sibling_ids)
        self.assertIn(opinion.pk, opinion_1_doc.sibling_ids)

        opinion_2 = OpinionFactory.create(
            extracted_by_ocr=False,
            plain_text="my plain text secret word for queries",
            cluster=opinion_cluster,
            type=Opinion.COMBINED,
        )
        opinion_2.save()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertIn(opinion_2.pk, cluster_doc.sibling_ids)
        self.assertIn(opinion_2.pk, opinion_doc.sibling_ids)

        # Add lexis citation to the cluster
        lexis_citation = CitationWithParentsFactory.create(
            volume=10,
            reporter="Yeates",
            page="4",
            type=6,
            cluster=opinion_cluster,
        )

        lexis_citation_str = str(lexis_citation)
        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.lexisCite, lexis_citation_str)
        self.assertEqual(opinion_doc.lexisCite, lexis_citation_str)

        # Remove lexis citation from the db
        lexis_citation.delete()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertNotEqual(cluster_doc.lexisCite, lexis_citation_str)
        self.assertNotEqual(opinion_doc.lexisCite, lexis_citation_str)

        # Add neutral citation to the cluster
        neutral_citation = CitationWithParentsFactory.create(
            volume=16,
            reporter="Yeates",
            page="58",
            type=8,
            cluster=opinion_cluster,
        )

        neutral_citation_str = str(neutral_citation)
        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.neutralCite, neutral_citation_str)
        self.assertEqual(opinion_doc.neutralCite, neutral_citation_str)

        # Remove neutral citation from the db
        neutral_citation.delete()

        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertNotEqual(cluster_doc.neutralCite, neutral_citation_str)
        self.assertNotEqual(opinion_doc.neutralCite, neutral_citation_str)

        # Update the cite_count field in the cluster record.
        opinion_clusters_to_update = OpinionCluster.objects.filter(
            pk=opinion_cluster.pk
        )
        opinion_clusters_to_update.update(
            citation_count=F("citation_count") + 1
        )
        cluster_ids_to_update = list(
            opinion_clusters_to_update.values_list("id", flat=True)
        )

        index_related_cites_fields.delay(
            OpinionsCited.__name__, opinion.pk, cluster_ids_to_update
        )
        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.citeCount, 5)
        self.assertEqual(opinion_doc.citeCount, 5)

        # Confirm a Opinion is indexed if it doesn't exist in the
        # index on a tracked field update.
        # Clean the OpinionsCluster index.
        self.delete_index("search.OpinionCluster")
        self.create_index("search.OpinionCluster")

        # Index OpinionCluster
        opinion_cluster.citation_count = 5
        opinion_cluster.save()

        self.assertFalse(
            OpinionClusterDocument.exists(id=ES_CHILD_ID(opinion.pk).OPINION)
        )
        # Opinion Document creation on update.
        opinion.plain_text = "Lorem ipsum dolor."
        opinion.save()

        opinion_doc = OpinionClusterDocument.get(
            id=ES_CHILD_ID(opinion.pk).OPINION
        )
        self.assertEqual(opinion_doc.text, "Lorem ipsum dolor.")
        self.assertEqual(
            opinion_doc.cluster_child["parent"], opinion_cluster.pk
        )

        docket.delete()
        opinion_cluster.delete()

    def test_remove_control_chars_on_text_indexing(self) -> None:
        """Confirm control chars are removed at indexing time."""

        o_c = OpinionClusterFactory.create(
            case_name_full="Testing v. Cluster",
            date_filed=datetime.date(2034, 8, 14),
            slug="case-name-cluster",
            precedential_status="Errata",
            docket=self.docket,
        )
        o = OpinionFactory.create(
            author=self.person,
            plain_text="Lorem ipsum control chars \x07\x08\x0B.",
            cluster=o_c,
            type="020lead",
        )
        o_2 = OpinionFactory.create(
            author=self.person,
            html="<p>Lorem html ipsum control chars \x07\x08\x0B.</p>",
            cluster=o_c,
            type="020lead",
        )

        o_doc = OpinionDocument.get(id=ES_CHILD_ID(o.pk).OPINION)
        self.assertEqual(o_doc.text, "Lorem ipsum control chars .")
        o_2_doc = OpinionDocument.get(id=ES_CHILD_ID(o_2.pk).OPINION)
        self.assertEqual(o_2_doc.text, "Lorem html ipsum control chars .")
        o_c.docket.delete()


class OpinionFeedTest(
    ESIndexTestCase, CourtTestCase, PeopleTestCase, SearchTestCase, TestCase
):
    """Tests for Opinion Search Feed"""

    def setUp(self) -> None:
        self.good_item = {
            "title": "Opinion Title",
            "court": "SCOTUS",
            "absolute_url": "http://absolute_url",
            "caseName": "Case Name",
            "status": "Precedential",
            "dateFiled": datetime.date(2015, 12, 25),
            "local_path": "txt/2015/12/28/opinion_text.txt",
        }
        self.zero_item = self.good_item.copy()
        self.zero_item.update(
            {"local_path": "txt/2015/12/28/opinion_text_bad.junk"}
        )
        self.bad_item = self.good_item.copy()
        self.bad_item.update(
            {"local_path": "asdfasdfasdfasdfasdfasdfasdfasdfasdjkfasdf"}
        )
        self.pdf_item = self.good_item.copy()
        self.pdf_item.update(
            {
                "local_path": "pdf/2013/06/12/"
                + "in_re_motion_for_consent_to_disclosure_of_court_records.pdf"
            }
        )
        self.null_item = self.good_item.copy()
        self.null_item.update({"local_path": None})
        self.feed = JurisdictionFeed()
        super(OpinionFeedTest, self).setUp()

    @classmethod
    def setUpTestData(cls) -> None:
        cls.rebuild_index("search.OpinionCluster")
        super().setUpTestData()
        court = CourtFactory(
            id="canb",
            jurisdiction="FB",
            full_name="court of the Medical Worries",
        )
        OpinionClusterFactoryWithChildrenAndParents(
            date_filed=datetime.date(2020, 8, 15),
            docket=DocketFactory(court=court, docket_number="123456"),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            syllabus="some rando syllabus",
            procedural_history="some rando history",
            source="C",
            judges="",
            attorneys="a bunch of crooks!",
            citation_count=1,
            scdb_votes_minority=3,
            scdb_votes_majority=6,
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def test_do_opinion_search_feed_have_content(self) -> None:
        """Can we make an Opinion Search Feed?"""

        # Text query case.
        params = {
            "q": f"docket number",
            "type": SEARCH_TYPES.OPINION,
        }
        response = self.client.get(
            reverse("search_feed", args=["search"]),
            params,
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        node_tests = (
            ("//atom:feed/atom:title", 1),
            ("//atom:feed/atom:link", 2),
            ("//atom:entry", 2),
            ("//atom:entry/atom:title", 2),
            ("//atom:entry/atom:link", 2),
            ("//atom:entry/atom:published", 2),
            ("//atom:entry/atom:author/atom:name", 2),
            ("//atom:entry/atom:id", 2),
            ("//atom:entry/atom:summary", 2),
        )
        for test, count in node_tests:
            node_count = len(xml_tree.xpath(test, namespaces=namespaces))  # type: ignore
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (count, test, node_count),
            )

        # Confirm items are ordered by date_filed desc
        published_format = "%Y-%m-%dT%H:%M:%S%z"
        first_item_published_str = str(
            xml_tree.xpath(
                "//atom:entry[1]/atom:published", namespaces=namespaces
            )[0].text
            # type: ignore
        )
        second_item_published_str = str(
            xml_tree.xpath(
                "//atom:entry[2]/atom:published", namespaces=namespaces
            )[0].text
            # type: ignore
        )
        first_item_published_dt = datetime.datetime.strptime(
            first_item_published_str, published_format
        )
        second_item_published_dt = datetime.datetime.strptime(
            second_item_published_str, published_format
        )
        self.assertGreater(
            first_item_published_dt,
            second_item_published_dt,
            msg="The first item should be newer than the second item.",
        )
        # Filter case.
        params = {
            "court": self.court_1.pk,
            "type": SEARCH_TYPES.OPINION,
        }
        response = self.client.get(
            reverse("search_feed", args=["search"]),
            params,
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ("//atom:feed/atom:title", 1),
            ("//atom:feed/atom:link", 2),
            ("//atom:entry", 1),
            ("//atom:entry/atom:title", 1),
            ("//atom:entry/atom:link", 1),
            ("//atom:entry/atom:published", 1),
            ("//atom:entry/atom:author/atom:name", 1),
            ("//atom:entry/atom:id", 1),
            ("//atom:entry/atom:summary", 1),
        )

        for test, count in node_tests:
            node_count = len(xml_tree.xpath(test, namespaces=namespaces))  # type: ignore
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (count, test, node_count),
            )

        # Match all case.
        params = {
            "type": SEARCH_TYPES.OPINION,
        }
        response = self.client.get(
            reverse("search_feed", args=["search"]),
            params,
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ("//atom:feed/atom:title", 1),
            ("//atom:feed/atom:link", 2),
            ("//atom:entry", 3),
            ("//atom:entry/atom:title", 3),
            ("//atom:entry/atom:link", 3),
            ("//atom:entry/atom:published", 3),
            ("//atom:entry/atom:author/atom:name", 3),
            ("//atom:entry/atom:id", 3),
            ("//atom:entry/atom:summary", 3),
        )
        for test, count in node_tests:
            node_count = len(
                xml_tree.xpath(test, namespaces=namespaces)
            )  # type: ignore
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (count, test, node_count),
            )

    async def test_jurisdiction_feed(self) -> None:
        """Can we simply load the jurisdiction feed?"""
        response = await self.async_client.get(
            reverse("jurisdiction_feed", kwargs={"court": "test"})
        )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for jurisdiction feed",
        )
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ("//atom:feed/atom:entry", 5),
            ("//atom:feed/atom:entry/atom:title", 5),
            ("//atom:entry/atom:link", 10),
            ("//atom:entry/atom:published", 5),
            ("//atom:entry/atom:author/atom:name", 5),
            ("//atom:entry/atom:id", 5),
            ("//atom:entry/atom:summary", 5),
        )
        for test, expected_count in node_tests:
            actual_count = len(
                xml_tree.xpath(
                    test, namespaces={"atom": "http://www.w3.org/2005/Atom"}
                )
            )
            self.assertEqual(
                actual_count,
                expected_count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (expected_count, test, actual_count),
            )

    async def test_all_jurisdiction_feed(self) -> None:
        """Can we simply load the jurisdiction feed?"""
        response = await self.async_client.get(
            reverse("all_jurisdictions_feed")
        )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for jurisdiction feed",
        )
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ("//atom:feed/atom:entry", 7),
            ("//atom:feed/atom:entry/atom:title", 7),
            ("//atom:entry/atom:link", 14),
            ("//atom:entry/atom:published", 7),
            ("//atom:entry/atom:author/atom:name", 7),
            ("//atom:entry/atom:id", 7),
            ("//atom:entry/atom:summary", 7),
        )
        for test, expected_count in node_tests:
            actual_count = len(
                xml_tree.xpath(
                    test, namespaces={"atom": "http://www.w3.org/2005/Atom"}
                )
            )
            self.assertEqual(
                actual_count,
                expected_count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (expected_count, test, actual_count),
            )

    def test_item_enclosure_mime_type(self) -> None:
        """Does the mime type detection work correctly?"""
        self.assertEqual(
            self.feed.item_enclosure_mime_type(self.good_item), "text/plain"
        )

    def test_item_enclosure_mime_type_handles_bogus_files(self) -> None:
        """
        Does the mime type detection safely return a good default value when
        given a file it can't detect the mime type for?
        """
        self.assertEqual(
            self.feed.item_enclosure_mime_type(self.zero_item),
            "application/octet-stream",
        )
        self.assertEqual(
            self.feed.item_enclosure_mime_type(self.bad_item),
            "application/octet-stream",
        )

    def test_feed_renders_with_item_without_file_path(self) -> None:
        """
        For Opinions without local_path attributes (that is they don't have a
        corresponding original PDF/txt/doc file) can we render the feed without
        the enclosures
        """
        fake_results = [self.null_item]

        class FakeFeed(JurisdictionFeed):
            link = "http://localhost"

            def items(self, obj):
                return fake_results

        request = HttpRequest()
        request.user = AnonymousUser()
        request.path = "/feed"
        try:
            feed = FakeFeed().get_feed(self.court_2, request)
            xml = feed.writeString("utf-8")
            self.assertIn(
                'feed xml:lang="en-us" xmlns="http://www.w3.org/2005/Atom',
                xml,
            )
        except Exception as e:
            self.fail(f"Could not call get_feed(): {e}")

    def test_cleanup_control_characters_for_xml_rendering(self) -> None:
        """Can we clean up control characters in the text for a proper XML
        rendering?
        """
        with mock.patch(
            "cl.search.documents.escape",
            return_value="Lorem ipsum control chars \x07\x08\x0B.",
        ), self.captureOnCommitCallbacks(execute=True):
            court = CourtFactory(
                id="ca1_test",
                jurisdiction="FB",
            )
            o_c = OpinionClusterFactoryWithChildrenAndParents(
                date_filed=datetime.date(2020, 8, 15),
                docket=DocketFactory(court=court, docket_number="123456"),
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                syllabus="some rando syllabus",
                sub_opinions=RelatedFactory(
                    OpinionWithChildrenFactory,
                    factory_related_name="cluster",
                    plain_text="Lorem ipsum control chars \x07\x08\x0B.",
                ),
            )

        # Opinions Search Feed
        params = {
            "q": "Lorem ipsum control chars",
            "type": SEARCH_TYPES.OPINION,
        }
        response = self.client.get(
            reverse("search_feed", args=["search"]),
            params,
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        entry_summary = "//atom:entry/atom:summary"

        # Confirm the summary is properly rendered without control chars.
        # And without highlighting
        expected_summary = "Lorem ipsum control chars ."
        actual_summary = xml_tree.xpath(entry_summary, namespaces=namespaces)[
            0
        ].text
        self.assertIn(expected_summary, actual_summary)

        # Jurisdiction Feed
        response = self.client.get(
            reverse("jurisdiction_feed", kwargs={"court": court.pk})
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        entry_summary = "//atom:entry/atom:summary"

        # Confirm the summary is properly rendered without control chars.
        # And without highlighting
        expected_summary = "Lorem ipsum control chars ."
        actual_summary = xml_tree.xpath(entry_summary, namespaces=namespaces)[
            0
        ].text
        self.assertIn(expected_summary, actual_summary)

        with self.captureOnCommitCallbacks(execute=True):
            o_c.delete()
