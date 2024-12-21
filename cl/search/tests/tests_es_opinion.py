import datetime
from http import HTTPStatus
from unittest import mock

import pytz
import time_machine
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.db.models import F
from django.http import HttpRequest
from django.test import override_settings
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.timezone import now
from elasticsearch.exceptions import ConnectionTimeout
from elasticsearch_dsl import Q
from factory import RelatedFactory
from lxml import etree, html
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from waffle.testutils import override_flag

from cl.custom_filters.templatetags.text_filters import html_decode
from cl.lib.elasticsearch_utils import do_es_api_query
from cl.lib.redis_utils import get_redis_interface
from cl.lib.test_helpers import (
    CourtTestCase,
    PeopleTestCase,
    SearchTestCase,
    opinion_document_v4_api_keys,
    opinion_v3_search_api_keys,
    opinion_v4_search_api_keys,
    skip_if_common_tests_skipped,
    v4_meta_keys,
)
from cl.people_db.factories import PersonFactory
from cl.search.api_utils import ESList
from cl.search.constants import SEARCH_HL_TAG, o_type_index_map
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
    OpinionWithParentsFactory,
)
from cl.search.feeds import JurisdictionFeed
from cl.search.management.commands.cl_index_parent_and_child_docs import (
    compose_redis_key,
)
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Court,
    Docket,
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
from cl.tests.cases import (
    CountESTasksTestCase,
    ESIndexTestCase,
    TestCase,
    TransactionTestCase,
    V4SearchAPIAssertions,
)
from cl.users.factories import UserProfileWithParentsFactory


