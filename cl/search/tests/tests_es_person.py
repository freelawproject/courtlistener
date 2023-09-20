import datetime
import operator
from functools import reduce

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
    PersonFactory,
    PoliticalAffiliationFactory,
    PositionFactory,
    SchoolFactory,
)
from cl.search.documents import ES_CHILD_ID, PersonDocument, PositionDocument
from cl.search.models import SEARCH_TYPES
from cl.tests.cases import ESIndexTestCase, TestCase


class PeopleSearchTestElasticSearch(
    CourtTestCase, PeopleTestCase, ESIndexTestCase, TestCase
):
    """People search tests for Elasticsearch"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        super().setUpTestData()

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

    def test_remove_parent_child_objects_from_index(self) -> None:
        """Confirm join child objects are removed from the index when the
        parent objects is deleted.
        """
        person = PersonFactory.create(name_first="John Deer")
        pos_1 = PositionFactory.create(
            court=self.court_1,
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
        school = SchoolFactory.create(name="Harvard University")

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

        pos_1.court = self.court_2
        pos_1.save()

        person_doc = PersonDocument.get(id=person.pk)
        self.assertIn("Debbas", person_doc.name)

        position_doc = PersonDocument.get(id=ES_CHILD_ID(pos_1_pk).POSITION)
        self.assertEqual(self.court_2.pk, position_doc.court_exact)

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
            court=self.court_1,
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

        # Delete pos_1 and education, keep the parent person instance.
        pos_1.delete()

        # Person instance still exists.
        self.assertTrue(PersonDocument.exists(id=person_pk))

        # Position object is removed
        self.assertFalse(
            PersonDocument.exists(id=ES_CHILD_ID(pos_1_pk).POSITION)
        )
        person.delete()

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
            "dob_state": "NY",
            "selection_method": "e_part",
            "type": SEARCH_TYPES.PEOPLE,
        }
        s = PersonDocument.search()
        has_child_filters = build_join_es_filters(cd)
        s = s.filter(reduce(operator.iand, has_child_filters))
        self.assertEqual(s.count(), 1)

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
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )

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
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
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
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
        # Main result. Court that doesn't belong any of the positions
        # No results
        self.assertEqual(s.count(), 0)

        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "appointer": "clinton",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
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
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
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
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
        self.assertEqual(s.count(), 1)

        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "clinton Olivia",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
        # Two main results, matched by string queries on parent and position
        self.assertEqual(s.count(), 2)

        cd = {
            "type": SEARCH_TYPES.PEOPLE,
            "q": "clinton OR Olivia",
            "order_by": "name_reverse asc",
        }

        search_query = PersonDocument.search()
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
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
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
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
            date_referred_to_judicial_committee=datetime.date(2017, 11, 14),
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

        self.assertEqual(
            r.data["results"][0]["court"],
            [self.position_2.court.short_name, position_6.court.short_name],
        )
        self.assertEqual(
            r.data["results"][0]["court_exact"],
            [self.position_2.court.pk, position_6.court.pk],
        )
        self.assertEqual(
            r.data["results"][0]["position_type"],
            [
                self.position_2.get_position_type_display(),
                position_6.get_position_type_display(),
            ],
        )
        self.assertEqual(
            r.data["results"][0]["appointer"],
            [
                self.position_2.appointer.person.name_full_reverse,
                position_6.appointer.person.name_full_reverse,
            ],
        )
        self.assertEqual(
            r.data["results"][0]["supervisor"],
            [position_6.supervisor.name_full_reverse],
        )
        self.assertEqual(
            r.data["results"][0]["predecessor"],
            [
                self.position_2.predecessor.name_full_reverse,
                position_6.predecessor.name_full_reverse,
            ],
        )

        positions = self.person_2.positions.all()
        self.assertEqual(
            r.data["results"][0]["date_nominated"],
            solr_list(positions, "date_nominated"),
        )
        self.assertEqual(
            r.data["results"][0]["date_elected"],
            solr_list(positions, "date_elected"),
        )
        self.assertEqual(
            r.data["results"][0]["date_recess_appointment"],
            solr_list(positions, "date_recess_appointment"),
        )
        self.assertEqual(
            r.data["results"][0]["date_referred_to_judicial_committee"],
            solr_list(positions, "date_referred_to_judicial_committee"),
        )
        self.assertEqual(
            r.data["results"][0]["date_judicial_committee_action"],
            solr_list(positions, "date_judicial_committee_action"),
        )
        self.assertEqual(
            r.data["results"][0]["date_hearing"],
            solr_list(positions, "date_hearing"),
        )
        self.assertEqual(
            r.data["results"][0]["date_confirmation"],
            solr_list(positions, "date_confirmation"),
        )
        self.assertEqual(
            r.data["results"][0]["date_start"],
            solr_list(positions, "date_start"),
        )
        self.assertEqual(
            r.data["results"][0]["date_granularity_start"],
            [
                self.position_2.date_granularity_start,
                self.position_3.date_granularity_start,
                position_6.date_granularity_start,
            ],
        )
        self.assertEqual(
            r.data["results"][0]["date_retirement"],
            solr_list(positions, "date_retirement"),
        )
        self.assertEqual(
            r.data["results"][0]["date_termination"],
            solr_list(positions, "date_termination"),
        )
        self.assertEqual(
            r.data["results"][0]["date_granularity_termination"],
            [position_6.date_granularity_termination],
        )
        self.assertEqual(
            r.data["results"][0]["judicial_committee_action"],
            [
                self.position_2.get_judicial_committee_action_display(),
                position_6.get_judicial_committee_action_display(),
            ],
        )
        self.assertEqual(
            r.data["results"][0]["nomination_process"],
            [
                self.position_2.get_nomination_process_display(),
                position_6.get_nomination_process_display(),
            ],
        )
        self.assertEqual(
            r.data["results"][0]["selection_method"],
            [
                self.position_2.get_how_selected_display(),
                position_6.get_how_selected_display(),
            ],
        )
        self.assertEqual(
            r.data["results"][0]["selection_method_id"],
            [self.position_2.how_selected, position_6.how_selected],
        )
        self.assertEqual(
            r.data["results"][0]["termination_reason"],
            [
                self.position_2.get_termination_reason_display(),
                position_6.get_termination_reason_display(),
            ],
        )

        position_5.delete()
        position_6.delete()
        person.delete()

    def test_update_related_documents(self):
        person = PersonFactory.create(name_first="John American")
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

        self.person_3.dob_city = "Brookyln"
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("Brookyln", pos_doc.dob_city)

        self.person_3.dob_city = "Brookyln"
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("Brookyln", pos_doc.dob_city)

        self.person_3.dob_state = "AL"
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("Alabama", pos_doc.dob_state)

        self.person_3.gender = "m"
        self.person_3.save()

        pos_doc = PositionDocument.get(id=ES_CHILD_ID(position_6.pk).POSITION)
        self.assertEqual("Male", pos_doc.gender)
