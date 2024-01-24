import datetime
import operator
from collections import Counter
from functools import reduce
from unittest import mock

from django.core.management import call_command
from django.urls import reverse
from elasticsearch_dsl import Q
from lxml import html

from cl.lib.elasticsearch_utils import (
    build_es_main_query,
    build_join_es_filters,
    build_join_fulltext_queries,
)
from cl.lib.search_index_utils import solr_list
from cl.lib.test_helpers import CourtTestCase, PeopleTestCase
from cl.people_db.factories import (
    ABARatingFactory,
    EducationFactory,
    PersonFactory,
    PoliticalAffiliationFactory,
    PositionFactory,
    RaceFactory,
    SchoolFactory,
)
from cl.people_db.models import Race
from cl.search.documents import ES_CHILD_ID, PersonDocument, PositionDocument
from cl.search.factories import CourtFactory
from cl.search.models import SEARCH_TYPES
from cl.search.tasks import es_save_document, update_es_document
from cl.tests.cases import (
    CountESTasksTestCase,
    ESIndexTestCase,
    TestCase,
    TransactionTestCase,
)


class PeopleSearchTestElasticSearch(
    CourtTestCase, PeopleTestCase, ESIndexTestCase, TestCase
):
    """People search tests for Elasticsearch"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        super().setUpTestData()
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.PEOPLE,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def _test_article_count(self, params, expected_count, field_name):
        r = self.client.get("/", params)
        tree = html.fromstring(r.content.decode())
        got = len(tree.xpath("//article"))
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of search results with %s "
            "filter applied.\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            "Params were: %s" % (field_name, expected_count, got, params),
        )
        return r

    def _test_api_results_count(self, params, expected_count, field_name):
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), params
        )
        got = len(r.data["results"])
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of search results with %s "
            "filter applied.\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            "Params were: %s" % (field_name, expected_count, got, params),
        )
        return r

    @staticmethod
    def _get_meta_value(article, html_content, header):
        tree = html.fromstring(html_content)
        article = tree.xpath("//article")[article]
        for element in article.xpath('//span[@class="meta-data-header"]'):
            if element.text_content() == header:
                value_element = element.getnext()
                if (
                    value_element is not None
                    and (
                        value_element.tag == "span"
                        or value_element.tag == "time"
                    )
                    and "meta-data-value" in value_element.classes
                ):
                    value_str = value_element.text_content()
                    return " ".join(value_str.split())
        return None

    def test_index_parent_and_child_objects(self) -> None:
        """Confirm Parent object and child objects are properly indexed."""

        # Judges are indexed.
        s = PersonDocument.search()
        s = s.query(Q("match", person_child="person"))
        self.assertEqual(s.count(), 2)

        # Positions are indexed.
        position_pks = [
            self.position_2.pk,
            self.position_4.pk,
        ]
        for position_pk in position_pks:
            self.assertTrue(
                PersonDocument.exists(id=ES_CHILD_ID(position_pk).POSITION)
            )

    def test_has_child_queries(self) -> None:
        """Test the build_join_fulltext_queries has child query, it returns a
        list of parent documents where their child's documents or the parent
        document itself match the query.
        """
        # Query only over child objects, match position appointer.
        query_values = {"position": ["appointer"]}
        s = PersonDocument.search()
        has_child_queries = build_join_fulltext_queries(
            query_values, [], "Bill"
        )
        s = s.query(has_child_queries)
        response = s.execute().to_dict()
        self.assertEqual(s.count(), 2)

        for hit in response["hits"]["hits"]:
            self.assertIn(
                "Bill",
                hit["inner_hits"]["text_query_inner_position"][0].appointer,
            )

        person = PersonFactory.create(name_first="John American")
        position_5 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=self.court_1,
            date_start=datetime.date(2015, 12, 14),
            predecessor=self.person_2,
            appointer=self.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=person,
            how_selected="e_part",
            nomination_process="fed_senate",
        )
        person.delete()

    def test_has_child_filters(self) -> None:
        """Test the build_join_es_filters has child filter, it returns a
        list of parent documents where their child's documents or the parent
        document itself match the filter.
        """
        position_5 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=self.court_2,
            date_start=datetime.date(2020, 12, 14),
            predecessor=self.person_3,
            appointer=self.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=self.person_3,
            how_selected="e_part",
            nomination_process="fed_senate",
        )

        # Query by parent field dob_state.
        cd = {
            "dob_state": "NY",
            "type": SEARCH_TYPES.PEOPLE,
        }
        s = PersonDocument.search()
        has_child_filters = build_join_es_filters(cd)
        s = s.filter(reduce(operator.iand, has_child_filters))
        self.assertEqual(s.count(), 2)

        # Query by parent field dob_state and child field selection_method.
        cd = {
            "dob_city": "Brookyln",
            "selection_method": "e_part",
            "type": SEARCH_TYPES.PEOPLE,
        }
        s = PersonDocument.search()
        has_child_filters = build_join_es_filters(cd)
        s = s.filter(reduce(operator.iand, has_child_filters))
        self.assertEqual(s.count(), 1)

        position_5.delete()

    def test_sorting(self) -> None:
        """Can we do sorting on various fields?"""
        sort_fields = [
            "score desc",
            "name_reverse asc",
            "dob desc,name_reverse asc",
            "dod desc,name_reverse asc",
            "random_123 desc",
        ]
        for sort_field in sort_fields:
            r = self.client.get(
                "/", {"type": SEARCH_TYPES.PEOPLE, "order_by": sort_field}
            )
            self.assertNotIn(
                "an error",
                r.content.decode().lower(),
                msg=f"Got an error when doing a judge search ordered by {sort_field}",
            )

    def test_name_field(self) -> None:
        # Frontend
        params = {"type": SEARCH_TYPES.PEOPLE, "name": "judith"}
        self._test_article_count(params, 2, "name")
        # API
        self._test_api_results_count(params, 2, "name")

    def test_court_filter(self) -> None:
        # Frontend
        params = {"type": SEARCH_TYPES.PEOPLE, "court": "ca1"}
        self._test_article_count(params, 1, "court")

        # API
        self._test_api_results_count(params, 1, "court")

        # Frontend
        params = {"type": SEARCH_TYPES.PEOPLE, "court": "scotus"}
        self._test_article_count(params, 0, "court")
        # API
        self._test_api_results_count(params, 0, "court")

        # Frontend
        params = {"type": SEARCH_TYPES.PEOPLE, "court": "scotus ca1"}
        self._test_article_count(params, 1, "court")
        # API
        self._test_api_results_count(params, 1, "court")

    def test_dob_filters(self) -> None:
        # Frontend
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "born_after": "1941",
            "born_before": "1943",
        }
        self._test_article_count(params, 1, "born_{before|after}")
        # API
        self._test_api_results_count(params, 1, "born_{before|after}")

        # Are reversed dates corrected?
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "born_after": "1943",
            "born_before": "1941",
        }
        # Frontend
        self._test_article_count(params, 1, "born_{before|after}")
        # API
        self._test_api_results_count(params, 1, "born_{before|after}")

        # Just one filter, but Judy is older than this.
        params = {"type": SEARCH_TYPES.PEOPLE, "born_after": "1946"}
        # Frontend
        self._test_article_count(params, 0, "born_{before|after}")
        # API
        self._test_api_results_count(
            params,
            0,
            "born_{before|after}",
        )

    def test_birth_location(self) -> None:
        """Can we filter by city and state?"""

        params = {"type": SEARCH_TYPES.PEOPLE, "dob_city": "brookyln"}
        # Frontend
        self._test_article_count(
            params,
            1,
            "dob_city",
        )
        # API
        self._test_api_results_count(params, 1, "dob_city")

        params = {"type": SEARCH_TYPES.PEOPLE, "dob_city": "brooklyn2"}
        # Frontend
        self._test_article_count(
            params,
            0,
            "dob_city",
        )
        # API
        self._test_api_results_count(
            params,
            0,
            "dob_city",
        )

        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "dob_city": "brookyln",
            "dob_state": "NY",
        }
        # Frontend
        self._test_article_count(params, 1, "dob_city")
        # API
        self._test_api_results_count(params, 1, "dob_city")

        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "dob_city": "brookyln",
            "dob_state": "OK",
        }
        # Frontend
        self._test_article_count(
            params,
            0,
            "dob_city",
        )
        # API
        self._test_api_results_count(params, 0, "dob_city")

    def test_schools_filter(self) -> None:
        params = {"type": SEARCH_TYPES.PEOPLE, "school": "american"}
        # Frontend
        self._test_article_count(params, 1, "school")
        # API
        self._test_api_results_count(params, 1, "school")

        params = {"type": SEARCH_TYPES.PEOPLE, "school": "pitzer"}
        # Frontend
        self._test_article_count(params, 0, "school")
        # API
        self._test_api_results_count(params, 0, "school")

    def test_appointer_filter(self) -> None:
        params = {"type": SEARCH_TYPES.PEOPLE, "appointer": "clinton"}
        # Frontend
        self._test_article_count(
            params,
            2,
            "appointer",
        )
        # API
        self._test_api_results_count(params, 2, "appointer")

        params = {"type": SEARCH_TYPES.PEOPLE, "appointer": "obama"}
        # Frontend
        self._test_article_count(params, 0, "appointer")
        # API
        self._test_api_results_count(params, 0, "appointer")

    def test_selection_method_filter(self) -> None:
        params = {"type": SEARCH_TYPES.PEOPLE, "selection_method": "e_part"}
        # Frontend
        self._test_article_count(params, 1, "selection_method")
        # API
        self._test_api_results_count(params, 1, "selection_method")

        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "selection_method": "e_non_part",
        }
        # Frontend
        self._test_article_count(params, 0, "selection_method")
        # API
        self._test_api_results_count(
            params,
            0,
            "selection_method",
        )

    def test_political_affiliation_filter(self) -> None:
        params = {"type": SEARCH_TYPES.PEOPLE, "political_affiliation": "d"}
        # Frontend
        self._test_article_count(params, 1, "political_affiliation")
        # API
        self._test_api_results_count(params, 1, "political_affiliation")

        params = {"type": SEARCH_TYPES.PEOPLE, "political_affiliation": "r"}
        # Frontend
        self._test_article_count(params, 0, "political_affiliation")
        # API
        self._test_api_results_count(params, 0, "political_affiliation")

    def test_search_query_and_order(self) -> None:
        # Search by name and relevance result order.
        # Frontend
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "Judith Sheindlin",
            "order_by": "score desc",
        }
        r = self._test_article_count(params, 2, "q")
        self.assertTrue(
            r.content.decode().index("Olivia")
            < r.content.decode().index("Susan"),
            msg="'Susan' should come AFTER 'Olivia'.",
        )
        # API
        self._test_api_results_count(params, 2, "q")

        # Search by name and dob order.
        # Frontend
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "Judith Sheindlin",
            "order_by": "dob desc,name_reverse asc",
        }
        r = self._test_article_count(params, 2, "q")
        self.assertTrue(
            r.content.decode().index("Olivia")
            < r.content.decode().index("Susan"),
            msg="'Susan' should come AFTER 'Olivia'.",
        )
        # API
        self._test_api_results_count(params, 2, "q")

        # Search by name and filter.
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "Judith Sheindlin",
            "school": "american",
        }
        # Frontend
        self._test_article_count(params, 1, "q + school")
        # API
        self._test_api_results_count(params, 1, "q + school")

    def test_advanced_search(self) -> None:
        # Search by advanced field.
        # Frontend
        params = {"type": SEARCH_TYPES.PEOPLE, "q": "name:Judith Sheindlin"}
        self._test_article_count(params, 2, "q")
        # API
        self._test_api_results_count(params, 2, "q")

        # Combine fields of the parent document in advanced search.
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "name:Judith Sheindlin AND dob_city:Queens",
        }
        # Frontend
        r = self._test_article_count(
            params,
            1,
            "q",
        )
        self.assertIn("Olivia", r.content.decode())
        # API
        r = self._test_api_results_count(params, 1, "q")
        self.assertIn("Olivia", r.content.decode())

        # Combine fields from the parent and the child mapping in advanced search.
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "appointer:Clinton AND dob_city:Queens",
        }
        r = self._test_article_count(
            params,
            1,
            "q",
        )
        self.assertIn("Olivia", r.content.decode())
        # API
        r = self._test_api_results_count(params, 1, "q")
        self.assertIn("Olivia", r.content.decode())

        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "appointer:Clinton AND races:(Black or African American)",
        }
        r = self._test_article_count(
            params,
            1,
            "q",
        )
        self.assertIn("Judith", r.content.decode())
        # API
        r = self._test_api_results_count(params, 1, "q")
        self.assertIn("Judith", r.content.decode())

        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "appointer:Clinton AND political_affiliation_id:i",
        }
        r = self._test_article_count(
            params,
            1,
            "q",
        )
        self.assertIn("Judith", r.content.decode())
        # API
        r = self._test_api_results_count(params, 1, "q")
        self.assertIn("Judith", r.content.decode())

        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "selection_method_id:e_part AND dob_state_id:NY",
        }
        r = self._test_article_count(
            params,
            1,
            "q",
        )
        self.assertIn("Judith", r.content.decode())
        # API
        r = self._test_api_results_count(params, 1, "q")
        self.assertIn("Judith", r.content.decode())

    def test_parent_document_fields_on_search_results(self):
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "name:Judith Sheindlin Susan",
        }
        r = self._test_article_count(params, 1, "q")

        born = self._get_meta_value(0, r.content.decode(), "Born:")
        self.assertEqual(born, "October 21, 1942 in Brookyln, NY")

        deceased = self._get_meta_value(0, r.content.decode(), "Deceased:")
        self.assertEqual(deceased, "November 25, 2020")

        political_affiliations = self._get_meta_value(
            0, r.content.decode(), "Political Affiliations:"
        )
        self.assertEqual(
            political_affiliations,
            self.political_affiliation_2.get_political_party_display(),
        )

        aba_ratings = self._get_meta_value(
            0, r.content.decode(), "ABA Ratings:"
        )
        self.assertEqual(aba_ratings, self.aba_rating_1.get_rating_display())

    def test_merge_unavailable_fields_on_parent_document(self):
        """Confirm unavailable ES fields are properly merged from DB in fronted"""
        params = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "name:Judith Sheindlin Olivia",
        }
        r = self._test_article_count(params, 1, "q")

        appointers = self._get_meta_value(0, r.content.decode(), "Appointers:")
        self.assertEqual(appointers, self.person_1.name_full_reverse)

        selection_methods = self._get_meta_value(
            0, r.content.decode(), "Selection Methods:"
        )
        self.assertEqual(
            selection_methods, self.position_4.get_how_selected_display()
        )

        selection_methods = self._get_meta_value(
            0, r.content.decode(), "Selection Methods:"
        )
        self.assertEqual(
            selection_methods, self.position_4.get_how_selected_display()
        )

        predecessors = self._get_meta_value(
            0, r.content.decode(), "Predecessors:"
        )
        self.assertEqual(predecessors, self.person_3.name_full_reverse)

        person = PersonFactory.create(name_first="John American")
        position_5 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=self.court_1,
            date_start=datetime.date(2015, 12, 14),
            predecessor=self.person_2,
            appointer=self.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=person,
            how_selected="e_part",
            nomination_process="fed_senate",
        )

        position_6 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=self.court_1,
            date_start=datetime.date(2015, 12, 14),
            predecessor=self.person_2,
            appointer=self.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="clerk",
            person=self.person_3,
            supervisor=person,
            how_selected="e_part",
            nomination_process="fed_senate",
        )

        r = self._test_article_count(params, 1, "q")
        supervisors = self._get_meta_value(
            0, r.content.decode(), "Supervisors:"
        )
        self.assertEqual(supervisors, position_6.supervisor.name_full_reverse)

        position_6.delete()
        person.delete()

    def test_has_child_queries_combine_filters(self) -> None:
        """Test confirm if we can combine multiple has child filter inner hits
        into a single dict.
        """
        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "appointer": "clinton",
            "selection_method": "e_part",
            "order_by": "name_reverse asc",
        }
        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        # Main result.
        # Person 3 Judith Susan Sheindlin II
        #    Inner hits:
        #       Position 2
        #          Appointer Bill Clinton.
        response = s.execute().to_dict()
        self.assertEqual(s.count(), 1)
        self.assertEqual(
            1,
            len(
                response["hits"]["hits"][0]["inner_hits"][
                    "filter_inner_position"
                ]["hits"]["hits"]
            ),
        )
        self.assertIn(
            "Bill",
            response["hits"]["hits"][0]["inner_hits"]["filter_inner_position"][
                "hits"
            ]["hits"][0]["_source"]["appointer"],
        )
        with self.captureOnCommitCallbacks(execute=True):
            appointer = PersonFactory.create(
                name_first="Obama", name_last="Clinton"
            )
            position_obama = PositionFactory.create(
                date_granularity_start="%Y-%m-%d",
                date_start=datetime.date(1993, 1, 20),
                date_retirement=datetime.date(2001, 1, 20),
                termination_reason="retire_mand",
                position_type="pres",
                person=appointer,
                how_selected="e_part",
            )
            person_2_position = PositionFactory.create(
                date_granularity_start="%Y-%m-%d",
                court=self.court_1,
                date_start=datetime.date(2015, 12, 14),
                predecessor=self.person_3,
                appointer=position_obama,
                judicial_committee_action="no_rep",
                termination_reason="retire_mand",
                position_type="c-jud",
                person=self.person_2,
                how_selected="e_part",
                nomination_process="fed_senate",
            )

        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        response = s.execute().to_dict()
        # Main result. All Courts
        # Person 3 Judith Susan Sheindlin II
        #    Inner hits:
        #       Position 2
        #          Appointer Bill Clinton.
        #       Position 5
        #          Appointer Bill Obama

        self.assertEqual(s.count(), 1)
        self.assertEqual(
            2,
            len(
                response["hits"]["hits"][0]["inner_hits"][
                    "filter_inner_position"
                ]["hits"]["hits"]
            ),
        )
        self.assertIn(
            "Bill",
            response["hits"]["hits"][0]["inner_hits"]["filter_inner_position"][
                "hits"
            ]["hits"][0]["_source"]["appointer"],
        )
        self.assertIn(
            "Obama",
            response["hits"]["hits"][0]["inner_hits"]["filter_inner_position"][
                "hits"
            ]["hits"][1]["_source"]["appointer"],
        )

        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "appointer": "clinton",
            "selection_method": "e_part",
            "court": "ca5",
            "order_by": "name_reverse asc",
        }
        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        # Main result. Court that doesn't belong any of the positions
        # No results
        self.assertEqual(s.count(), 0)

        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "appointer": "clinton",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        # Two main results, matched by has_child.
        # [parent_filter, has_child_filters[]]
        # Only 1 result.
        self.assertEqual(s.count(), 2)

        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "appointer": "clinton",
            "name": "olivia",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        # Main result. Combine has child filters and parent filter.
        # Must:
        # [parent_filter, has_child_filters[]]
        # Only 1 result.
        self.assertEqual(s.count(), 1)

        # Include Education.
        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "appointer": "clinton",
            "school": "american",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        self.assertEqual(s.count(), 1)

        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "clinton Olivia",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        # Two main results, matched by string queries on parent and position
        self.assertEqual(s.count(), 2)

        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "clinton OR Olivia",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        # Two main results, matched by string queries on parent and position
        self.assertEqual(s.count(), 2)

        # Include Education.
        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "appointer": "obama",
            "q": "clinton",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        self.assertEqual(s.count(), 1)
        person_2_position.delete()
        position_obama.delete()
        appointer.delete()

    def test_results_highlights(self) -> None:
        """Test highlighting for Judge results."""

        # name query highlights in text query.
        params = {
            "q": "Sheindlin Olivia",
            "type": SEARCH_TYPES.PEOPLE,
            "order_by": "score desc",
        }
        r = self._test_article_count(params, 1, "q")
        self.assertIn("<mark>Sheindlin</mark>", r.content.decode())
        self.assertIn("<mark>Olivia</mark>", r.content.decode())

        # name.exact query highlights in text query.
        params = {
            "q": '"Sheindlin" Judith',
            "type": SEARCH_TYPES.PEOPLE,
            "order_by": "score desc",
        }
        r = self._test_article_count(params, 2, "q")
        self.assertIn("<mark>Sheindlin</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Sheindlin</mark>"), 2)
        self.assertEqual(r.content.decode().count("<mark>Judith</mark>"), 2)

        # name highlights in filter.
        params = {
            "name": "Sheindlin",
            "type": SEARCH_TYPES.PEOPLE,
            "order_by": "score desc",
        }
        r = self._test_article_count(params, 2, "q")
        self.assertIn("<mark>Sheindlin</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Sheindlin</mark>"), 2)

        # dob_city highlights
        params = {
            "dob_city": "Queens",
            "type": SEARCH_TYPES.PEOPLE,
            "order_by": "score desc",
        }
        r = self._test_article_count(params, 1, "q")
        self.assertIn("<mark>Queens</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Queens</mark>"), 1)

        # dob_state highlights
        params = {
            "dob_state": "NY",
            "type": SEARCH_TYPES.PEOPLE,
            "order_by": "score desc",
        }
        r = self._test_article_count(params, 2, "q")
        self.assertIn("<mark>NY</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>NY</mark>"), 2)

    def test_api_fields(self) -> None:
        """Confirm the search API for People return the expected fields."""

        params = {"type": SEARCH_TYPES.PEOPLE, "q": "Susan"}
        r = self._test_api_results_count(params, 1, "API")
        keys_to_check = [
            "aba_rating",
            "absolute_url",
            "alias",
            "alias_ids",
            "appointer",
            "court",
            "court_exact",
            "date_confirmation",
            "date_elected",
            "date_granularity_dob",
            "date_granularity_dod",
            "date_granularity_start",
            "date_granularity_termination",
            "date_hearing",
            "date_judicial_committee_action",
            "date_nominated",
            "date_recess_appointment",
            "date_referred_to_judicial_committee",
            "date_retirement",
            "date_start",
            "date_termination",
            "dob",
            "dob_city",
            "dob_state",
            "dob_state_id",
            "dod",
            "fjc_id",
            "gender",
            "id",
            "judicial_committee_action",
            "name",
            "name_reverse",
            "nomination_process",
            "political_affiliation",
            "political_affiliation_id",
            "position_type",
            "predecessor",
            "races",
            "religion",
            "school",
            "selection_method",
            "selection_method_id",
            "snippet",
            "supervisor",
            "termination_reason",
            "timestamp",
        ]
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, 46)
        for key in keys_to_check:
            self.assertTrue(
                key in r.data["results"][0],
                msg=f"Key {key} not found in the result object.",
            )

    def test_merge_unavailable_fields_api(self) -> None:
        """Confirm unavailable ES fields are properly merged from DB in the API"""
        with self.captureOnCommitCallbacks(execute=True):
            person = PersonFactory.create(name_first="John American")
            position_5 = PositionFactory.create(
                date_granularity_start="%Y-%m-%d",
                court=self.court_1,
                date_start=datetime.date(2015, 12, 14),
                predecessor=self.person_3,
                appointer=self.position_1,
                judicial_committee_action="no_rep",
                termination_reason="retire_mand",
                position_type="c-jud",
                person=person,
                how_selected="e_part",
                nomination_process="fed_senate",
            )

            position_6 = PositionFactory.create(
                date_granularity_start="%Y-%m-%d",
                court=self.court_2,
                date_start=datetime.date(2015, 12, 14),
                predecessor=self.person_2,
                appointer=self.position_1,
                judicial_committee_action="no_rep",
                termination_reason="retire_mand",
                position_type="clerk",
                person=self.person_2,
                supervisor=person,
                date_nominated=datetime.date(2015, 11, 14),
                date_recess_appointment=datetime.date(2016, 11, 14),
                date_referred_to_judicial_committee=datetime.date(
                    2017, 11, 14
                ),
                date_judicial_committee_action=datetime.date(2017, 10, 14),
                date_confirmation=datetime.date(2017, 10, 11),
                date_hearing=datetime.date(2017, 10, 16),
                date_retirement=datetime.date(2020, 10, 10),
                date_termination=datetime.date(2019, 10, 24),
                date_granularity_termination="%Y-%m-%d",
                how_selected="a_legis",
                nomination_process="fed_senate",
            )

        params = {"type": SEARCH_TYPES.PEOPLE, "q": "Susan"}

        # API
        r = self._test_api_results_count(params, 1, "API")

        # Compare whether every field in the results contains the same content,
        # regardless of the order.
        self.assertEqual(
            Counter(r.data["results"][0]["court"]),
            Counter(
                [position_6.court.short_name, self.position_2.court.short_name]
            ),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["court_exact"]),
            Counter([self.position_2.court.pk, position_6.court.pk]),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["position_type"]),
            Counter(
                [
                    self.position_2.get_position_type_display(),
                    position_6.get_position_type_display(),
                ]
            ),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["appointer"]),
            Counter(
                [
                    self.position_2.appointer.person.name_full_reverse,
                    position_6.appointer.person.name_full_reverse,
                ]
            ),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["supervisor"]),
            Counter([position_6.supervisor.name_full_reverse]),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["predecessor"]),
            Counter(
                [
                    self.position_2.predecessor.name_full_reverse,
                    position_6.predecessor.name_full_reverse,
                ]
            ),
        )

        positions = self.person_2.positions.all()
        self.assertEqual(
            Counter(r.data["results"][0]["date_nominated"]),
            Counter(solr_list(positions, "date_nominated")),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_elected"]),
            Counter(solr_list(positions, "date_elected")),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_recess_appointment"]),
            Counter(solr_list(positions, "date_recess_appointment")),
        )
        self.assertEqual(
            Counter(
                r.data["results"][0]["date_referred_to_judicial_committee"]
            ),
            Counter(
                solr_list(positions, "date_referred_to_judicial_committee")
            ),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_judicial_committee_action"]),
            Counter(solr_list(positions, "date_judicial_committee_action")),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_hearing"]),
            Counter(solr_list(positions, "date_hearing")),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_confirmation"]),
            Counter(solr_list(positions, "date_confirmation")),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_start"]),
            Counter(solr_list(positions, "date_start")),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_granularity_start"]),
            Counter(
                [
                    self.position_2.date_granularity_start,
                    self.position_3.date_granularity_start,
                    position_6.date_granularity_start,
                ]
            ),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_retirement"]),
            Counter(solr_list(positions, "date_retirement")),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_termination"]),
            Counter(solr_list(positions, "date_termination")),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["date_granularity_termination"]),
            Counter([position_6.date_granularity_termination]),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["judicial_committee_action"]),
            Counter(
                [
                    self.position_2.get_judicial_committee_action_display(),
                    position_6.get_judicial_committee_action_display(),
                ]
            ),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["nomination_process"]),
            Counter(
                [
                    self.position_2.get_nomination_process_display(),
                    position_6.get_nomination_process_display(),
                ]
            ),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["selection_method"]),
            Counter(
                [
                    self.position_2.get_how_selected_display(),
                    position_6.get_how_selected_display(),
                ]
            ),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["selection_method_id"]),
            Counter([self.position_2.how_selected, position_6.how_selected]),
        )
        self.assertEqual(
            Counter(r.data["results"][0]["termination_reason"]),
            Counter(
                [
                    self.position_2.get_termination_reason_display(),
                    position_6.get_termination_reason_display(),
                ]
            ),
        )

        position_5.delete()
        position_6.delete()
        person.delete()


class IndexJudgesPositionsCommandTest(
    CourtTestCase, PeopleTestCase, ESIndexTestCase, TestCase
):
    """test_cl_index_parent_and_child_docs_command tests for Elasticsearch"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        super().setUpTestData()
        cls.delete_index("people_db.Person")
        cls.create_index("people_db.Person")

    def test_cl_index_parent_and_child_docs_command(self):
        """Confirm the command can properly index Judges and their positions
        into the ES."""

        s = PersonDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)

        # Call cl_index_parent_and_child_docs command.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.PEOPLE,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

        s = PersonDocument.search()
        s = s.query(Q("match", person_child="person"))
        self.assertEqual(s.count(), 2, msg="Wrong number of judges returned.")

        s = PersonDocument.search()
        s = s.query(Q("match", person_child="position"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of positions returned."
        )

        # Positions are indexed.
        position_pks = [
            self.position_2.pk,
            self.position_4.pk,
            self.position_3.pk,
        ]
        for position_pk in position_pks:
            self.assertTrue(
                PositionDocument.exists(id=ES_CHILD_ID(position_pk).POSITION)
            )

        s = PersonDocument.search()
        s = s.query("parent_id", type="position", id=self.person_2.pk)
        self.assertEqual(s.count(), 2)

        s = PersonDocument.search()
        s = s.query("parent_id", type="position", id=self.person_3.pk)
        self.assertEqual(s.count(), 1)


class PeopleIndexingTest(
    CountESTasksTestCase, ESIndexTestCase, TransactionTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rebuild_index("people_db.Person")

    def setUp(self):
        super().setUp()
        self.court_1 = CourtFactory(
            id="ca1",
            full_name="First Circuit",
            citation_string="1st Cir.",
        )
        self.court_2 = CourtFactory(
            id="test",
            full_name="Testing Supreme Court",
            citation_string="Test",
        )

        w_query = Race.objects.filter(race="w")
        b_query = Race.objects.filter(race="b")
        self.w_race = (
            w_query.first() if w_query.exists() else RaceFactory(race="w")
        )
        self.b_race = (
            b_query.first() if b_query.exists() else RaceFactory(race="b")
        )

        self.person_1 = PersonFactory.create(
            gender="m",
            name_first="Bill",
            name_last="Clinton",
        )
        self.person_1.race.add(self.w_race)
        self.position_1 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(1993, 1, 20),
            date_retirement=datetime.date(2001, 1, 20),
            termination_reason="retire_mand",
            position_type="pres",
            person=self.person_1,
            how_selected="e_part",
        )

        self.person_2 = PersonFactory.create(
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
        self.person_2.race.add(self.w_race)
        self.person_2.race.add(self.b_race)

        self.person_3 = PersonFactory.create(
            gender="f",
            name_first="Sheindlin",
            name_last="Judith",
            date_dob=datetime.date(1945, 11, 20),
            date_granularity_dob="%Y-%m-%d",
            name_middle="Olivia",
            dob_city="Queens",
            dob_state="NY",
        )
        self.person_3.race.add(self.w_race)
        PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=self.court_2,
            date_start=datetime.date(2020, 12, 14),
            predecessor=self.person_3,
            appointer=self.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=self.person_3,
            how_selected="a_legis",
            nomination_process="fed_senate",
        )
        self.school_1 = SchoolFactory(name="New York Law School")
        self.education_3 = EducationFactory(
            degree_level="ba",
            person=self.person_3,
            school=self.school_1,
        )
        self.political_affiliation_3 = PoliticalAffiliationFactory.create(
            political_party="i",
            source="b",
            date_start=datetime.date(2015, 12, 14),
            person=self.person_3,
            date_granularity_start="%Y-%m-%d",
        )

    def test_index_all_person_positions(self) -> None:
        """Confirm we can index all the person positions in ES after a
        judiciary position is created for the person.
        """

        person = PersonFactory.create(
            gender="f",
            name_first="Ava",
            name_last="Wilson",
            date_dob=datetime.date(1942, 10, 21),
            date_dod=datetime.date(2020, 11, 25),
            date_granularity_dob="%Y-%m-%d",
            date_granularity_dod="%Y-%m-%d",
        )
        person_id = person.pk
        no_jud_position = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(2015, 12, 14),
            organization_name="Pants, Inc.",
            job_title="Corporate Lawyer",
            position_type=None,
            person=person,
        )

        # At this point there is no judiciary position for person, so the
        # person and no_jud_position are not indexed yet.
        self.assertFalse(PersonDocument.exists(id=person_id))
        self.assertFalse(
            PersonDocument.exists(id=ES_CHILD_ID(no_jud_position.pk).POSITION)
        )

        # Add a judiciary position:
        jud_position = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(2015, 12, 14),
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=person,
            how_selected="e_part",
            nomination_process="fed_senate",
            date_elected=datetime.date(2015, 11, 12),
        )
        jud_position_id = jud_position.pk

        # Confirm now the Person is indexed in ES.
        self.assertTrue(PersonDocument.exists(id=person_id))
        # Also the judiciary position is indexed.
        self.assertTrue(
            PositionDocument.exists(id=ES_CHILD_ID(jud_position_id).POSITION)
        )
        # Previous no judiciary positions should also been indexed now.
        self.assertTrue(
            PositionDocument.exists(
                id=ES_CHILD_ID(no_jud_position.pk).POSITION
            )
        )

        # Upcoming non-judiciary and judiciary positions should be indexed.
        no_jud_position_2 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(2015, 12, 14),
            organization_name="Pants, Inc.",
            job_title="Corporate Lawyer",
            position_type=None,
            person=person,
        )
        no_jud_position_2_id = no_jud_position_2.pk
        self.assertTrue(
            PositionDocument.exists(
                id=ES_CHILD_ID(no_jud_position_2_id).POSITION
            )
        )

        jud_position_2 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(2015, 12, 14),
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=person,
            how_selected="e_part",
            nomination_process="fed_senate",
            date_elected=datetime.date(2015, 11, 12),
        )
        jud_position_2_id = jud_position_2.pk
        self.assertTrue(
            PositionDocument.exists(id=ES_CHILD_ID(jud_position_2_id).POSITION)
        )

        # If Judge Positions are removed and the Person is not a Judge anymore,
        # remove it from the index with all the other positions.

        jud_position.delete()
        jud_position_2.delete()
        self.assertFalse(
            PositionDocument.exists(id=ES_CHILD_ID(jud_position_id).POSITION)
        )
        self.assertFalse(
            PositionDocument.exists(id=ES_CHILD_ID(jud_position_2_id).POSITION)
        )

        # Non-judiciary positions and the Person should be also removed from
        # the index
        self.assertFalse(
            PositionDocument.exists(
                id=ES_CHILD_ID(no_jud_position_2_id).POSITION
            )
        )
        self.assertFalse(PersonDocument.exists(id=person_id))

        # Avoid indexing Person if a reverse related for a non-judge Person
        # is added or updated.
        aba_rating = ABARatingFactory(
            rating="nq",
            person=person,
            year_rated="2015",
        )
        self.assertFalse(PersonDocument.exists(id=person_id))
        aba_rating.year_rated = "2023"
        aba_rating.save()
        self.assertFalse(PersonDocument.exists(id=person_id))

        person.delete()

    def test_remove_parent_child_objects_from_index(self) -> None:
        """Confirm join child objects are removed from the index when the
        parent objects is deleted.
        """
        person = PersonFactory.create(name_first="John Deer")
        pos_1 = PositionFactory.create(
            person=person,
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(1993, 1, 20),
            date_retirement=datetime.date(2001, 1, 20),
            termination_reason="retire_mand",
            position_type="c-jud",
            how_selected="e_part",
            nomination_process="fed_senate",
        )
        PoliticalAffiliationFactory.create(person=person)

        person_pk = person.pk
        pos_1_pk = pos_1.pk
        # Person instance is indexed.
        self.assertTrue(PersonDocument.exists(id=person_pk))
        # Position instance is indexed.
        self.assertTrue(
            PersonDocument.exists(id=ES_CHILD_ID(pos_1_pk).POSITION)
        )

        # Confirm documents can be updated in the ES index.
        person.name_first = "John Debbas"
        person.save()

        court = CourtFactory()
        pos_1.court = court
        pos_1.save()

        person_doc = PersonDocument.get(id=person.pk)
        self.assertIn("Debbas", person_doc.name)

        position_doc = PersonDocument.get(id=ES_CHILD_ID(pos_1_pk).POSITION)
        self.assertEqual(court.pk, position_doc.court_exact)

        # Delete person instance; it should be removed from the index along
        # with its child documents.
        person.delete()

        # Person document should be removed.
        self.assertFalse(PersonDocument.exists(id=person_pk))
        # Position document is removed.
        self.assertFalse(
            PersonDocument.exists(id=ES_CHILD_ID(pos_1_pk).POSITION)
        )

    def test_remove_nested_objects_from_index(self) -> None:
        """Confirm that child objects are removed from the index when they are
        deleted independently of their parent object
        """

        person = PersonFactory.create(name_first="John Deer")
        pos_1 = PositionFactory.create(
            person=person,
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(1993, 1, 20),
            date_retirement=datetime.date(2001, 1, 20),
            termination_reason="retire_mand",
            position_type="c-jud",
            how_selected="e_part",
            nomination_process="fed_senate",
        )
        PositionFactory.create(
            person=person,
            position_type="c-jud",
            how_selected="e_part",
            nomination_process="fed_senate",
        )
        PoliticalAffiliationFactory.create(person=person)

        person_pk = person.pk
        pos_1_pk = pos_1.pk
        # Person instance is indexed.
        self.assertTrue(PersonDocument.exists(id=person_pk))
        # Position instance is indexed.
        self.assertTrue(
            PersonDocument.exists(id=ES_CHILD_ID(pos_1_pk).POSITION)
        )

        # Delete pos_1 and education, keep the parent person instance.
        pos_1.delete()

        # Person instance still exists.
        self.assertTrue(PersonDocument.exists(id=person_pk))

        # Position object is removed
        self.assertFalse(
            PersonDocument.exists(id=ES_CHILD_ID(pos_1_pk).POSITION)
        )
        person.delete()

    def test_update_related_documents(self):
        person = PersonFactory.create(
            name_first="John American",
            date_granularity_dob="%Y-%m-%d",
            date_granularity_dod="%Y-%m-%d",
            date_dob=datetime.date(1940, 10, 21),
            date_dod=datetime.date(2021, 11, 25),
        )
        person.race.add(self.w_race)
        po_af = PoliticalAffiliationFactory.create(
            political_party="i",
            source="b",
            date_start=datetime.date(2015, 12, 14),
            person=person,
            date_granularity_start="%Y-%m-%d",
        )

        person_2 = PersonFactory.create(name_first="Barack Obama")
        position_5 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=self.court_1,
            date_start=datetime.date(2015, 12, 14),
            predecessor=self.person_2,
            appointer=self.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=person,
            how_selected="e_part",
            nomination_process="fed_senate",
        )

        position_5_1 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=self.court_1,
            date_start=datetime.date(2015, 12, 14),
            predecessor=self.person_2,
            appointer=self.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=person_2,
            how_selected="e_part",
            nomination_process="fed_senate",
        )

        position_6 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=self.court_1,
            date_start=datetime.date(2015, 12, 14),
            predecessor=self.person_2,
            appointer=self.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="clerk",
            person=self.person_3,
            supervisor=person,
            how_selected="e_part",
            nomination_process="fed_senate",
        )

        # Confirm initial values are properly indexed.
        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        name_full_reverse = person.name_full_reverse
        self.assertEqual(name_full_reverse, pos_doc.supervisor)
        self.assertEqual(self.person_2.name_full_reverse, pos_doc.predecessor)
        self.assertEqual(
            self.position_1.person.name_full_reverse, pos_doc.appointer
        )

        # Check for races, political_affiliation_idk, dod and dob, initial values.
        person_doc = PersonDocument.get(id=person.pk)
        self.assertEqual(
            Counter([self.w_race.get_race_display()]),
            Counter(person_doc.races),
        )
        self.assertEqual(person.date_dob, person_doc.dob.date())
        self.assertEqual(person.date_dod, person_doc.dod.date())
        self.assertEqual(["i"], person_doc.political_affiliation_id)

        pos_5_doc = PositionDocument.get(
            id=ES_CHILD_ID(position_5.pk).POSITION
        )
        self.assertEqual(
            Counter([self.w_race.get_race_display()]), Counter(pos_5_doc.races)
        )
        self.assertEqual(person.date_dob, pos_5_doc.dob.date())
        self.assertEqual(person.date_dod, pos_5_doc.dod.date())
        self.assertEqual(["i"], pos_5_doc.political_affiliation_id)

        # Remove political affiliation:
        po_af.delete()

        # Add a new race and compare person and position fields.
        person.race.add(self.b_race)
        person_doc = PersonDocument.get(id=person.pk)
        self.assertEqual(
            Counter(
                [
                    self.w_race.get_race_display(),
                    self.b_race.get_race_display(),
                ]
            ),
            Counter(person_doc.races),
        )
        # political_affiliation_id is removed from person doc.
        self.assertEqual(None, person_doc.political_affiliation_id)
        pos_5_doc = PositionDocument.get(
            id=ES_CHILD_ID(position_5.pk).POSITION
        )
        self.assertEqual(
            Counter(
                [
                    self.w_race.get_race_display(),
                    self.b_race.get_race_display(),
                ]
            ),
            Counter(pos_5_doc.races),
        )
        # political_affiliation_id is removed form position doc.
        self.assertEqual(None, pos_5_doc.political_affiliation_id)

        # Update dob and dod:
        person.date_dob = datetime.date(1940, 10, 25)
        person.date_dod = datetime.date(2021, 11, 25)
        person.save()

        person_doc = PersonDocument.get(id=person.pk)
        pos_5_doc = PositionDocument.get(
            id=ES_CHILD_ID(position_5.pk).POSITION
        )
        self.assertEqual(person.date_dob, person_doc.dob.date())
        self.assertEqual(person.date_dod, person_doc.dod.date())
        self.assertEqual(person.date_dob, pos_5_doc.dob.date())
        self.assertEqual(person.date_dod, pos_5_doc.dod.date())

        # Update supervisor
        position_6.supervisor = person_2
        position_6.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        name_full_reverse = person_2.name_full_reverse
        self.assertEqual(name_full_reverse, pos_doc.supervisor)

        # Update predecessor
        position_6.predecessor = person_2
        position_6.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        name_full_reverse = person_2.name_full_reverse
        self.assertEqual(name_full_reverse, pos_doc.predecessor)

        # Update appointer
        position_6.appointer = position_5_1
        position_6.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)

        name_full_reverse = position_5_1.person.name_full_reverse
        self.assertEqual(name_full_reverse, pos_doc.appointer)

        # Update appointer (position_5_1) person name, it should be updated.
        person_2.name_first = "Sarah Miller"
        person_2.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        name_full_reverse = person_2.name_full_reverse
        self.assertEqual(name_full_reverse, pos_doc.appointer)
        self.assertEqual(name_full_reverse, pos_doc.supervisor)
        self.assertEqual(name_full_reverse, pos_doc.predecessor)

        # The following changes should update the child document.
        # Update dob_city field in the parent record.
        self.person_3.name_first = "William"
        self.person_3.save()
        name_full = self.person_3.name_full

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual(name_full, pos_doc.name)

        self.person_3.dob_city = "Brookyln"
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("Brookyln", pos_doc.dob_city)

        # Update the dob_state field in the parent record.
        self.person_3.dob_state = "AL"
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("Alabama", pos_doc.dob_state)
        self.assertEqual("AL", pos_doc.dob_state_id)

        # Update the gender field in the parent record.
        self.person_3.gender = "m"
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("Male", pos_doc.gender)

        # Update the religion field in the parent record
        self.person_3.religion = "je"
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("je", pos_doc.religion)

        # Update the fjc_id field in the parent record
        self.person_3.fjc_id = 39
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("39", pos_doc.fjc_id)

        school_2 = SchoolFactory(name="American University")

        # Add education to the parent object
        ed_obj = EducationFactory(
            degree_level="ba",
            person=self.person_3,
            school=school_2,
        )
        ed_obj_school_name = ed_obj.school.name

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        for education in self.person_3.educations.all():
            self.assertIn(education.school.name, pos_doc.school)

        # Update existing education record in the parent object
        self.school_1.name = "New school updated"
        self.school_1.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertIn("New school updated", pos_doc.school)

        # Remove Education.
        ed_obj.delete()
        # Confirm School is removed from the parent and child document.
        person_3_doc = PersonDocument.get(self.person_3.pk)
        self.assertNotIn(ed_obj_school_name, person_3_doc.school)
        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertNotIn(ed_obj_school_name, pos_doc.school)

        # Add political affiliation to the parent object
        PoliticalAffiliationFactory(
            political_party="d",
            source="b",
            date_start=datetime.date(2015, 12, 14),
            person=self.person_3,
            date_granularity_start="%Y-%m-%d",
        )

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        for affiliation in self.person_3.political_affiliations.all():
            self.assertIn(
                affiliation.get_political_party_display(),
                pos_doc.political_affiliation,
            )

        # Update existing political affiliation in the parent document
        self.political_affiliation_3.political_party = "f"
        self.political_affiliation_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertIn("Federalist", pos_doc.political_affiliation)

        # Add aba_rating to the parent object
        rating = ABARatingFactory(
            rating="nq",
            person=self.person_3,
            year_rated="2015",
        )
        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        for r in self.person_3.aba_ratings.all():
            self.assertIn(r.get_rating_display(), pos_doc.aba_rating)

        # Update existing rating in the parent object
        rating.rating = "ewq"
        rating.save()
        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertIn("Exceptionally Well Qualified", pos_doc.aba_rating)

        # Remove aba_rating and confirm it's removed from parent and child docs
        rating.delete()
        person_3_doc = PersonDocument.get(self.person_3.pk)
        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual(None, person_3_doc.aba_rating)
        self.assertEqual(None, pos_doc.aba_rating)

    def test_person_indexing_and_tasks_count(self) -> None:
        """Confirm a Person is properly indexed in ES with the right number of
        indexing tasks.
        """

        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            person = PersonFactory.create(
                name_first="Bill Clinton",
                date_granularity_dob="%Y-%m-%d",
                date_granularity_dod="%Y-%m-%d",
                religion="ca",
                date_dob=datetime.date(1941, 10, 21),
                date_dod=datetime.date(2022, 11, 25),
            )
        # 0 es_save_document task calls for Person creation since it's not a
        # Judge.
        self.reset_and_assert_task_count(expected=0)
        # The person is not indexed since it's not a Judge.
        self.assertFalse(PersonDocument.exists(id=person.pk))

        # Add a judiciaryPosition to person.
        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            position = PositionFactory.create(
                date_granularity_start="%Y-%m-%d",
                court=self.court_2,
                date_start=datetime.date(2020, 12, 14),
                predecessor=self.person_3,
                appointer=self.position_1,
                judicial_committee_action="no_rep",
                termination_reason="retire_mand",
                position_type="c-jud",
                person=person,
                how_selected="a_legis",
                nomination_process="fed_senate",
            )
        # 1 es_save_document task calls for Position creation.
        self.reset_and_assert_task_count(expected=1)
        # The Person and the Position are now indexed.
        self.assertTrue(PersonDocument.exists(id=person.pk))
        self.assertTrue(
            PersonDocument.exists(id=ES_CHILD_ID(position.pk).POSITION)
        )

        # Update a Person without changes.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            person.save()
        # update_es_document task shouldn't be called on save() without changes
        self.reset_and_assert_task_count(expected=0)

        # Update a Position without changes.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            position.save()
        # update_es_document task shouldn't be called on save() without changes
        self.reset_and_assert_task_count(expected=0)

        # Update a Person tracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            person.name_first = "Barack"
            person.save()
        # update_es_document task should be called 1 on tracked fields updates
        self.reset_and_assert_task_count(expected=1)
        p_doc = PersonDocument.get(id=person.pk)
        self.assertIn("Barack", p_doc.name)

        # Confirm a Person is indexed if it doesn't exist in the index on a
        # tracked field update.
        self.delete_index("people_db.Person")
        self.create_index("people_db.Person")

        self.assertFalse(PersonDocument.exists(id=person.pk))
        self.assertFalse(
            PersonDocument.exists(id=ES_CHILD_ID(position.pk).POSITION)
        )

        # Person creation on update.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            person.religion = "pr"
            person.save()

        # update_es_document task should be called 1 on tracked fields update
        self.reset_and_assert_task_count(expected=1)
        p_doc = PersonDocument.get(id=person.pk)
        self.assertEqual(p_doc.religion, "pr")

        # Position creation on update.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            position.nomination_process = "state_senate"
            position.save()

        # update_es_document task should be called 1 on tracked fields update
        self.reset_and_assert_task_count(expected=1)
        po_doc = PersonDocument.get(id=ES_CHILD_ID(position.pk).POSITION)
        self.assertEqual(po_doc.nomination_process, "State Senate")

        # Position ForeignKey field update.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            position.predecessor = self.person_2
            position.save()

        # update_es_document task should be called 1 on tracked fields update
        self.reset_and_assert_task_count(expected=1)
        po_doc = PersonDocument.get(id=ES_CHILD_ID(position.pk).POSITION)
        self.assertEqual(po_doc.predecessor, self.person_2.name_full_reverse)

        person.delete()
