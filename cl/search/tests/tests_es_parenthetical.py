import datetime
import operator
from datetime import date
from functools import reduce

from django.urls import reverse
from elasticsearch_dsl import Q
from lxml import html

from cl.lib.elasticsearch_utils import (
    build_daterange_query,
    build_es_filters,
    build_es_main_query,
    build_fulltext_query,
    build_sort_results,
    build_terms_query,
    group_search_results,
)
from cl.people_db.factories import PersonFactory
from cl.search.documents import (
    ParentheticalGroupDocument,
    parenthetical_group_index,
)
from cl.search.factories import (
    CitationWithParentsFactory,
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionsCitedWithParentsFactory,
    OpinionWithParentsFactory,
    ParentheticalFactory,
    ParentheticalGroupFactory,
)
from cl.search.models import PRECEDENTIAL_STATUS, SEARCH_TYPES, Citation
from cl.tests.cases import ESIndexTestCase, TestCase


class ParentheticalESTest(ESIndexTestCase, TestCase):
    """Parenthetical ES search related tests"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.ParentheticalGroup")
        cls.c1 = CourtFactory(id="canb", jurisdiction="I")
        cls.c2 = CourtFactory(id="ca1", jurisdiction="F")
        cls.c3 = CourtFactory(id="cacd", jurisdiction="FB")

        cls.cluster = OpinionClusterFactory(
            case_name="Peck, Williams and Freeman v. Stephens",
            case_name_short="Stephens",
            judges="Lorem ipsum",
            scdb_id="1952-121",
            nature_of_suit="710",
            docket=DocketFactory(
                court=cls.c1,
                docket_number="1:98-cr-35856",
                date_reargued=date(1986, 1, 30),
                date_reargument_denied=date(1986, 5, 30),
            ),
            date_filed=date(1978, 3, 10),
            source="H",
            precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
        )
        cls.o = OpinionWithParentsFactory(
            cluster=cls.cluster,
            type="Plurality Opinion",
            extracted_by_ocr=True,
        )
        cls.o.joined_by.add(cls.o.author)
        cls.cluster.panel.add(cls.o.author)
        cls.citation = CitationWithParentsFactory(cluster=cls.cluster)
        cls.citation_lexis = CitationWithParentsFactory(
            cluster=cls.cluster, type=Citation.LEXIS
        )
        cls.citation_neutral = CitationWithParentsFactory(
            cluster=cls.cluster, type=Citation.NEUTRAL
        )
        cls.opinion_cited = OpinionsCitedWithParentsFactory(
            citing_opinion=cls.o, cited_opinion=cls.o
        )
        cls.o2 = OpinionWithParentsFactory(
            cluster=OpinionClusterFactory(
                case_name="Riley v. Brewer-Hall",
                case_name_short="Riley",
                docket=DocketFactory(
                    court=cls.c2,
                ),
                date_filed=date(1976, 8, 30),
                source="H",
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            ),
            type="Concurrence Opinion",
            extracted_by_ocr=False,
        )

        cls.o3 = OpinionWithParentsFactory(
            cluster=OpinionClusterFactory(
                case_name="Smith v. Herrera",
                case_name_short="Herrera",
                docket=DocketFactory(
                    court=cls.c3,
                ),
                date_filed=date(1981, 7, 11),
                source="LC",
                precedential_status=PRECEDENTIAL_STATUS.SEPARATE,
            ),
            type="In Part Opinion",
            extracted_by_ocr=True,
        )

        cls.p = ParentheticalFactory(
            describing_opinion=cls.o,
            described_opinion=cls.o,
            group=None,
            text="At responsibility learn point year rate.",
            score=0.3236,
        )

        cls.p2 = ParentheticalFactory(
            describing_opinion=cls.o2,
            described_opinion=cls.o2,
            group=None,
            text="Necessary Together friend conference end different such.",
            score=0.4218,
        )

        cls.p3 = ParentheticalFactory(
            describing_opinion=cls.o3,
            described_opinion=cls.o3,
            group=None,
            text="Necessary drug realize matter provide different.",
            score=0.1578,
        )

        cls.p4 = ParentheticalFactory(
            describing_opinion=cls.o3,
            described_opinion=cls.o3,
            group=None,
            text="Necessary realize matter to provide further.",
            score=0.1478,
        )

        cls.pg = ParentheticalGroupFactory(
            opinion=cls.o, representative=cls.p, score=0.3236, size=1
        )
        cls.pg2 = ParentheticalGroupFactory(
            opinion=cls.o2, representative=cls.p2, score=0.318, size=1
        )
        cls.pg3 = ParentheticalGroupFactory(
            opinion=cls.o3, representative=cls.p3, score=0.1578, size=1
        )
        cls.pg4 = ParentheticalGroupFactory(
            opinion=cls.o3, representative=cls.p4, score=0.1678, size=1
        )
        # Set parenthetical group
        cls.p.group = cls.pg
        cls.p.save()
        cls.p2.group = cls.pg2
        cls.p2.save()
        cls.p3.group = cls.pg3
        cls.p3.save()
        cls.p4.group = cls.pg4
        cls.p4.save()

    def test_filter_search(self) -> None:
        """Test filtering and search at the same time"""
        filters = []
        filters.append(Q("match", representative_text="different"))
        s1 = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )
        self.assertEqual(s1.count(), 2)

        filters.append(Q("match", opinion_extracted_by_ocr=False))
        s2 = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )
        self.assertEqual(s2.count(), 1)

    def test_filter_daterange(self) -> None:
        """Test filter by date range"""
        filters = []
        date_gte = "1976-08-30T00:00:00Z"
        date_lte = "1978-03-10T23:59:59Z"

        filters.append(
            Q(
                "range",
                dateFiled={
                    "gte": date_gte,
                    "lte": date_lte,
                },
            )
        )

        s1 = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )

        self.assertEqual(s1.count(), 2)

    def test_filter_search_2(self) -> None:
        """Test filtering date range and search at the same time"""
        filters = []
        date_gte = "1976-08-30T00:00:00Z"
        date_lte = "1978-03-10T23:59:59Z"

        filters.append(Q("match", representative_text="different"))
        filters.append(
            Q(
                "range",
                dateFiled={
                    "gte": date_gte,
                    "lte": date_lte,
                },
            )
        )

        s = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )
        self.assertEqual(s.count(), 1)

    def test_ordering(self) -> None:
        """Test filter and then ordering by descending dateFiled"""
        filters = []
        date_gte = "1976-08-30T00:00:00Z"
        date_lte = "1978-03-10T23:59:59Z"

        filters.append(
            Q(
                "range",
                dateFiled={
                    "gte": date_gte,
                    "lte": date_lte,
                },
            )
        )

        s = (
            ParentheticalGroupDocument.search()
            .filter(reduce(operator.iand, filters))
            .sort("-dateFiled")
        )
        s1 = s.sort("-dateFiled")
        self.assertEqual(s1.count(), 2)
        self.assertEqual(
            s1.execute()[0].dateFiled,
            datetime.datetime(1978, 3, 10, 0, 0),
        )
        s2 = s.sort("dateFiled")
        self.assertEqual(
            s2.execute()[0].dateFiled,
            datetime.datetime(1976, 8, 30, 0, 0),
        )

    @staticmethod
    def get_article_count(r):
        """Get the article count in a query response"""
        return len(html.fromstring(r.content.decode()).xpath("//article"))

    def test_build_daterange_query(self) -> None:
        """Test build es daterange query"""
        filters = []
        date_gte = datetime.datetime(1976, 8, 30, 0, 0).date()
        date_lte = datetime.datetime(1978, 3, 10, 0, 0).date()

        q1 = build_daterange_query("dateFiled", date_lte, date_gte)
        filters.extend(q1)

        s = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )
        self.assertEqual(s.count(), 2)

    def test_build_fulltext_query(self) -> None:
        """Test build es fulltext query"""
        q1 = build_fulltext_query("representative_text", "responsibility")
        s = ParentheticalGroupDocument.search().filter(q1)
        self.assertEqual(s.count(), 1)

    def test_build_terms_query(self) -> None:
        """Test build es terms query"""
        filters = []
        q = build_terms_query(
            "court_id",
            [self.c1.pk, self.c2.pk],
        )
        filters.extend(q)
        s = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )
        self.assertEqual(s.count(), 2)

    def test_cd_query(self) -> None:
        """Test build es query with cleaned data"""

        cd = {
            "filed_after": datetime.datetime(1976, 8, 30, 0, 0).date(),
            "filed_before": datetime.datetime(1978, 3, 10, 0, 0).date(),
            "q": "responsibility",
            "type": "pa",
        }
        search_query = ParentheticalGroupDocument.search()
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
        self.assertEqual(s.count(), 1)

    def test_cd_query_2(self) -> None:
        """Test build es query with cleaned data"""
        cd = {"filed_after": "", "filed_before": "", "q": ""}

        filters = build_es_filters(cd)

        if not filters:
            # Return all results
            s = ParentheticalGroupDocument.search().query("match_all")
            self.assertEqual(s.count(), 4)

    def test_docket_number_filter(self) -> None:
        """Test filter by docker_number"""
        filters = []

        filters.append(Q("term", docketNumber="1:98-cr-35856"))

        s = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )
        self.assertEqual(s.count(), 1)

    def test_build_sort(self) -> None:
        """Test we can build sort dict and sort ES query"""
        cd = {"order_by": "dateFiled desc"}
        ordering = build_sort_results(cd)
        s = (
            ParentheticalGroupDocument.search()
            .query("match_all")
            .sort(ordering)
        )
        self.assertEqual(s.count(), 4)
        self.assertEqual(
            s.execute()[0].dateFiled,
            datetime.datetime(1981, 7, 11, 0, 0),
        )

        cd = {"order_by": "dateFiled asc"}
        ordering = build_sort_results(cd)
        s = (
            ParentheticalGroupDocument.search()
            .query("match_all")
            .sort(ordering)
        )
        self.assertEqual(
            s.execute()[0].dateFiled,
            datetime.datetime(1976, 8, 30, 0, 0),
        )

        cd = {"order_by": "score desc"}
        ordering = build_sort_results(cd)
        s = (
            ParentheticalGroupDocument.search()
            .query("match_all")
            .sort(ordering)
        )
        self.assertEqual(
            s.execute()[0].dateFiled,
            datetime.datetime(1978, 3, 10, 0, 0),
        )

    def test_group_results(self) -> None:
        """Test retrieve results grouped by group_id"""

        cd = {"type": "pa", "q": ""}
        q1 = build_fulltext_query("representative_text", "Necessary")
        s = ParentheticalGroupDocument.search().query(q1)
        # Group results.
        group_search_results(s, cd, {"score": {"order": "desc"}})
        hits = s.execute()
        groups = hits.aggregations.groups.buckets

        # Compare groups and hits content.
        self.assertEqual(len(groups), 2)
        self.assertEqual(
            len(groups[0].grouped_by_opinion_cluster_id.hits.hits), 2
        )
        self.assertEqual(
            len(groups[1].grouped_by_opinion_cluster_id.hits.hits), 1
        )

        group_1_hits = groups[0].grouped_by_opinion_cluster_id.hits.hits
        self.assertEqual(group_1_hits[0]._source.score, 0.1578)
        self.assertEqual(group_1_hits[1]._source.score, 0.1678)

    def test_index_advanced_search_fields(self) -> None:
        """Test confirm advanced search fields are indexed."""

        filters = []
        filters.append(Q("term", docketNumber="1:98-cr-35856"))
        s = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )
        results = s.execute()

        # Check advanced search fields are indexed and confirm their data types
        self.assertEqual(len(results), 1)
        self.assertEqual(type(results[0].author_id), int)
        self.assertEqual(type(results[0].caseName), str)
        self.assertEqual(results[0].citeCount, 0)
        self.assertIsNotNone(results[0].citation)
        self.assertEqual(type(results[0].citation[0]), str)
        self.assertEqual(type(results[0].cites[0]), int)
        self.assertEqual(type(results[0].court_id), str)
        self.assertEqual(type(results[0].dateFiled), datetime.datetime)
        self.assertEqual(type(results[0].docket_id), int)
        self.assertEqual(type(results[0].docketNumber), str)
        self.assertEqual(type(results[0].judge), str)
        self.assertEqual(type(results[0].lexisCite), str)
        self.assertEqual(type(results[0].neutralCite), str)
        self.assertEqual(type(results[0].panel_ids[0]), int)
        self.assertEqual(type(results[0].status), str)
        self.assertEqual(type(results[0].suitNature), str)

    async def test_pa_search_form_search_and_filtering(self) -> None:
        """Test Parenthetical search directly from the form."""
        r = await self.async_client.get(
            reverse("show_results"),
            {
                "q": "Necessary",
                "type": SEARCH_TYPES.PARENTHETICAL,
            },
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

        r = await self.async_client.get(
            reverse("show_results"),
            {
                "q": "",
                "docket_number": "1:98-cr-35856",
                "type": SEARCH_TYPES.PARENTHETICAL,
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )
        r = await self.async_client.get(
            reverse("show_results"),
            {
                "q": "",
                "filed_after": "1978/02/10",
                "type": SEARCH_TYPES.PARENTHETICAL,
            },
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )
        r = await self.async_client.get(
            reverse("show_results"),
            {
                "q": "",
                "order_by": "dateFiled asc",
                "type": SEARCH_TYPES.PARENTHETICAL,
            },
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )
        self.assertTrue(
            r.content.decode().index("Riley")
            < r.content.decode().index("Peck")
            < r.content.decode().index("Smith"),
            msg="'Riley' should come before 'Peck' and before 'Smith' when order_by asc.",
        )


class ParentheticalESSignalProcessorTest(ESIndexTestCase, TestCase):
    """Parenthetical ES indexing related tests"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.ParentheticalGroup")
        # Create factories for the test.
        cls.c1 = CourtFactory(id="canb", jurisdiction="I")
        cls.c2 = CourtFactory(id="ca1", jurisdiction="F")
        cls.cluster_1 = OpinionClusterFactory(
            case_name="Lorem Ipsum",
            case_name_short="Ipsum",
            judges="Lorem 2",
            scdb_id="0000",
            nature_of_suit="410",
            docket=DocketFactory(
                court=cls.c1,
                docket_number="1:95-cr-11111",
                date_reargued=date(1986, 1, 30),
                date_reargument_denied=date(1986, 5, 30),
            ),
            date_filed=date(1976, 3, 10),
            source="H",
            precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
        )
        cls.cluster_2 = OpinionClusterFactory(
            docket=DocketFactory(
                court=cls.c1,
                docket_number="1:25-cr-1111",
                date_reargued=date(1986, 1, 30),
                date_reargument_denied=date(1986, 5, 30),
            ),
            date_filed=date(1976, 3, 10),
            source="H",
            precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
        )
        cls.o = OpinionWithParentsFactory(
            cluster=cls.cluster_1,
            type="Plurality Opinion",
            extracted_by_ocr=True,
        )
        cls.o_2 = OpinionWithParentsFactory(
            cluster=cls.cluster_2,
        )
        cls.p5 = ParentheticalFactory(
            describing_opinion=cls.o_2,
            described_opinion=cls.o_2,
            group=None,
            text="Lorem Ipsum Dolor.",
            score=0.4218,
        )
        cls.pg_test = ParentheticalGroupFactory(
            opinion=cls.o, representative=cls.p5, score=0.3236, size=1
        )
        cls.p5.group = cls.pg_test
        cls.p5.save()

    def setUp(self) -> None:
        self.setUpTestData()
        super().setUp()

    def test_keep_in_sync_related_pa_objects_on_save(self) -> None:
        """Test PA documents are updated in ES when related objects change."""

        # Retrieve the document from ES and confirm it was indexed.
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual(self.cluster_1.docket.docket_number, doc.docketNumber)
        # Update docket number and confirm it's updated in ES.
        self.cluster_1.docket.docket_number = "1:98-cr-0000"
        self.cluster_1.docket.save()
        self.cluster_1.refresh_from_db()
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual("1:98-cr-0000", doc.docketNumber)

        # Confirm we can avoid updating documents in ES when a related object
        # field is not including in the document mapping.
        # Confirm initial version is 2.
        self.assertEqual(2, doc.meta.version)

        # Update a related object field which is not including in the document
        # mapping.
        self.cluster_1.docket.view_count = 5
        self.cluster_1.docket.save()
        self.cluster_1.refresh_from_db()
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        # Document version remains the same since document was not updated.
        self.assertEqual(2, doc.meta.version)

        # Confirm court_id is updated in ES.
        self.cluster_1.docket.court = self.c2
        self.cluster_1.docket.save()
        self.cluster_1.refresh_from_db()
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual(self.c2.pk, doc.court_id)

        # Confirm opinion related fields are updated in ES.
        author_1 = PersonFactory(name_first="John")
        self.o.extracted_by_ocr = False
        self.o.cluster = self.cluster_1
        self.o.author = author_1
        self.o.save()
        self.cluster_1.refresh_from_db()
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual(False, doc.opinion_extracted_by_ocr)
        self.assertEqual(self.cluster_1.pk, doc.cluster_id)
        self.assertEqual(author_1.pk, doc.author_id)

        # Confirm opinion cluster related fields are updated in ES.
        docket_1 = DocketFactory()
        self.cluster_1.case_name = "USA vs IPSUM"
        self.cluster_1.citation_count = 10
        self.cluster_1.date_filed = datetime.datetime(2023, 3, 10)
        self.cluster_1.docket = docket_1
        self.cluster_1.judges = "Bill Clinton"
        self.cluster_1.nature_of_suit = "110"
        self.cluster_1.save()
        self.cluster_1.refresh_from_db()
        self.pg_test.representative.describing_opinion.cluster.case_name = (
            "California vs Doe"
        )
        self.pg_test.representative.describing_opinion.cluster.save()
        self.pg_test.representative.describing_opinion.cluster.refresh_from_db()

        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual("USA vs IPSUM", doc.caseName)
        self.assertEqual(10, doc.citeCount)
        self.assertEqual(datetime.datetime(2023, 3, 10), doc.dateFiled)
        self.assertEqual("usa-vs-ipsum", doc.opinion_cluster_slug)
        self.assertEqual(
            "california-vs-doe", doc.describing_opinion_cluster_slug
        )
        self.assertEqual(docket_1.pk, doc.docket_id)
        self.assertEqual("Bill Clinton", doc.judge)
        self.assertEqual("110", doc.suitNature)

        # Confirm representative Parenthetical fields are updated in ES.
        self.p5.text = "New text"
        self.p5.score = 0.70
        self.p5.save()
        self.p5.save()

        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual("New text", doc.representative_text)
        self.assertEqual(0.70, doc.representative_score)

        # Confirm related object fields using display value are properly indexed.
        self.assertEqual("Non-Precedential", doc.status)
        self.cluster_1.precedential_status = PRECEDENTIAL_STATUS.PUBLISHED
        self.cluster_1.save()
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual("Precedential", doc.status)
        self.pg_test.delete()

    def test_keep_in_sync_related_pa_objects_on_m2m_change(self) -> None:
        # Confirm m2m related fields are updated in ES.
        # Check initial m2m values are empty.
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        author_1 = PersonFactory(name_first="John")
        self.assertEqual([], doc.panel_ids)
        self.assertEqual([], doc.cites)
        # Add m2m relation.
        self.cluster_1.panel.add(author_1)
        self.o.opinions_cited.add(self.o_2)
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        # m2m fields are properly updated in ES.
        self.assertEqual([author_1.pk], doc.panel_ids)
        self.assertEqual([self.o_2.pk], doc.cites)

        # Confirm m2m fields are cleaned in ES when the relation is removed.
        self.cluster_1.panel.remove(author_1)
        self.o.opinions_cited.remove(self.o_2)

        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual(None, doc.cites)
        self.assertEqual(None, doc.panel_ids)
        self.pg_test.delete()

    def test_keep_in_sync_related_pa_objects_on_reverse_relation(self) -> None:
        # Confirm reverse related fields are updated in ES.
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual([], doc.citation)
        # Create reverse related objects to cluster_1.
        citation = CitationWithParentsFactory(cluster=self.cluster_1)
        citation_lexis = CitationWithParentsFactory(
            cluster=self.cluster_1, type=Citation.LEXIS
        )
        citation_neutral = CitationWithParentsFactory(
            cluster=self.cluster_1, type=Citation.NEUTRAL
        )
        # Reverse related object fields are updated in ES.
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual(
            [str(citation), str(citation_lexis), str(citation_neutral)],
            doc.citation,
        )
        self.assertEqual(str(citation_lexis), doc.lexisCite)
        self.assertEqual(str(citation_neutral), doc.neutralCite)

        # Confirm reverse related object fields are cleaned in ES when the
        # object is removed.
        citation.delete()
        citation_lexis.delete()
        citation_neutral.delete()
        doc = ParentheticalGroupDocument.get(id=self.pg_test.pk)
        self.assertEqual(None, doc.citation)
        self.assertEqual(None, doc.lexisCite)
        self.assertEqual(None, doc.neutralCite)
        self.pg_test.delete()

    def test_keep_in_sync_related_pa_objects_on_delete(self) -> None:
        # Confirm document is removed from ES, when the ParentheticalGroup is
        # removed from DB.
        pg_id = self.pg_test.pk
        self.pg_test.delete()
        self.assertEqual(False, ParentheticalGroupDocument.exists(id=pg_id))

        # Confirm we can index a document if it doesn't exist when trying to
        # update a related document.
        # Simulate new document is not indexed in ES yet, index it and delete
        # the document from ES but keep the object in DB.
        pg_1 = ParentheticalGroupFactory(
            opinion=self.o, representative=self.p5, score=0.3236, size=1
        )
        pg_1_id = pg_1.pk
        doc = ParentheticalGroupDocument.get(id=pg_1.pk)
        doc.delete()
        self.assertEqual(False, ParentheticalGroupDocument.exists(id=pg_1_id))

        # Try to update a related object field.
        self.cluster_1.precedential_status = PRECEDENTIAL_STATUS.IN_CHAMBERS
        self.cluster_1.save()
        # Document is indexed in ES again.
        self.assertEqual(True, ParentheticalGroupDocument.exists(id=pg_1_id))
        pg_1.delete()