class OpinionSearchAPICommonTests(
    CourtTestCase, PeopleTestCase, SearchTestCase
):
    version_api = "v3"
    skip_common_tests = True

    @classmethod
    def setUpTestData(cls):
        cls.mock_date = now().replace(day=15, hour=0)
        with time_machine.travel(cls.mock_date, tick=False):
            court = CourtFactory(
                id="canb",
                jurisdiction="FB",
                full_name="court of the Medical Worries",
            )
            cls.opinion_cluster_4 = (
                OpinionClusterFactoryWithChildrenAndParents(
                    case_name="Strickland v. Washington.",
                    case_name_full="Strickland v. Washington.",
                    docket=DocketFactory(
                        court=court,
                        docket_number="1:21-cv-1234",
                        source=Docket.HARVARD,
                    ),
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
            )
            cls.opinion_cluster_5 = (
                OpinionClusterFactoryWithChildrenAndParents(
                    case_name="Strickland v. Lorem.",
                    case_name_full="Strickland v. Lorem.",
                    date_filed=datetime.date(2020, 8, 15),
                    docket=DocketFactory(
                        court=court,
                        docket_number="123456",
                        source=Docket.HARVARD,
                    ),
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

    @skip_if_common_tests_skipped
    async def test_can_perform_a_regular_text_query(self) -> None:
        search_params = {"q": "supreme"}

        r = await self._test_api_results_count(search_params, 1, "text_query")
        self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_search_with_white_spaces_only(self) -> None:
        """Does everything work when whitespace is in various fields?"""
        search_params = {"q": " ", "judge": " ", "case_name": " "}

        # API, 2 results expected since the query shows published clusters by default
        r = await self._test_api_results_count(
            search_params, 4, "white_spaces"
        )
        self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_filter_using_the_case_name(self) -> None:
        search_params = {"q": "*", "case_name": "honda"}

        r = await self._test_api_results_count(search_params, 1, "case_name")
        self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_query_with_an_old_date(self) -> None:
        """Do we have any recurrent issues with old dates and strftime (issue
        220)?"""
        search_params = {"q": "*", "filed_after": "1890"}

        r = await self._test_api_results_count(search_params, 4, "filed_after")
        self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_filter_using_filed_range(self) -> None:
        """Does querying by date work?"""
        search_params = {
            "q": "*",
            "filed_after": "1895-06",
            "filed_before": "1896-01",
        }

        r = await self._test_api_results_count(search_params, 1, "filed_range")
        self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_filter_using_a_docket_number(self) -> None:
        """Can we query by docket number?"""
        search_params = {"q": "*", "docket_number": "2"}

        r = await self._test_api_results_count(
            search_params, 1, "docket_number"
        )
        self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_filter_by_citation_number(self) -> None:
        """Can we query by citation number?"""
        get_dicts = [{"q": "*", "citation": "33"}, {"q": "citation:33"}]
        for get_dict in get_dicts:
            r = await self._test_api_results_count(
                get_dict, 1, "citation_count"
            )
            self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_filter_using_neutral_citation(self) -> None:
        """Can we query by neutral citation numbers?"""
        search_params = {"q": "*", "neutral_cite": "22"}

        r = await self._test_api_results_count(
            search_params, 1, "citation_number"
        )
        self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_filter_using_judge_name(self) -> None:
        """Can we query by judge name?"""
        search_array = [{"q": "*", "judge": "david"}, {"q": "judge:david"}]
        for search_params in search_array:
            r = await self._test_api_results_count(
                search_params, 1, "judge_name"
            )
            self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_filter_by_nature_of_suit(self) -> None:
        """Can we query by nature of suit?"""
        search_params = {"q": 'suitNature:"copyright"'}

        r = await self._test_api_results_count(search_params, 1, "suit_nature")
        self.assertIn("Honda", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_can_filtering_by_citation_count(self) -> None:
        """Can we find Documents by citation filtering?"""
        search_params = {"q": "*", "cited_lt": 7, "cited_gt": 5}

        r = await self._test_api_results_count(
            search_params, 1, "citation_count"
        )
        self.assertIn("Honda", r.content.decode())

        search_params = {"q": "*", "cited_lt": 100, "cited_gt": 80}

        r = self._test_api_results_count(search_params, 0, "citation_count")

    @skip_if_common_tests_skipped
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

    @skip_if_common_tests_skipped
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

    @skip_if_common_tests_skipped
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

    @skip_if_common_tests_skipped
    async def test_can_filter_with_docket_number_suffixes(self) -> None:
        """Test docket_number with suffixes can be found."""
        # Indexed: 1:21-cv-1234 -> Search: 1:21-cv-1234-ABC
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "1:21-cv-1234-ABC",
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

    @skip_if_common_tests_skipped
    async def test_api_results_count(self) -> None:
        """Test the results count returned by the API"""
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            f"stat_{PRECEDENTIAL_STATUS.PUBLISHED}": "on",
            f"stat_{PRECEDENTIAL_STATUS.UNPUBLISHED}": "on",
            f"stat_{PRECEDENTIAL_STATUS.ERRATA}": "on",
            f"stat_{PRECEDENTIAL_STATUS.SEPARATE}": "on",
            f"stat_{PRECEDENTIAL_STATUS.IN_CHAMBERS}": "on",
            f"stat_{PRECEDENTIAL_STATUS.RELATING_TO}": "on",
            f"stat_{PRECEDENTIAL_STATUS.UNKNOWN}": "on",
        }
        expected_results = 5 if self.version_api == "v3" else 6
        r = await self._test_api_results_count(
            search_params, expected_results, "API results count"
        )
        self.assertEqual(
            r.data["count"], expected_results, msg="Wrong number of results."
        )


class OpinionV3APISearchTest(
    OpinionSearchAPICommonTests, ESIndexTestCase, TestCase
):
    skip_common_tests = False

    @classmethod
    def setUpTestData(cls):
        cls.mock_date = now().replace(day=15, hour=0)
        with time_machine.travel(cls.mock_date, tick=False):
            super().setUpTestData()
            call_command(
                "cl_index_parent_and_child_docs",
                search_type=SEARCH_TYPES.OPINION,
                queue="celery",
                pk_offset=0,
                testing_mode=True,
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

    async def test_results_api_fields(self) -> None:
        """Confirm fields in Opinion Search API results."""
        search_params = {"q": f"id:{self.opinion_2.pk} AND secret"}
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")

        keys_count = len(r.data["results"][0])
        self.assertEqual(
            keys_count,
            len(opinion_v3_search_api_keys),
            msg="Wrong number of keys.",
        )
        for (
            field,
            get_expected_value,
        ) in opinion_v3_search_api_keys.items():
            with self.subTest(field=field):
                expected_value = await sync_to_async(get_expected_value)(
                    {
                        "result": self.opinion_2,
                        "snippet": "my plain text <mark>secret</mark> word for queries",
                    }
                )
                actual_value = r.data["results"][0].get(field)
                self.assertEqual(
                    actual_value,
                    expected_value,
                    f"Field '{field}' does not match.",
                )

    def test_o_results_api_pagination(self) -> None:
        """Test pagination for V3 Opinion Search API."""

        created_opinions = []
        opinions_to_create = 20
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            for i in range(opinions_to_create):
                opinion = OpinionWithParentsFactory(
                    cluster__date_filed=datetime.date(2000, 6, i + 1)
                )
                created_opinions.append(opinion)

        page_size = 20
        total_opinions = Opinion.objects.all().distinct("cluster_id").count()
        total_pages = int(total_opinions / page_size) + 1
        ids_in_results = set()
        cd = {
            "type": SEARCH_TYPES.OPINION,
            "order_by": "dateFiled desc",
            "highlight": False,
        }
        request = Request(APIRequestFactory().get("/"))
        for page in range(1, total_pages + 1):
            search_query = OpinionClusterDocument.search()
            offset = max(0, (page - 1) * page_size)
            main_query, _ = do_es_api_query(
                search_query, cd, {"text": 500}, SEARCH_HL_TAG, "v3"
            )
            hits = ESList(
                request=request,
                main_query=main_query,
                offset=offset,
                page_size=page_size,
                type=cd["type"],
            )
            for result in hits:
                ids_in_results.add(result.id)
        self.assertEqual(
            len(ids_in_results),
            total_opinions,
            msg="Wrong number of opinions.",
        )

        search_params = {
            "type": SEARCH_TYPES.OPINION,
            f"stat_{PRECEDENTIAL_STATUS.PUBLISHED}": "on",
            f"stat_{PRECEDENTIAL_STATUS.UNPUBLISHED}": "on",
            f"stat_{PRECEDENTIAL_STATUS.ERRATA}": "on",
            f"stat_{PRECEDENTIAL_STATUS.SEPARATE}": "on",
            f"stat_{PRECEDENTIAL_STATUS.IN_CHAMBERS}": "on",
            f"stat_{PRECEDENTIAL_STATUS.RELATING_TO}": "on",
            f"stat_{PRECEDENTIAL_STATUS.UNKNOWN}": "on",
        }
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        self.assertEqual(len(r.data["results"]), 20)
        self.assertEqual(25, r.data["count"])
        self.assertIn("page=2", r.data["next"])

        # Test next page.
        search_params.update({"page": 2})
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        self.assertEqual(len(r.data["results"]), 5)
        self.assertEqual(25, r.data["count"])
        self.assertEqual(None, r.data["next"])

        # Remove Opinion objects to avoid affecting other tests.
        for created_opinion in created_opinions:
            created_opinion.delete()

    async def test_bad_syntax_error(self) -> None:
        """Can we properly raise the ElasticServerError exception?"""

        # Bad syntax due to the / char in the query.
        params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "This query contains bad/syntax query",
        }
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v3"}), params
        )
        self.assertEqual(r.status_code, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertEqual(
            r.data["detail"],
            "Internal Server Error. Please try again later or review your query.",
        )


class OpinionV4APISearchTest(
    OpinionSearchAPICommonTests,
    ESIndexTestCase,
    TestCase,
    V4SearchAPIAssertions,
):
    version_api = "v4"
    skip_common_tests = False

    @classmethod
    def setUpTestData(cls):
        cls.mock_date = now().replace(day=15, hour=0)
        with time_machine.travel(cls.mock_date, tick=False):
            cls.docket_empty = DocketFactory.create()
            cls.empty_cluster = OpinionClusterFactory.create(
                precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
                docket=cls.docket_empty,
                date_filed=datetime.date(2024, 2, 23),
            )
            cls.empty_opinion = OpinionFactory.create(
                cluster=cls.empty_cluster, plain_text=""
            )

            super().setUpTestData()
            call_command(
                "cl_index_parent_and_child_docs",
                search_type=SEARCH_TYPES.OPINION,
                queue="celery",
                pk_offset=0,
                testing_mode=True,
            )

    async def _test_api_results_count(
        self, params, expected_count, field_name
    ):
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v4"}), params
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

    async def test_results_api_fields(self) -> None:
        """Confirm fields in V4 Opinion Search API results."""
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"id:{self.opinion_2.pk}",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_count = len(r.data["results"][0])
        self.assertEqual(
            keys_count,
            len(opinion_v4_search_api_keys),
            msg="Parent fields count didn't match.",
        )
        rd_keys_count = len(r.data["results"][0]["opinions"][0])
        self.assertEqual(
            rd_keys_count,
            len(opinion_document_v4_api_keys),
            msg="Child fields count didn't match.",
        )
        content_to_compare = {"result": self.opinion_2, "V4": True}
        await self._test_api_fields_content(
            r,
            content_to_compare,
            opinion_v4_search_api_keys,
            opinion_document_v4_api_keys,
            v4_meta_keys,
        )

    def test_extract_snippet_from_db_highlight_disabled(self) -> None:
        """Confirm that the snippet can be properly extracted from the database,
        prioritizing the different text fields available in the content when
        highlighting is disabled."""

        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            c_2_opinion_1 = OpinionFactory.create(
                extracted_by_ocr=True,
                author=self.person_2,
                html_columbia="<b>html_columbia</b> &amp; text from DB ",
                html_lawbox="<b>html_lawbox</b> &amp; text from DB",
                cluster=self.opinion_cluster_2,
            )
            c_2_opinion_2 = OpinionFactory.create(
                extracted_by_ocr=True,
                author=self.person_2,
                html_lawbox="<b>html_lawbox</b> &amp; text from DB",
                xml_harvard="<b>xml_harvard</b> &amp; text from DB",
                cluster=self.opinion_cluster_2,
            )
            c_2_opinion_3 = OpinionFactory.create(
                extracted_by_ocr=True,
                author=self.person_2,
                xml_harvard="<b>xml_harvard</b> &amp; text from DB",
                html_anon_2020="<b>html_anon_2020</b> &amp; text from DB",
                cluster=self.opinion_cluster_2,
            )

            c_3_opinion_1 = OpinionFactory.create(
                extracted_by_ocr=True,
                author=self.person_2,
                html_anon_2020="<b>html_anon_2020</b> &amp; text from DB",
                html="<b>html</b> &amp; text from DB",
                cluster=self.opinion_cluster_3,
            )
            c_3_opinion_2 = OpinionFactory.create(
                extracted_by_ocr=True,
                author=self.person_2,
                html="<b>html</b> &amp; text from DB",
                plain_text="plain_text text from DB",
                cluster=self.opinion_cluster_3,
            )

        test_cases = [
            (
                self.opinion_cluster_3.pk,
                {
                    c_3_opinion_1.pk: c_3_opinion_1.html_anon_2020,
                    c_3_opinion_2.pk: c_3_opinion_2.html,
                    self.opinion_3.pk: self.opinion_3.plain_text,
                },
            ),
            (
                self.opinion_cluster_2.pk,
                {
                    c_2_opinion_1.pk: c_2_opinion_1.html_columbia,
                    c_2_opinion_2.pk: c_2_opinion_2.html_lawbox,
                    c_2_opinion_3.pk: c_2_opinion_2.xml_harvard,
                    self.opinion_2.pk: self.opinion_2.plain_text,
                },
            ),
        ]
        # Opinion Search type HL disabled, snippet is extracted from DB.
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"cluster_id:({self.opinion_cluster_2.pk} OR {self.opinion_cluster_3.pk})",
            "order_by": "dateFiled desc",
        }
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}),
            search_params,
        )
        for result, (cluster_pk, opinions) in zip(
            r.data["results"], test_cases
        ):
            self.assertEqual(cluster_pk, result["cluster_id"])
            cluster_opinions = result["opinions"]
            for result_opinion in cluster_opinions:
                with self.subTest(
                    result_opinion=result_opinion,
                    msg="Test snippet extracted from DB.",
                ):
                    expected_text = html_decode(
                        strip_tags(opinions[result_opinion["id"]])
                    )
                    self.assertEqual(expected_text, result_opinion["snippet"])

        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            c_2_opinion_1.delete()
            c_2_opinion_2.delete()
            c_2_opinion_3.delete()
            c_3_opinion_1.delete()
            c_3_opinion_2.delete()

    async def test_results_api_highlighted_fields(self) -> None:
        """Confirm highlighted fields in V4 Opinion Search API results."""
        # API HL disabled.
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"id:{self.opinion_2.pk} suitNature:copyright court_citation_string:Test text:(secret word) citation:(22 AL) OR citation:(33 state)",
            "case_name": "Howard",
            "docket_number": "docket number 2",
        }

        # Opinion Search type HL disabled.
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, len(opinion_v4_search_api_keys))
        rd_keys_count = len(r.data["results"][0]["opinions"][0])
        self.assertEqual(rd_keys_count, len(opinion_document_v4_api_keys))
        content_to_compare = {"result": self.opinion_2, "V4": True}
        await self._test_api_fields_content(
            r,
            content_to_compare,
            opinion_v4_search_api_keys,
            opinion_document_v4_api_keys,
            v4_meta_keys,
        )

        # Opinion Search type HL enabled.
        search_params["type"] = SEARCH_TYPES.OPINION
        search_params["highlight"] = True
        r = await self._test_api_results_count(search_params, 1, "API fields")
        content_to_compare = {
            "result": self.opinion_2,
            "caseName": "<mark>Howard</mark> v. Honda",
            "citation": [
                "<mark>22</mark> <mark>AL</mark> 339",
                "<mark>33</mark> <mark>state</mark> 1",
            ],
            "suitNature": "<mark>copyright</mark>",
            "court_citation_string": "<mark>Test</mark>",
            "docketNumber": "<mark>docket number 2</mark>",
            "snippet": "my plain text <mark>secret word</mark> for queries",
            "V4": True,
        }
        await self._test_api_fields_content(
            r,
            content_to_compare,
            opinion_v4_search_api_keys,
            opinion_document_v4_api_keys,
            v4_meta_keys,
        )

    @override_settings(SEARCH_API_PAGE_SIZE=3)
    def test_opinion_results_cursor_api_pagination(self) -> None:
        """Test cursor pagination for V4 Opinion Search API."""

        created_clusters = []
        cluster_to_create = 6
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            for _ in range(cluster_to_create):
                cluster = OpinionClusterFactoryWithChildrenAndParents(
                    docket=DocketFactory(
                        court=self.court_1,
                        source=Docket.HARVARD,
                    ),
                    sub_opinions=RelatedFactory(
                        OpinionWithChildrenFactory,
                        factory_related_name="cluster",
                    ),
                    date_filed=datetime.date(2023, 8, 15),
                    precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                )
                created_clusters.append(cluster)

        total_clusters = OpinionCluster.objects.filter(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED
        ).count()
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "order_by": "score desc",
            "highlight": False,
        }
        tests = [
            {
                "results": 3,
                "count_exact": total_clusters,
                "next": True,
                "previous": False,
            },
            {
                "results": 3,
                "count_exact": total_clusters,
                "next": True,
                "previous": True,
            },
            {
                "results": 3,
                "count_exact": total_clusters,
                "next": True,
                "previous": True,
            },
            {
                "results": 1,
                "count_exact": total_clusters,
                "next": False,
                "previous": True,
            },
        ]

        order_types = [
            "score desc",
            "dateFiled desc",
            "dateFiled asc",
            "citeCount desc",
            "citeCount asc",
        ]
        for order_type in order_types:
            # Test forward pagination.
            next_page = None
            all_document_ids = []
            ids_per_page = []
            current_page = None
            with self.subTest(order_type=order_type, msg="Sorting order."):
                search_params["order_by"] = order_type
                for test in tests:
                    with self.subTest(test=test, msg="forward pagination"):
                        if not next_page:
                            r = self.client.get(
                                reverse(
                                    "search-list", kwargs={"version": "v4"}
                                ),
                                search_params,
                            )
                        else:
                            r = self.client.get(next_page)
                        # Test page variables.
                        next_page, _, current_page = self._test_page_variables(
                            r, test, current_page, search_params["type"]
                        )
                        ids_in_page = set()
                        for result in r.data["results"]:
                            all_document_ids.append(result["docket_id"])
                            ids_in_page.add(result["docket_id"])
                        ids_per_page.append(ids_in_page)

            # Confirm all the documents were shown when paginating forwards.
            self.assertEqual(
                len(all_document_ids),
                total_clusters,
                msg="Wrong number of clusters.",
            )

        # Test backward pagination.
        tests_backward = tests.copy()
        tests_backward.reverse()
        previous_page = None
        all_ids_prev = []
        for test in tests_backward:
            with self.subTest(test=test, msg="backward pagination"):
                if not previous_page:
                    r = self.client.get(current_page)
                else:
                    r = self.client.get(previous_page)

                # Test page variables.
                _, previous_page, current_page = self._test_page_variables(
                    r, test, current_page, search_params["type"]
                )
                ids_in_page_got = set()
                for result in r.data["results"]:
                    all_ids_prev.append(result["docket_id"])
                    ids_in_page_got.add(result["docket_id"])
                current_page_ids_prev = ids_per_page.pop()
                # Check if IDs obtained with forward pagination match
                # the IDs obtained when paginating backwards.
                self.assertEqual(
                    current_page_ids_prev,
                    ids_in_page_got,
                    msg="Wrong clusters in page.",
                )

        # Confirm all the documents were shown when paginating backwards.
        self.assertEqual(
            len(all_ids_prev),
            total_clusters,
            msg="Wrong number of clusters.",
        )

        # Remove OpinionCluster objects to avoid affecting other tests.
        for created_cluster in created_clusters:
            created_cluster.delete()

    def test_opinion_cursor_api_pagination_count(self) -> None:
        """Test cursor pagination count for V4 Opinion Search API."""

        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "order_by": "score desc",
            "highlight": False,
        }
        total_clusters = OpinionCluster.objects.filter(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED
        ).count()
        ## Get count from cardinality.
        with override_settings(
            ELASTICSEARCH_MAX_RESULT_COUNT=total_clusters - 1
        ):
            # Opinion Search request, count clusters.
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_clusters,
                msg="Results cardinality count didn't match.",
            )

        ## Get count from main query.
        with override_settings(ELASTICSEARCH_MAX_RESULT_COUNT=total_clusters):
            # Opinion Search request, count clusters.
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_clusters,
                msg="Results main query count didn't match.",
            )

    async def test_results_api_empty_fields(self) -> None:
        """Confirm empty fields values in V4 Opinion Search API results."""

        # Confirm expected values for empty fields.
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"id:{self.empty_opinion.pk}",
            f"stat_{PRECEDENTIAL_STATUS.UNPUBLISHED}": "on",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, len(opinion_v4_search_api_keys))
        op_doc_keys_count = len(r.data["results"][0]["opinions"][0])
        self.assertEqual(op_doc_keys_count, len(opinion_document_v4_api_keys))
        content_to_compare = {
            "result": self.empty_opinion,
            "V4": True,
        }
        await self._test_api_fields_content(
            r,
            content_to_compare,
            opinion_v4_search_api_keys,
            opinion_document_v4_api_keys,
            v4_meta_keys,
        )

    def test_date_created_without_microseconds_parsing(self) -> None:
        """Confirm a date_created filed without microseconds can be properly
        parsed by TimeStampField"""

        no_micro_second_cluster = OpinionClusterFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
            docket=self.docket_empty,
            date_filed=datetime.date(2024, 2, 23),
        )
        date_created_no_microseconds = datetime.datetime(
            2010, 4, 28, 16, 1, 19, tzinfo=pytz.UTC
        )
        no_micro_second_opinion = OpinionFactory.create(
            cluster=no_micro_second_cluster, plain_text=""
        )
        # Override date_created
        no_micro_second_opinion.date_created = date_created_no_microseconds
        no_micro_second_opinion.save()

        # Index the document into ES.
        es_save_document.delay(
            no_micro_second_opinion.pk,
            "search.Opinion",
            OpinionDocument.__name__,
        )
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"id:{no_micro_second_opinion.pk}",
            f"stat_{PRECEDENTIAL_STATUS.UNPUBLISHED}": "on",
        }
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}), search_params
        )
        self.assertEqual(
            r.data["results"][0]["opinions"][0]["meta"]["date_created"],
            date_created_no_microseconds.isoformat().replace("+00:00", "Z"),
        )

        no_micro_second_cluster.delete()

    @override_settings(OPINION_HITS_PER_RESULT=6)
    def test_nested_opinions_limit(self) -> None:
        """Test nested opinions limit for V4 Opinion Search API."""

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            cluster = OpinionClusterFactory.create(
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                docket=self.docket_1,
                date_filed=datetime.date(2024, 8, 23),
            )
            opinions_to_create = 6
            for _ in range(opinions_to_create):
                OpinionFactory.create(cluster=cluster, plain_text="")

        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"cluster_id:{cluster.pk}",
            "order_by": "score desc",
            "highlight": False,
        }
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}), search_params
        )
        self.assertEqual(
            len(r.data["results"][0]["opinions"]),
            settings.OPINION_HITS_PER_RESULT,
            msg="Results count didn't match.",
        )
        cluster.delete()

    def test_opinions_specific_sorting_keys(self) -> None:
        """Test if the dateFiled and citeCount sorting keys work properly in
        the V4 Opinions Search API. Note that no function score is used in the
        Opinions search because it is not required; dateFiled is a mandatory
        field in the OpinionCluster model."""

        # Query string, order by dateFiled desc
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "order_by": "dateFiled desc",
            "highlight": False,
            f"stat_{PRECEDENTIAL_STATUS.PUBLISHED}": "on",
            f"stat_{PRECEDENTIAL_STATUS.UNPUBLISHED}": "on",
        }
        params_date_filed_asc = search_params.copy()
        params_date_filed_asc["order_by"] = "dateFiled asc"
        params_cite_count_desc = search_params.copy()
        params_cite_count_desc["order_by"] = "citeCount desc"
        params_cite_count_asc = search_params.copy()
        params_cite_count_asc["order_by"] = "citeCount asc"

        test_cases = [
            {
                "name": "Query order by dateFiled desc",
                "search_params": search_params,
                "expected_results": 5,
                "expected_order": [
                    self.empty_cluster.pk,  # 2024/02/23
                    self.opinion_cluster_5.pk,  # 2020/08/15 pk 2
                    self.opinion_cluster_4.pk,  # 2020/08/15 pk 1
                    self.opinion_cluster_3.pk,  # 2015/08/15
                    self.opinion_cluster_2.pk,  # 1895/06/09
                ],
            },
            {
                "name": "Query order by dateFiled asc",
                "search_params": params_date_filed_asc,
                "expected_results": 5,
                "expected_order": [
                    self.opinion_cluster_2.pk,  # 1895/06/09
                    self.opinion_cluster_3.pk,  # 2015/08/15
                    self.opinion_cluster_5.pk,  # 2020/08/15 pk 2
                    self.opinion_cluster_4.pk,  # 2020/08/15 pk 1
                    self.empty_cluster.pk,  # 2024/02/23
                ],
            },
            {
                "name": "Query order by citeCount desc",
                "search_params": params_cite_count_desc,
                "expected_results": 5,
                "expected_order": [
                    self.opinion_cluster_3.pk,  # 8
                    self.opinion_cluster_2.pk,  # 6
                    self.opinion_cluster_5.pk,  # 1 pk 2
                    self.opinion_cluster_4.pk,  # 1 pk 1
                    self.empty_cluster.pk,  # 0
                ],
            },
            {
                "name": "Query order by citeCount asc",
                "search_params": params_cite_count_asc,
                "expected_results": 5,
                "expected_order": [
                    self.empty_cluster.pk,  # 0
                    self.opinion_cluster_5.pk,  # 1 pk 2
                    self.opinion_cluster_4.pk,  # 1 pk 1
                    self.opinion_cluster_2.pk,  # 6
                    self.opinion_cluster_3.pk,  # 8
                ],
            },
        ]
        for test in test_cases:
            self._test_results_ordering(test, "cluster_id")

    def test_verify_empty_lists_type_fields_after_partial_update(self):
        """Verify that list fields related to foreign keys are returned as
        empty lists after a partial update that removes the related instance
        and empties the list field.
        """
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            person = PersonFactory.create(
                gender="m",
                name_first="Bill",
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
                precedential_status="Published",
                citation_count=4,
                docket=self.docket_1,
            )
            opinion_cluster.panel.add(person)
            citation_1 = CitationWithParentsFactory.create(
                volume=33,
                reporter="state",
                page="1",
                type=1,
                cluster=opinion_cluster,
            )
            opinion = OpinionFactory.create(
                extracted_by_ocr=False,
                plain_text="my plain text secret word for queries",
                cluster=opinion_cluster,
                local_path="test/search/opinion_doc.doc",
                per_curiam=False,
                type="020lead",
            )
            opinion.joined_by.add(person)

            person.delete()

        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"cluster_id:{opinion_cluster.pk}",
        }
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}), search_params
        )

        self.assertEqual(
            r.data["results"][0]["opinions"][0]["joined_by_ids"], []
        )

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            citation_1.delete()
            opinion.delete()

        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}), search_params
        )

        fields_to_tests = [
            "panel_names",
            "citation",
            "sibling_ids",
            "panel_ids",
        ]
        # Lists fields should return []
        for field in fields_to_tests:
            with self.subTest(field=field, msg="List fields test."):
                self.assertEqual(r.data["results"][0][field], [])


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
            docket=DocketFactory(
                court=court,
                docket_number="1:21-cv-1234",
                source=Docket.HARVARD,
            ),
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
            docket=DocketFactory(
                court=court, docket_number="123456", source=Docket.HARVARD
            ),
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

    def _assert_missing_citations_query(
        self, html_content, suggested_query, missing_citations
    ):
        """Assert that a message with missing citations is present in search
        results.
        """
        p_element = html.fromstring(html_content).xpath(
            '//p[@id="missing-citations"]'
        )
        p_content = html.tostring(
            p_element[0], method="text", encoding="unicode"
        ).replace("\xa0", " ")

        self.assertIn(
            suggested_query,
            p_content.strip(),
            msg=f"'{suggested_query}' was not found within the message.",
        )

        for missing_citation in missing_citations:
            with self.subTest(
                missing_citation=missing_citation,
                msg="Confirm missing_citations",
            ):
                self.assertIn(
                    missing_citation,
                    p_content.strip(),
                    msg=f"'{missing_citation}' was not found within the message.",
                )

        if len(missing_citations) > 1:
            self.assertIn(
                "It appears we don't yet have those citations.",
                p_content.strip(),
            )
        else:
            self.assertIn(
                "It appears we don't yet have that citation.",
                p_content.strip(),
            )

    def _assert_search_box_query(self, html_content, expected_query):
        """Assert the search box value is correct."""
        search_box = html.fromstring(html_content).xpath('//input[@id="id_q"]')
        search_box_value = search_box[0].get("value", "")

        self.assertIn(
            expected_query,
            search_box_value.strip(),
            msg=f"'{expected_query}' was not found within the search box.",
        )

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
        court_count = await Court.objects.filter(in_use=True).acount()
        self.assertIn(
            f"{court_count} Jurisdictions",
            response.content.decode(),
            msg="Wrong number of Jurisdictions shown in Homepage",
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
                HTTPStatus.OK,
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
            "q": "1:21-cv-1234-ABC",
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
        search_params = {"q": 'status:"published"'}
        r = await self._test_article_count(search_params, 4, "status")
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("4 Opinions", r.content.decode())

        search_params = {"q": 'status:"errata"', "stat_Errata": "on"}
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

    @override_settings(OPINION_HITS_PER_RESULT=6)
    def test_nested_opinions_limit_frontend(self) -> None:
        """Test nested opinions limit for Opinion Search in the frontend."""

        with self.captureOnCommitCallbacks(execute=True):
            cluster = OpinionClusterFactory.create(
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                docket=self.docket_1,
                date_filed=datetime.date(2024, 8, 23),
            )
            opinions_to_create = 6
            for _ in range(opinions_to_create):
                OpinionFactory.create(cluster=cluster, plain_text="")

        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"cluster_id:{cluster.pk}",
            "order_by": "score desc",
            "highlight": False,
        }
        r = self.client.get("/", search_params)

        # Count nested opinions in the cluster results.
        expected_count = 6
        tree = html.fromstring(r.content.decode())
        article = tree.xpath("//article")[0]
        got = len(article.xpath(".//h4"))
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of child documents \n"
            "Expected: %s\n"
            "     Got: %s\n\n" % (expected_count, got),
        )
        cluster.delete()

    def test_frontend_opinions_count(self) -> None:
        """Assert Opinions search results counts in the fronted. Below and
        above the estimation threshold.
        """
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        counts_text = self._get_frontend_counts_text(r)
        # 2 cases and 3 Docket entries in counts are returned
        self.assertIn("4 Opinions", counts_text)

        # Assert estimated counts above the threshold.
        with mock.patch(
            "cl.lib.elasticsearch_utils.simplify_estimated_count",
            return_value=5300,
        ):
            r = self.client.get(
                reverse("show_results"),
                search_params,
            )
        counts_text = self._get_frontend_counts_text(r)
        self.assertIn("About 5,300 Opinions", counts_text)

    def test_display_query_citation_frontend(self) -> None:
        """Confirm if the query citation alert is shown on the frontend when
        querying a single citation, and it's found into ES."""

        # Cluster with citation and multiple sibling opinions is properly matched.
        with self.captureOnCommitCallbacks(execute=True):
            cluster = OpinionClusterFactory.create(
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                docket=self.docket_1,
                date_filed=datetime.date(2024, 8, 23),
            )
            OpinionFactory.create(cluster=cluster, plain_text="")
            OpinionFactory.create(cluster=cluster, plain_text="")
            CitationWithParentsFactory.create(
                volume=31,
                reporter="Pa. D. & C.",
                page="445",
                type=2,
                cluster=cluster,
            )

        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "31 Pa. D. & C. 445",
            "order_by": "score desc",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertIn(
            "It looks like you're trying to search for", r.content.decode()
        )

        # Add a new cluster for the same citation. This time, it is not
        # possible to identify a unique case for the citation.
        with self.captureOnCommitCallbacks(execute=True):
            cluster_2 = OpinionClusterFactory.create(
                case_name="Test case",
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                docket=self.docket_1,
                date_filed=datetime.date(2024, 8, 23),
            )
            OpinionFactory.create(cluster=cluster_2, plain_text="")
            CitationWithParentsFactory.create(
                volume=31,
                reporter="Pa. D. & C.",
                page="445",
                type=2,
                cluster=cluster_2,
            )

        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "31 Pa. D. & C. 445",
            "order_by": "score desc",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertNotIn(
            "It looks like you're trying to search for", r.content.decode()
        )

        cluster_2.delete()
        cluster.delete()

    def test_drop_missing_citation_from_query(self) -> None:
        """If a query contains a citation that we don't have,
        drop the citation(s) from the query, perform the query, and inform the
        users about this behavior."""

        # Cluster with citation and multiple sibling opinions is properly matched.
        with self.captureOnCommitCallbacks(execute=True):
            cluster = OpinionClusterFactory.create(
                case_name="Voutila v. Lorem",
                attorneys="James Smith",
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                docket=self.docket_1,
                date_filed=datetime.date(2024, 8, 23),
            )
            CitationWithParentsFactory.create(
                volume=31,
                reporter="Pa. D. & C.",
                page="445",
                type=2,
                cluster=cluster,
            )
            OpinionFactory.create(cluster=cluster, plain_text="")

        # Test missing citation 32 Pa. D. & C. 446
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "Voutila v. Lorem 32 Pa. D. & C. 446 James Smith",
            "order_by": "score desc",
        }
        r = async_to_sync(self._test_article_count)(
            search_params, 1, "text_query"
        )
        self._assert_missing_citations_query(
            r.content.decode(),
            "Voutila v. Lorem James Smith",
            ["32 Pa. D. & C. 446"],
        )
        self._assert_search_box_query(
            r.content.decode(),
            "Voutila v. Lorem 32 Pa. D. & C. 446 James Smith",
        )

        # Test two missing citations "32 Pa. D. & C. 446" and "32 Pa. D. & C. 447"
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "Voutila v. Lorem 32 Pa. D. & C. 446 James Smith 32 Pa. D. & C. 447",
            "order_by": "score desc",
        }
        r = async_to_sync(self._test_article_count)(
            search_params, 1, "text_query"
        )
        self._assert_missing_citations_query(
            r.content.decode(),
            "Voutila v. Lorem James Smith",
            ["32 Pa. D. & C. 446", "32 Pa. D. & C. 447"],
        )
        self._assert_search_box_query(
            r.content.decode(),
            "Voutila v. Lorem 32 Pa. D. & C. 446 James Smith 32 Pa. D. & C. 447",
        )

        # Test one missing citations "32 Pa. D. & C. 446" and keep an available
        # one "31 Pa. D. & C. 445"
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "Voutila v. Lorem 32 Pa. D. & C. 446 James Smith 31 Pa. D. & C. 445",
            "order_by": "score desc",
        }
        r = async_to_sync(self._test_article_count)(
            search_params, 1, "text_query"
        )
        self._assert_missing_citations_query(
            r.content.decode(),
            "Voutila v. Lorem James Smith 31 Pa. D. & C. 445",
            ["32 Pa. D. & C. 446"],
        )
        self._assert_search_box_query(
            r.content.decode(),
            "Voutila v. Lorem 32 Pa. D. & C. 446 James Smith 31 Pa. D. & C. 445",
        )

        cluster.delete()

    def test_uses_exact_version_for_case_name_field(self) -> None:
        """Confirm that stemming is disabled on the case_name
        filter and text query.
        """

        with self.captureOnCommitCallbacks(execute=True):
            cluster_1 = OpinionClusterFactory.create(
                case_name="Maecenas Howell",
                case_name_full="Ipsum Dolor",
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                docket=self.docket_1,
            )
            OpinionFactory.create(cluster=cluster_1, plain_text="")
            cluster_2 = OpinionClusterFactory.create(
                case_name="Maecenas Howells",
                case_name_full="Ipsum Dolor",
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                docket=self.docket_1,
            )
            OpinionFactory.create(cluster=cluster_2, plain_text="")

        # case_name filter: Howell
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "case_name": "Maecenas Howell",
        }
        r = async_to_sync(self._test_article_count)(
            search_params, 1, "case_name exact filter"
        )
        self.assertIn("<mark>Maecenas</mark>", r.content.decode())
        self.assertIn("<mark>Howell</mark>", r.content.decode())

        # case_name filter: Howells
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "case_name": "Maecenas Howells",
        }
        r = async_to_sync(self._test_article_count)(
            search_params, 1, "case_name exact filter"
        )
        self.assertIn("<mark>Maecenas</mark>", r.content.decode())
        self.assertIn("<mark>Howells</mark>", r.content.decode())

        # text query: Howell
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "Maecenas Howell",
        }
        r = async_to_sync(self._test_article_count)(
            search_params, 1, "case_name exact query"
        )
        self.assertIn("<mark>Maecenas Howell</mark>", r.content.decode())

        # text query: Howells
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "Maecenas Howells",
        }
        r = async_to_sync(self._test_article_count)(
            search_params, 1, "case_name exact query"
        )
        self.assertIn("<mark>Maecenas Howells</mark>", r.content.decode())

        cluster_1.delete()
        cluster_2.delete()


