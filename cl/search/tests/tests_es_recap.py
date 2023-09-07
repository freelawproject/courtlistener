import datetime
import unittest

from asgiref.sync import sync_to_async
from django.urls import reverse
from lxml import html
from rest_framework.status import HTTP_200_OK
from elasticsearch_dsl import Q

from cl.people_db.factories import (
    AttorneyFactory,
    AttorneyOrganizationFactory,
    PartyFactory,
    PartyTypeFactory,
    PersonFactory,
)
from cl.lib.elasticsearch_utils import (
    build_es_main_query,
    build_join_es_filters,
    build_join_fulltext_queries,
)
from cl.search.factories import (
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    RECAPDocumentFactory,
BankruptcyInformationFactory
)
from cl.search.models import SEARCH_TYPES, RECAPDocument
from cl.search.tasks import add_docket_to_solr_by_rds
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.search.documents import DocketDocument, ESRECAPDocument, ES_CHILD_ID


class RECAPSearchTest(ESIndexTestCase, TestCase):
    """
    RECAP Search Tests
    """

    tests_running_over_solr = True

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.Docket")
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_2 = CourtFactory(id="ca1", jurisdiction="F")
        cls.judge = PersonFactory.create(
            name_first="Thalassa", name_last="Miller"
        )
        cls.judge_2 = PersonFactory.create(
            name_first="Persephone", name_last="Sinclair"
        )
        cls.de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=cls.court,
                case_name="SUBPOENAS SERVED ON",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:21-bk-1234",
                assigned_to=cls.judge,
                referred_to=cls.judge_2,
                nature_of_suit="440",
            ),
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem",
        )
        cls.firm = AttorneyOrganizationFactory(name="Associates LLP")
        cls.attorney = AttorneyFactory(
            name="Debbie Russell",
            organizations=[cls.firm],
            docket=cls.de.docket,
        )
        cls.party_type = PartyTypeFactory.create(
            party=PartyFactory(
                name="Defendant Jane Roe",
                docket=cls.de.docket,
                attorneys=[cls.attorney],
            ),
            docket=cls.de.docket,
        )

        cls.rd = RECAPDocumentFactory(
            docket_entry=cls.de,
            description="Leave to File",
            document_number="1",
            is_available=True,
            page_count=5,
        )
        cls.rd_att = RECAPDocumentFactory(
            docket_entry=cls.de,
            description="Document attachment",
            document_type=RECAPDocument.ATTACHMENT,
            document_number="1",
            attachment_number=2,
            is_available=False,
            page_count=7,
        )

        cls.judge_3 = PersonFactory.create(
            name_first="Seraphina", name_last="Hawthorne"
        )
        cls.judge_4 = PersonFactory.create(
            name_first="Leopold", name_last="Featherstone"
        )
        cls.de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                docket_number="12-1235",
                court=cls.court_2,
                case_name="SUBPOENAS SERVED OFF",
                case_name_full="The State of Franklin v. Solutions LLC",
                date_filed=datetime.date(2016, 8, 16),
                date_argued=datetime.date(2012, 6, 23),
                assigned_to=cls.judge_3,
                referred_to=cls.judge_4,
            ),
            date_filed=datetime.date(2014, 7, 19),
            description="MOTION for Leave to File Amicus Discharging Debtor",
        )
        cls.rd_2 = RECAPDocumentFactory(
            docket_entry=cls.de_1,
            description="Leave to File",
            document_number="3",
            page_count=10,
            plain_text="Maecenas nunc justo"
        )
        super().setUpTestData()


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

    def _count_child_documents(
        self, article, html_content, expected_count, field_name
    ):
        tree = html.fromstring(html_content)
        article = tree.xpath("//article")[article]
        got = len(article.xpath(".//h4"))
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of grouped documents %s\n"
            "Expected: %s\n"
            "     Got: %s\n\n" % (field_name, expected_count, got),
        )

    def test_index_recap_parent_and_child_objects(self) -> None:
        """Confirm Dockets and RECAPDocuments are properly indexed in ES"""

        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2)

        # RECAPDocuments are indexed.
        rd_pks = [
            self.rd.pk,
            self.rd_att.pk,
            self.rd_2.pk,
        ]
        for rd_pk in rd_pks:
            self.assertTrue(
                DocketDocument.exists(
                    id=ES_CHILD_ID(rd_pk).RECAP
                )
            )

    def test_update_and_remove_parent_child_objects_in_es(self) -> None:
        """Confirm child documents can be updated and removed properly."""

        de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                case_name="Lorem Ipsum",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:21-bk-1234",
                assigned_to=self.judge,
                referred_to=self.judge_2,
                nature_of_suit="440",
            ),
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem",
            )
        rd_1 = RECAPDocumentFactory(
            docket_entry=de_1,
            description="Leave to File",
            document_number="1",
            is_available=True,
            page_count=5,
        )

        docket_pk = de_1.docket.pk
        rd_pk = rd_1.pk
        self.assertTrue(DocketDocument.exists(id=docket_pk))

        self.assertTrue(
            DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP)
        )

        # Update docket field:
        de_1.docket.case_name = "USA vs Bank"
        de_1.docket.save()

        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertIn("USA vs Bank", docket_doc.caseName)


        # Update docket entry field:

        de_1.description = "Notification to File Ipsum"
        de_1.entry_number = 99
        de_1.save()

        rd_doc = DocketDocument.get(id=ES_CHILD_ID(rd_pk).RECAP)
        self.assertEqual("Notification to File Ipsum", rd_doc.description)
        self.assertEqual(99, rd_doc.entry_number)

        # Add a Bankruptcy document.

        bank = BankruptcyInformationFactory(docket=de_1.docket)
        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertEqual(bank.chapter, docket_doc.chapter)
        self.assertEqual(bank.trustee_str, docket_doc.trustee_str)

        # Update Bankruptcy document.
        bank.chapter = "97"
        bank.trustee_str = "Victoria, Sherline"
        bank.save()

        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertEqual("97", docket_doc.chapter)
        self.assertEqual("Victoria, Sherline", docket_doc.trustee_str)


        # Add another RD:
        rd_2 = RECAPDocumentFactory(
            docket_entry=de_1,
            description="Notification to File",
            document_number="2",
            is_available=True,
            page_count=2,
        )

        rd_2_pk = rd_2.pk
        self.assertTrue(
            DocketDocument.exists(id=ES_CHILD_ID(rd_2_pk).RECAP)
        )
        rd_2.delete()
        self.assertFalse(
            DocketDocument.exists(id=ES_CHILD_ID(rd_2_pk).RECAP)
        )

        self.assertTrue(DocketDocument.exists(id=docket_pk))
        self.assertTrue(
            DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP)
        )

        de_1.docket.delete()
        self.assertFalse(DocketDocument.exists(id=docket_pk))
        self.assertFalse(
            DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP)
        )

    def test_has_child_text_queries(self) -> None:
        """Test the build_es_main_query method."""
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Discharging Debtor",
        }
        search_query = DocketDocument.search()
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )

        response = s.execute().to_dict()
        self.assertEqual(s.count(), 1)
        self.assertEqual(
            1,
            len(
                response["hits"]["hits"][0]["inner_hits"][
                    "text_query_inner_recap_document"
                ]["hits"]["hits"]
            ),
        )

        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Document attachment",
        }
        search_query = DocketDocument.search()
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
        response = s.execute().to_dict()
        self.assertEqual(s.count(), 1)
        self.assertEqual(
            1,
            len(
                response["hits"]["hits"][0]["inner_hits"][
                    "text_query_inner_recap_document"
                ]["hits"]["hits"]
            ),
        )
        self.assertEqual(
            "Document attachment",
                response["hits"]["hits"][0]["inner_hits"][
                    "text_query_inner_recap_document"
                ]["hits"]["hits"][0]["_source"]["short_description"]

        )

        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Maecenas nunc justo",
        }
        search_query = DocketDocument.search()
        s, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
        response = s.execute().to_dict()
        self.assertEqual(s.count(), 1)
        self.assertEqual(
            1,
            len(
                response["hits"]["hits"][0]["inner_hits"][
                    "text_query_inner_recap_document"
                ]["hits"]["hits"]
            ),
        )


    async def test_phrase_plus_conjunction_search(self) -> None:
        """Confirm phrase + conjunction search works properly"""

        params = {
            "q": "",
            "description": '"leave to file" AND amicus',
            "type": SEARCH_TYPES.RECAP,
        }
        r = await self.async_client.get(
            reverse("show_results"),
            params,
        )
        self.assertIn("2 Cases", r.content.decode())
        self.assertIn("SUBPOENAS SERVED ON", r.content.decode())

        params["description"] = '"leave to file" amicus'
        r = await self.async_client.get(
            reverse("show_results"),
            params,
        )
        self.assertIn("2 Cases", r.content.decode())
        self.assertIn("SUBPOENAS SERVED ON", r.content.decode())

        params["description"] = '"leave to file" AND "amicus"'
        r = await self.async_client.get(
            reverse("show_results"),
            params,
        )
        self.assertIn("2 Cases", r.content.decode())
        self.assertIn("SUBPOENAS SERVED ON", r.content.decode())

        params[
            "description"
        ] = '"leave to file" AND "amicus" "Discharging Debtor"'
        r = await self.async_client.get(
            reverse("show_results"),
            params,
        )
        self.assertIn("1 Case", r.content.decode())
        self.assertIn("SUBPOENAS SERVED OFF", r.content.decode())

    async def test_issue_727_doc_att_numbers(self) -> None:
        """Can we send integers to the document number and attachment number
        fields?
        """
        r = await self.async_client.get(
            reverse("show_results"),
            {"type": SEARCH_TYPES.RECAP, "document_number": "1"},
        )
        self.assertEqual(r.status_code, HTTP_200_OK)
        r = await self.async_client.get(
            reverse("show_results"),
            {"type": SEARCH_TYPES.RECAP, "attachment_number": "1"},
        )
        self.assertEqual(r.status_code, HTTP_200_OK)

    async def test_case_name_filter(self) -> None:
        """Confirm case_name filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "SUBPOENAS SERVED OFF",
        }

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "case_name")
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 1, "case_name")

    async def test_court_filter(self) -> None:
        """Confirm court filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "court": "canb"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "court")

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "court")

    async def test_document_description_filter(self) -> None:
        """Confirm description filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "description": "MOTION for Leave to File Amicus Curiae Lorem",
        }

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "description")

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "description")

    async def test_docket_number_filter(self) -> None:
        """Confirm docket_number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "docket_number": "1:21-bk-1234"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "docket_number")

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "docket_number")

    async def test_attachment_number_filter(self) -> None:
        """Confirm attachment number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "attachment_number": 2}

        # Frontend
        await self._test_article_count(params, 1, "attachment_number")
        # API
        await self._test_api_results_count(params, 1, "attachment_number")

    async def test_assigned_to_judge_filter(self) -> None:
        """Confirm assigned_to filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "assigned_to": "Thalassa Miller"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "assigned_to")
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "assigned_to")

    async def test_referred_to_judge_filter(self) -> None:
        """Confirm referred_to_judge filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "referred_to": "Persephone Sinclair",
        }

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "referred_to")
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "referred_to")

    async def test_nature_of_suit_filter(self) -> None:
        """Confirm nature_of_suit filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "nature_of_suit": "440"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "nature_of_suit")
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "nature_of_suit")

    async def test_filed_after_filter(self) -> None:
        """Confirm filed_after filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "filed_after": "2016-08-16"}

        # Frontend
        await self._test_article_count(params, 1, "filed_after")
        # API
        await self._test_api_results_count(params, 1, "filed_after")

    async def test_filed_before_filter(self) -> None:
        """Confirm filed_before filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "filed_before": "2015-08-17"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "filed_before")
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "filed_before")

    async def test_document_number_filter(self) -> None:
        """Confirm document number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "document_number": "3"}

        # Frontend
        await self._test_article_count(params, 1, "document_number")
        # API
        await self._test_api_results_count(params, 1, "document_number")

    async def test_available_only_field(self) -> None:
        """Confirm available only filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "available_only": True}

        # Frontend
        await self._test_article_count(params, 1, "available_only")
        # API
        await self._test_api_results_count(params, 1, "available_only")

    async def test_party_name_filter(self) -> None:
        """Confirm party_name filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "party_name": "Defendant Jane Roe",
        }

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "party_name")
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "party_name")

    async def test_atty_name_filter(self) -> None:
        """Confirm atty_name filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "atty_name": "Debbie Russell"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "atty_name")
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "atty_name")

    async def test_combine_filters(self) -> None:
        """Confirm that combining filters works properly"""
        # Get results for a broad filter
        params = {"type": SEARCH_TYPES.RECAP, "case_name": "SUBPOENAS SERVED"}

        # Frontend, 2 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 2, "case_name")
        # API, 3 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 3, "case_name")

        # Constraint results by adding document number filter.
        params["docket_number"] = "12-1235"
        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "case_name + docket_number")
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(
            params, 1, "case_name + docket_number"
        )

        # Filter at document level.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "docket_number": "1:21-bk-1234",
            "available_only": True,
        }
        # Frontend
        await self._test_article_count(
            params, 1, "docket_number + available_only"
        )
        # API
        await self._test_api_results_count(
            params, 1, "docket_number + available_only"
        )

        # Combine query and filter.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "available_only": True,
            "q": "Amicus Curiae Lorem",
        }
        # Frontend
        r = await self._test_article_count(params, 1, "filter + text query")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "filter + text query"
        )

        # API
        await self._test_api_results_count(params, 1, "filter + text query")

    async def test_docket_child_documents(self) -> None:
        """Confirm results contain the right number of child documents"""
        # Get results for a broad filter
        rd_1 = await sync_to_async(RECAPDocumentFactory)(
            docket_entry=self.de,
            document_number="2",
            is_available=True,
        )
        rd_2 = await sync_to_async(RECAPDocumentFactory)(
            docket_entry=self.de,
            document_number="3",
            is_available=True,
        )
        rd_3 = await sync_to_async(RECAPDocumentFactory)(
            docket_entry=self.de,
            document_number="4",
            is_available=True,
        )
        rd_4 = await sync_to_async(RECAPDocumentFactory)(
            docket_entry=self.de,
            document_number="5",
            is_available=False,
        )
        await sync_to_async(add_docket_to_solr_by_rds)(
            [rd_1.pk, rd_2.pk, rd_3.pk, rd_4.pk], force_commit=True
        )

        params = {"type": SEARCH_TYPES.RECAP, "docket_number": "1:21-bk-1234"}

        # Frontend
        r = await self._test_article_count(params, 1, "docket_number")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 5, "docket_number")

        # Confirm view additional results button is shown.
        self.assertIn("View 1 Additional Result for", r.content.decode())

        # API
        await self._test_api_results_count(params, 6, "docket_number")

        # View additional results:
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"docket_id:{self.de.docket.id}",
        }
        # Frontend
        r = await self._test_article_count(params, 1, "docket_number")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 6, "docket_number")

        # Constraint filter:
        params = {
            "type": SEARCH_TYPES.RECAP,
            "docket_number": "1:21-bk-1234",
            "available_only": True,
        }
        # Frontend
        r = await self._test_article_count(
            params, 1, "docket_number + available_only"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 4, "docket_number + available_only"
        )

        # Confirm view additional results button is not shown.
        self.assertNotIn(
            "View 1 Additional Result for this Case", r.content.decode()
        )
        # API
        await self._test_api_results_count(
            params, 4, "docket_number + available_only"
        )

    async def test_advanced_queries(self) -> None:
        """Confirm advance queries works properly"""
        # Advanced query string, firm
        params = {"type": SEARCH_TYPES.RECAP, "q": "firm:(Associates LLP)"}

        # Frontend
        r = await self._test_article_count(params, 1, "advance firm")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 2, "advance firm")

        # API
        await self._test_api_results_count(params, 2, "advance firm")

        # Advanced query string, firm AND short_description
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": 'firm:(Associates LLP) AND short_description:"Document attachment"',
        }

        # Frontend
        r = await self._test_article_count(
            params, 1, "advance firm AND short_description"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "advance firm AND short_description"
        )
        # API
        await self._test_api_results_count(
            params, 1, "advance firm AND short_description"
        )

        # Advanced query string, page_count OR document_type
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "page_count:5 OR document_type:Attachment",
        }

        # Frontend
        r = await self._test_article_count(
            params, 1, "page_count OR document_type"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "page_count OR document_type"
        )
        # API
        await self._test_api_results_count(
            params, 2, "page_count OR document_type"
        )

        # Advanced query string, entry_date_filed NOT document_type
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "entry_date_filed:[2015-08-18T00:00:00Z TO 2015-08-20T00:00:00Z] NOT document_type:Attachment",
        }

        # Frontend
        r = await self._test_article_count(
            params, 1, "page_count OR document_type"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "page_count OR document_type"
        )
        # API
        await self._test_api_results_count(
            params, 1, "page_count OR document_type"
        )

        # Advanced query string, "SUBPOENAS SERVED" NOT "OFF"
        params = {"type": SEARCH_TYPES.RECAP, "q": "SUBPOENAS SERVED NOT OFF"}

        # Frontend
        r = await self._test_article_count(
            params, 1, '"SUBPOENAS SERVED" NOT "OFF"'
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, '"SUBPOENAS SERVED" NOT "OFF"'
        )
        # API
        await self._test_api_results_count(
            params, 2, '"SUBPOENAS SERVED" NOT "OFF"'
        )

    async def test_text_queries(self) -> None:
        """Confirm text queries works properly"""
        # Text query case name.
        params = {"type": SEARCH_TYPES.RECAP, "q": "SUBPOENAS SERVED OFF"}

        # Frontend
        r = await self._test_article_count(params, 1, "text query case name")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "text query case name"
        )

        # API
        await self._test_api_results_count(params, 1, "text query case name")

        # Text query description.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Amicus Curiae Lorem"}

        # Frontend
        r = await self._test_article_count(params, 1, "text query description")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "text query description"
        )

        # API
        await self._test_api_results_count(params, 2, "text query description")

        # Text query text.
        params = {"type": SEARCH_TYPES.RECAP, "q": "PACER Document Franklin"}

        # Frontend
        r = await self._test_article_count(params, 1, "text query text")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "text query text"
        )
        # API
        await self._test_api_results_count(params, 1, "text query text")

        # Text query text judge.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Thalassa Miller"}

        # Frontend
        r = await self._test_article_count(params, 1, "text query judge")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "text query judge"
        )
        # API
        await self._test_api_results_count(params, 2, "text query judge")

    async def test_results_highlights(self) -> None:
        """Confirm highlights are shown properly"""

        # Highlight case name.
        params = {"type": SEARCH_TYPES.RECAP, "q": "SUBPOENAS SERVED OFF"}

        r = await self._test_article_count(params, 1, "highlights case name")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "highlights case name"
        )

        self.assertIn("<mark>SUBPOENAS</mark>", r.content.decode())
        self.assertIn("<mark>SERVED</mark>", r.content.decode())
        self.assertIn("<mark>OFF</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>OFF</mark>"), 1)

        # Highlight assigned_to.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Thalassa Miller"}

        r = await self._test_article_count(params, 1, "highlights assigned_to")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "highlights case name"
        )

        self.assertIn("<mark>Thalassa</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Thalassa</mark>"), 3)

        # Highlight referred_to.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Persephone Sinclair"}

        r = await self._test_article_count(params, 1, "highlights referred_to")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "highlights case name"
        )

        self.assertIn("<mark>Persephone</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Persephone</mark>"), 3
        )

        # Highlight docketNumber.
        params = {"type": SEARCH_TYPES.RECAP, "q": "1:21-bk-1234"}

        r = await self._test_article_count(
            params, 1, "highlights docketNumber"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "highlights docketNumber"
        )

        self.assertIn("<mark>1:21-bk-1234</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>1:21-bk-1234</mark>"), 3
        )

        # Highlight description.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Discharging Debtor"}

        r = await self._test_article_count(params, 1, "highlights description")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "highlights description"
        )

        self.assertIn("<mark>Discharging</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Discharging</mark>"), 1
        )

        # Highlight suitNature and text.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Lorem 440"}

        r = await self._test_article_count(params, 1, "highlights suitNature")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "highlights suitNature"
        )
        self.assertIn("<mark>440</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>440</mark>"), 3)

        # TODO Filter highlights don't work in Solr. Fix it in ES and add tests

    async def test_results_api_fields(self) -> None:
        """Confirm fields in RECAP Search API results."""
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Discharging Debtor",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_to_check = [
            "absolute_url",
            "assignedTo",
            "assigned_to_id",
            "attachment_number",
            "attorney",
            "attorney_id",
            "caseName",
            "cause",
            "court",
            "court_citation_string",
            "court_exact",
            "court_id",
            "dateArgued",
            "dateFiled",
            "dateTerminated",
            "description",
            "docketNumber",
            "docket_absolute_url",
            "docket_entry_id",
            "docket_id",
            "document_number",
            "document_type",
            "entry_date_filed",
            "entry_number",
            "filepath_local",
            "firm",
            "firm_id",
            "id",
            "is_available",
            "jurisdictionType",
            "juryDemand",
            "page_count",
            "party",
            "party_id",
            "referredTo",
            "referred_to_id",
            "short_description",
            "snippet",
            "suitNature",
            "timestamp",
        ]
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, 40)
        for key in keys_to_check:
            self.assertTrue(
                key in r.data["results"][0],
                msg=f"Key {key} not found in the result object.",
            )

    async def test_results_ordering(self) -> None:
        """Confirm results ordering works properly"""
        # Order by random order.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "random_123 desc",
        }
        # Frontend
        await self._test_article_count(params, 2, "order random desc")
        # API
        await self._test_api_results_count(params, 3, "order random")

        # Order by score desc (relevance).
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "score desc",
        }
        # Frontend
        r = await self._test_article_count(params, 2, "order score desc")
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by desc.",
        )
        # API
        r = await self._test_api_results_count(params, 3, "order score desc")
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by desc.",
        )

        # Order by entry_date_filed desc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "entry_date_filed desc",
        }
        # Frontend
        r = await self._test_article_count(params, 2, "order dateFiled desc")
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by desc.",
        )

        # API
        r = await self._test_api_results_count(params, 3, "order")
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by desc.",
        )

        # Order by entry_date_filed asc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "entry_date_filed asc",
        }
        # Frontend
        r = await self._test_article_count(params, 2, "order dateFiled desc")
        self.assertTrue(
            r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234"),
            msg="'12-1235' should come BEFORE '1:21-bk-1234' when order_by asc.",
        )
        # API
        r = await self._test_api_results_count(params, 3, "order")
        self.assertTrue(
            r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234"),
            msg="'12-1235' should come BEFORE '1:21-bk-1234' when order_by asc.",
        )

        # Order by dateFiled desc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled desc",
        }

        # Frontend
        r = await self._test_article_count(params, 2, "order dateFiled desc")
        self.assertTrue(
            r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234"),
            msg="'12-1235' should come BEFORE '1:21-bk-1234' when order_by desc.",
        )

        # Order by dateFiled asc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled asc",
        }
        # Frontend
        r = await self._test_article_count(params, 2, "order dateFiled asc")
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by asc.",
        )

    @unittest.skipIf(
        tests_running_over_solr, "Skip in SOlR due to a existing bug."
    )
    async def test_api_results_date_filed_ordering(self) -> None:
        """Confirm api results date_filed ordering works properly"""

        # Order by dateFiled desc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled desc",
        }
        # API
        r = await self._test_api_results_count(params, 3, "order")
        self.assertTrue(
            r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234"),
            msg="'12-1235' should come BEFORE '1:21-bk-1234' when order_by desc.",
        )

        # Order by dateFiled asc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled asc",
        }

        # API
        r = await self._test_api_results_count(params, 3, "order")
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by asc.",
        )