@override_flag("ui_flag_for_o", False)
@override_settings(RELATED_MLT_MINTF=1)
class RelatedSearchTest(
    ESIndexTestCase, CourtTestCase, PeopleTestCase, SearchTestCase, TestCase
):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.cluster_4 = OpinionClusterFactory.create(
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
            docket=cls.docket_1,
        )
        cls.opinion_7 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=None,
            plain_text="my plain text secret word for queries",
            cluster=cls.cluster_4,
            local_path="txt/2015/12/28/opinion_text.txt",
            per_curiam=False,
            type="020lead",
        )
        cls.opinion_8 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=None,
            plain_text="my plain text secret word for queries",
            cluster=cls.cluster_4,
            local_path="txt/2015/12/28/opinion_text.txt",
            per_curiam=False,
            type="010combined",
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def setUp(self) -> None:
        # Do this in two steps to avoid triggering profile creation signal
        admin = UserProfileWithParentsFactory.create(
            user__username="admin",
            user__password=make_password("password"),
        )
        admin.user.is_superuser = True
        admin.user.is_staff = True
        admin.user.save()

        # Clean cached results before starting the test.
        r = get_redis_interface("CACHE")
        keys_cited = r.keys("clusters-cited-es")
        if keys_cited:
            r.delete(*keys_cited)
        keys_mlt = r.keys("clusters-mlt-es")
        if keys_mlt:
            r.delete(*keys_mlt)

        super().setUp()

    def get_article_count(self, r):
        """Get the article count in a query response"""
        return len(html.fromstring(r.content.decode()).xpath("//article"))

    def test_more_like_this_opinion(self) -> None:
        """Does the MoreLikeThis query return the correct number and order of
        articles."""

        seed_1_pk = self.opinion_1.pk  # Paul Debbas v. Franklin
        seed_2_pk = self.opinion_7.pk  # "Voutila v. Bonvini"
        expected_article_count = 2
        expected_first_pk = self.opinion_cluster_2.pk  # Howard v. Honda
        expected_second_pk = self.opinion_cluster_3.pk  # case name cluster 3

        params = {
            "type": "o",
            "q": f"related:{seed_1_pk},{seed_2_pk}",
        }

        # enable all status filters (otherwise results do not match detail page)
        params.update(
            {f"stat_{s}": "on" for s, v in PRECEDENTIAL_STATUS.NAMES}
        )

        r = self.client.get(reverse("show_results"), params)
        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertEqual(expected_article_count, self.get_article_count(r))
        self.assertTrue(
            r.content.decode().index("/opinion/%i/" % expected_first_pk)
            < r.content.decode().index("/opinion/%i/" % expected_second_pk),
            msg="'Howard v. Honda' should come AFTER 'case name cluster 3'.",
        )
        # Confirm that results contain a snippet
        self.assertIn("<mark>plain</mark>", r.content.decode())

        # Confirm "related to" cluster legend is within the results' header.
        h2_element = html.fromstring(r.content.decode()).xpath(
            '//h2[@id="result-count"]'
        )
        h2_content = html.tostring(
            h2_element[0], method="text", encoding="unicode"
        )
        # Confirm that we can display more than one "related to" cluster.
        self.assertIn("related to", h2_content)
        self.assertIn("Debbas", h2_content)
        self.assertIn("Franklin", h2_content)
        self.assertIn("Voutila", h2_content)
        self.assertIn("Bonvini", h2_content)

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
                f"/opinion/{self.opinion_cluster_1.pk}/{self.opinion_cluster_1.slug}/",
                "Debbas v. Franklin",
            ),
            (
                f"/opinion/{self.opinion_cluster_2.pk}/{self.opinion_cluster_2.slug}/",
                "Howard v. Honda",
            ),
            (
                f"/opinion/{self.cluster_4.pk}/{self.cluster_4.slug}/",
                "Voutila v. Bonvini",
            ),
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
                f"/opinion/{self.opinion_cluster_2.pk}/{self.opinion_cluster_2.slug}/",
                "Howard v. Honda",
            ),
            (
                f"/opinion/{self.cluster_4.pk}/{self.cluster_4.slug}/",
                "Voutila v. Bonvini",
            ),
            (
                f"/opinion/{self.opinion_cluster_3.pk}/{self.opinion_cluster_3.slug}/",
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

    async def test_more_like_this_opinion_detail_multiple_sub_opinions(
        self,
    ) -> None:
        """MoreLikeThis query on opinion detail page on a cluster with multiple
        sub_opinions."""
        seed_pk = self.cluster_4.pk  # Voutila v. Bonvini

        # Login as staff user (related items are by default disabled for guests)
        self.assertTrue(
            await sync_to_async(self.async_client.login)(
                username="admin", password="password"
            )
        )

        r = await self.async_client.get("/opinion/%i/asdf/" % seed_pk)
        self.assertEqual(r.status_code, 200)

        tree = html.fromstring(r.content.decode())

        recommendations_actual = [
            (a.get("href"), a.text_content().strip())
            for a in tree.xpath("//*[@id='recommendations']/ul/li/a")
        ]
        recommendations_expected = [
            (
                f"/opinion/{self.opinion_cluster_1.pk}/{self.opinion_cluster_1.slug}/",
                "Debbas v. Franklin",
            ),
            (
                f"/opinion/{self.opinion_cluster_2.pk}/{self.opinion_cluster_2.slug}/",
                "Howard v. Honda",
            ),
            (
                f"/opinion/{self.opinion_cluster_3.pk}/{self.opinion_cluster_3.slug}/",
                "case name cluster 3",
            ),
        ]
        # Test if related opinion exist in expected order
        self.assertEqual(
            recommendations_expected,
            recommendations_actual,
            msg="Unexpected opinion recommendations.",
        )
        await sync_to_async(self.async_client.logout)()

    async def test_es_get_citing_and_related_clusters_no_cache_timeout(
        self,
    ) -> None:
        """Confirm that 'Unable to retrieve clusters...' message is shown if
        the MLT and citing query time out."""
        seed_pk = self.opinion_cluster_3.pk  # case name cluster 3

        # Login as staff user (related items are by default disabled for guests)
        self.assertTrue(
            await sync_to_async(self.async_client.login)(
                username="admin", password="password"
            )
        )

        with mock.patch(
            "elasticsearch_dsl.MultiSearch.execute"
        ) as mock_m_search_execute:
            mock_m_search_execute.side_effect = ConnectionTimeout(
                "Connection timeout"
            )
            r = await self.async_client.get("/opinion/%i/asdf/" % seed_pk)

        self.assertEqual(r.status_code, 200)
        tree = html.fromstring(r.content.decode())
        recommendations_text = tree.xpath("//*[@id='recommendations']")[
            0
        ].text_content()
        citing_text = tree.xpath("//*[@id='cited-by']")[0].text_content()
        self.assertIn(
            "Unable to retrieve related clusters.", recommendations_text
        )
        self.assertIn("Unable to retrieve citing clusters.", citing_text)
        await sync_to_async(self.async_client.logout)()

    async def test_es_get_citing_and_related_clusters_no_cache_connection_error(
        self,
    ) -> None:
        """Confirm that there are no related clusters, and display 'This case
        has not yet been cited in our system.' if the query raised a
        connection error."""

        seed_pk = self.opinion_cluster_3.pk  # case name cluster 3

        # Login as staff user (related items are by default disabled for guests)
        self.assertTrue(
            await sync_to_async(self.async_client.login)(
                username="admin", password="password"
            )
        )

        with mock.patch(
            "elasticsearch_dsl.MultiSearch.execute"
        ) as mock_m_search_execute:
            mock_m_search_execute.side_effect = ConnectionError()
            r = await self.async_client.get("/opinion/%i/asdf/" % seed_pk)

        self.assertEqual(r.status_code, 200)
        tree = html.fromstring(r.content.decode())
        recommendations_text = tree.xpath("//*[@id='recommendations']")
        citing_text = tree.xpath("//*[@id='cited-by']")[0].text_content()
        self.assertEqual([], recommendations_text)
        self.assertIn(
            "This case has not yet been cited in our system.", citing_text
        )
        await sync_to_async(self.async_client.logout)()

    async def test_es_get_citing_and_related_clusters_cache_timeout(
        self,
    ) -> None:
        """Confirm that related and citing clusters are properly displayed if
        the MLT and citing queries time out but cached results are available.
        """
        seed_pk = self.opinion_cluster_3.pk  # case name cluster 3

        # Login as staff user (related items are by default disabled for guests)
        self.assertTrue(
            await sync_to_async(self.async_client.login)(
                username="admin", password="password"
            )
        )
        # Initial successful request. Results are cached.
        r = await self.async_client.get("/opinion/%i/asdf/" % seed_pk)
        self.assertEqual(r.status_code, 200)

        # Timeout Request.
        with mock.patch(
            "elasticsearch_dsl.MultiSearch.execute"
        ) as mock_m_search_execute:
            mock_m_search_execute.side_effect = ConnectionTimeout(
                "Connection timeout"
            )
            r = await self.async_client.get("/opinion/%i/asdf/" % seed_pk)

        self.assertEqual(r.status_code, 200)
        tree = html.fromstring(r.content.decode())

        # Results are returned from cache.
        recommendations_actual = [
            (a.get("href"), a.text_content().strip())
            for a in tree.xpath("//*[@id='recommendations']/ul/li/a")
        ]
        citing_actual = [
            (a.get("href"), a.text_content().strip())
            for a in tree.xpath("//*[@id='cited-by']/ul/li/a")
        ]
        recommendations_expected = [
            (
                f"/opinion/{self.opinion_cluster_1.pk}/{self.opinion_cluster_1.slug}/",
                "Debbas v. Franklin",
            ),
            (
                f"/opinion/{self.opinion_cluster_2.pk}/{self.opinion_cluster_2.slug}/",
                "Howard v. Honda",
            ),
            (
                f"/opinion/{self.cluster_4.pk}/{self.cluster_4.slug}/",
                "Voutila v. Bonvini",
            ),
        ]
        self.assertEqual(
            recommendations_expected,
            recommendations_actual,
            msg="Unexpected opinion recommendations.",
        )

        citing_expected = [
            (
                f"/opinion/{self.opinion_cluster_2.pk}/{self.opinion_cluster_2.slug}/",
                f"Howard v. Honda (1895)",
            ),
            (
                f"/opinion/{self.opinion_cluster_1.pk}/{self.opinion_cluster_1.slug}/",
                "Debbas v. Franklin (2015)",
            ),
        ]
        self.assertEqual(
            citing_expected,
            citing_actual,
            msg="Unexpected opinion cited.",
        )
        await sync_to_async(self.async_client.logout)()


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
        self.r = get_redis_interface("CACHE")
        keys = self.r.keys(compose_redis_key(SEARCH_TYPES.RECAP))
        if keys:
            self.r.delete(*keys)

    def tearDown(self) -> None:
        self.delete_index("search.OpinionCluster")
        self.create_index("search.OpinionCluster")

    def test_cl_index_parent_and_child_docs_command(self):
        """Confirm the command can properly index OpinionCluster and their
        Opinions into the ES."""

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

        # Opinions are indexed.
        opinions_pks = [
            self.opinion_1.pk,
            self.opinion_2.pk,
            self.opinion_3.pk,
        ]
        for pk in opinions_pks:
            self.assertTrue(OpinionDocument.exists(id=ES_CHILD_ID(pk).OPINION))

    def test_index_parent_or_child_docs(self):
        """Confirm the command can properly index missing clusters when
        indexing only Opinions.
        """

        s = OpinionClusterDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)
        # Call cl_index_parent_and_child_docs command for OpinionCluster.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            document_type="parent",
            testing_mode=True,
        )

        # Confirm clusters are indexed but child documents not yet.
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion_cluster"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of Clusters returned."
        )

        s = OpinionClusterDocument.search()
        s = s.query("parent_id", type="opinion", id=self.opinion_cluster_1.pk)
        self.assertEqual(
            s.count(), 0, msg="Wrong number of Opinions returned."
        )

        # Call cl_index_parent_and_child_docs command for Opinion.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            document_type="child",
            testing_mode=True,
        )

        # Confirm Opinions are indexed.
        s = OpinionClusterDocument.search()
        s = s.query("parent_id", type="opinion", id=self.opinion_cluster_1.pk)
        self.assertEqual(
            s.count(), 4, msg="Wrong number of Opinions returned."
        )

        s = OpinionClusterDocument.search()
        s = s.query("parent_id", type="opinion", id=self.opinion_cluster_2.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of Opinions returned."
        )

        s = OpinionClusterDocument.search()
        s = s.query("parent_id", type="opinion", id=self.opinion_cluster_3.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of Opinions returned."
        )

    def test_opinions_indexing_missing_flag(self):
        """Confirm the command can properly index missing Opinions."""

        # Call cl_index_parent_and_child_docs command for Opinions.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

        # Remove an opinion and opinion cluster manually.
        OpinionClusterDocument.get(id=self.opinion_cluster_2.pk).delete(
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
        )
        OpinionClusterDocument.get(
            id=ES_CHILD_ID(self.opinion_2.pk).OPINION
        ).delete(refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH)

        # Confirm clusters are indexed.
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion_cluster"))
        self.assertEqual(
            s.count(), 2, msg="Wrong number of Clusters returned."
        )
        # Confirm Opinions are indexed.
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion"))
        self.assertEqual(
            s.count(), 5, msg="Wrong number of Opinions returned."
        )

        # Call cl_index_parent_and_child_docs command for Opinions passing the
        # missing flag.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            document_type="child",
            missing=True,
            testing_mode=True,
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            document_type="parent",
            missing=True,
            testing_mode=True,
        )

        # Confirm clusters are indexed.
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion_cluster"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of Clusters returned."
        )
        # Confirm Opinions are indexed.
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion"))
        self.assertEqual(
            s.count(), 6, msg="Wrong number of Opinions returned."
        )


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
            source=Docket.HARVARD,
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
                es_save_document, True, *args, **kwargs
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
            "cl.lib.es_signal_processor.update_es_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, True, *args, **kwargs
            ),
        ):
            # Update the author field in the opinion record.
            opinion.author = self.person_2
            opinion.save()
        # One update_es_document task should be called on tracked field update.
        self.reset_and_assert_task_count(expected=1)

        # Update an opinion untracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, True, *args, **kwargs
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
            "cl.lib.es_signal_processor.update_es_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, True, *args, **kwargs
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
            "cl.lib.es_signal_processor.update_es_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, True, *args, **kwargs
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
        docket = DocketFactory(court_id=self.court_2.pk, source=Docket.HARVARD)
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
                update_es_document, False, *args, **kwargs
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
                update_es_document, False, *args, **kwargs
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
        docket = DocketFactory(court_id=self.court_2.pk, source=Docket.HARVARD)
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
                update_es_document, False, *args, **kwargs
            ),
        ):
            # update docket number in parent document
            docket.docket_number = "005"
            docket.save()

        # 1 update_es_document task should be called on tracked field update,
        # exclusively for updating the OpinionClusterDocument. Since the docket
        # is not from RECAP, it should not be updated in ES.
        self.reset_and_assert_task_count(expected=1)
        cluster_doc = OpinionClusterDocument.get(opinion_cluster.pk)
        opinion_doc = OpinionDocument.get(ES_CHILD_ID(opinion.pk).OPINION)
        self.assertEqual(cluster_doc.docketNumber, "005")
        self.assertEqual(opinion_doc.docketNumber, "005")
        self.assertEqual(
            cluster_doc.date_created, opinion_cluster.date_created
        )
        self.assertEqual(opinion_doc.date_created, opinion.date_created)

        with mock.patch(
            "cl.lib.es_signal_processor.update_children_docs_by_query.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_children_docs_by_query, False, *args, **kwargs
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
        self.assertEqual(
            cluster_doc.absolute_url,
            opinion_cluster.get_absolute_url(),
        )
        self.assertEqual(
            opinion_doc.absolute_url,
            opinion_cluster.get_absolute_url(),
        )

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
        super().setUp()

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
            docket=DocketFactory(
                court=court, docket_number="123456", source=Docket.HARVARD
            ),
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
            "q": "docket number",
            "type": SEARCH_TYPES.OPINION,
        }
        response = self.client.get(
            reverse("search_feed", args=["search"]),
            params,
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
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
        xml_tree = self.assert_es_feed_content(
            node_tests, response, namespaces
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
        self.assert_es_feed_content(node_tests, response, namespaces)

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
        self.assert_es_feed_content(node_tests, response, namespaces)

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
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        node_tests = (
            ("//atom:feed/atom:entry", 5),
            ("//atom:feed/atom:entry/atom:title", 5),
            ("//atom:entry/atom:link", 10),
            ("//atom:entry/atom:published", 5),
            ("//atom:entry/atom:author/atom:name", 5),
            ("//atom:entry/atom:id", 5),
            ("//atom:entry/atom:summary", 5),
        )
        self.assert_es_feed_content(node_tests, response, namespaces)

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
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        node_tests = (
            ("//atom:feed/atom:entry", 7),
            ("//atom:feed/atom:entry/atom:title", 7),
            ("//atom:entry/atom:link", 14),
            ("//atom:entry/atom:published", 7),
            ("//atom:entry/atom:author/atom:name", 7),
            ("//atom:entry/atom:id", 7),
            ("//atom:entry/atom:summary", 7),
        )
        self.assert_es_feed_content(node_tests, response, namespaces)

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
                docket=DocketFactory(
                    court=court, docket_number="123456", source=Docket.HARVARD
                ),
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

    def test_catch_es_errors(self) -> None:
        """Can we catch es errors and just render an empy feed?"""

        # Bad syntax error.
        params = {
            "q": "Leave /:",
            "type": SEARCH_TYPES.OPINION,
        }
        response = self.client.get(
            reverse("search_feed", args=["search"]),
            params,
        )
        self.assertEqual(
            400, response.status_code, msg="Did not get a 400 OK status code."
        )
        self.assertEqual(
            "Invalid search syntax. Please check your request and try again.",
            response.content.decode(),
        )
        # Unbalanced parentheses
        params = {
            "q": "(Leave ",
            "type": SEARCH_TYPES.OPINION,
        }
        response = self.client.get(
            reverse("search_feed", args=["search"]),
            params,
        )
        self.assertEqual(
            400, response.status_code, msg="Did not get a 400 OK status code."
        )
        self.assertEqual(
            "Invalid search syntax. Please check your request and try again.",
            response.content.decode(),
        )
