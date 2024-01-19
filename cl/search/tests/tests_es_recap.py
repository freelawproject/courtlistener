import datetime
import re
import unittest
from unittest import mock

from asgiref.sync import async_to_sync, sync_to_async
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import AsyncClient, override_settings
from django.urls import reverse
from elasticsearch_dsl import Q
from lxml import etree, html
from rest_framework.status import HTTP_200_OK

from cl.lib.elasticsearch_utils import build_es_main_query
from cl.lib.redis_utils import make_redis_interface
from cl.lib.test_helpers import IndexedSolrTestCase, RECAPSearchTestCase
from cl.lib.view_utils import increment_view_count
from cl.people_db.factories import (
    AttorneyFactory,
    AttorneyOrganizationFactory,
    PartyFactory,
    PartyTypeFactory,
    PersonFactory,
)
from cl.search.documents import ES_CHILD_ID, DocketDocument, ESRECAPDocument
from cl.search.factories import (
    BankruptcyInformationFactory,
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    OpinionWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.search.management.commands.cl_index_parent_and_child_docs import (
    compose_redis_key,
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.models import (
    SEARCH_TYPES,
    OpinionsCitedByRECAPDocument,
    RECAPDocument,
)
from cl.search.tasks import (
    add_docket_to_solr_by_rds,
    es_save_document,
    index_docket_parties_in_es,
    update_es_document,
)
from cl.tests.cases import (
    CountESTasksTestCase,
    ESIndexTestCase,
    TestCase,
    TransactionTestCase,
)


class RECAPSearchTest(RECAPSearchTestCase, ESIndexTestCase, TestCase):
    """
    RECAP Search Tests
    """

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")
        super().setUpTestData()
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )
        # Index parties in ES.
        index_docket_parties_in_es.delay(cls.de.docket.pk)

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
            msg="Did not get the right number of child documents %s\n"
            "Expected: %s\n"
            "     Got: %s\n\n" % (field_name, expected_count, got),
        )

    def _test_main_es_query(self, cd, parent_expected, field_name):
        search_query = DocketDocument.search()
        (
            s,
            total_query_results,
            top_hits_limit,
            total_child_results,
        ) = build_es_main_query(search_query, cd)
        self.assertEqual(
            total_query_results,
            parent_expected,
            msg="Did not get the right number of parent documents %s\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            % (field_name, parent_expected, total_query_results),
        )

        return s.execute().to_dict()

    def _compare_response_child_value(
        self,
        response,
        parent_index,
        child_index,
        expected_value,
        field_name,
    ):
        self.assertEqual(
            expected_value,
            response["hits"]["hits"][parent_index]["inner_hits"][
                "filter_query_inner_recap_document"
            ]["hits"]["hits"][child_index]["_source"][field_name],
            msg=f"Did not get the right {field_name} value.",
        )

    def _count_child_documents_dict(
        self, hit, response, expected_count, field_name
    ):
        got = len(
            response["hits"]["hits"][hit]["inner_hits"][
                "filter_query_inner_recap_document"
            ]["hits"]["hits"]
        )
        self.assertEqual(
            expected_count,
            got,
            msg="Did not get the right number of child documents %s\n"
            "Expected: %s\n"
            "     Got: %s\n\n" % (field_name, expected_count, got),
        )

    def test_has_child_text_queries(self) -> None:
        """Test has_child text queries."""
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Discharging Debtor",
        }
        response = self._test_main_es_query(cd, 1, "q")
        self.assertEqual(
            1,
            len(
                response["hits"]["hits"][0]["inner_hits"][
                    "filter_query_inner_recap_document"
                ]["hits"]["hits"]
            ),
        )

        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Document attachment",
        }
        response = self._test_main_es_query(cd, 1, "q")
        self.assertEqual(
            1,
            len(
                response["hits"]["hits"][0]["inner_hits"][
                    "filter_query_inner_recap_document"
                ]["hits"]["hits"]
            ),
        )
        self.assertEqual(
            "Document attachment",
            response["hits"]["hits"][0]["inner_hits"][
                "filter_query_inner_recap_document"
            ]["hits"]["hits"][0]["_source"]["short_description"],
        )

        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Maecenas nunc justo",
        }
        response = self._test_main_es_query(cd, 1, "q")
        self.assertEqual(
            1,
            len(
                response["hits"]["hits"][0]["inner_hits"][
                    "filter_query_inner_recap_document"
                ]["hits"]["hits"]
            ),
        )

    def test_child_and_parent_filter_queries(self) -> None:
        """Test has_child filters method."""

        # Filter by parent field, court.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "court": "ca1",
        }
        r = self._test_main_es_query(cd, 1, "court")
        self._count_child_documents_dict(0, r, 1, "court filter")

        # Filter by parent field, caseName
        cd = {"type": SEARCH_TYPES.RECAP, "case_name": "SUBPOENAS SERVED ON"}

        r = self._test_main_es_query(cd, 1, "caseName")
        self._count_child_documents_dict(0, r, 2, "caseName filter")

        # Filter by child field, description
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "description": "Amicus Curiae Lorem",
        }
        r = self._test_main_es_query(cd, 1, "description")
        self._count_child_documents_dict(0, r, 2, "description filter")

        # Filter by child field, description
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "document_number": 3,
        }
        r = self._test_main_es_query(cd, 1, "document_number")
        self._count_child_documents_dict(0, r, 1, "document_number filter")

        # Combine child filters
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "description": "Amicus Curiae Lorem",
            "available_only": True,
        }
        r = self._test_main_es_query(cd, 1, "description +  available_only")
        self._count_child_documents_dict(
            0, r, 1, "description +  available_only"
        )

        # Combine parent-child filters
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "docket_number": "1:21-bk-1234",
            "attachment_number": 2,
        }
        r = self._test_main_es_query(
            cd, 1, "docket_number + attachment_number"
        )
        self._count_child_documents_dict(
            0, r, 1, "docket_number + attachment_number"
        )

        # Combine parent filter and query.
        cd = {
            "type": SEARCH_TYPES.RECAP,
            "docket_number": "1:21-bk-1234",
            "q": "Document attachment",
        }
        r = self._test_main_es_query(cd, 1, "q")
        self._count_child_documents_dict(
            0, r, 1, "docket_number + Document attachment"
        )

    async def test_recap_dockets_search_type(self) -> None:
        """Confirm dockets search type works properly"""

        # Perform a RECAP search type.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Amicus Curiae Lorem"}
        # Frontend
        r = await self._test_article_count(params, 1, "text query description")
        # Two child documents are shown.
        self._count_child_documents(
            0, r.content.decode(), 2, "text query description"
        )
        # No View Additional Results button is shown.
        self.assertNotIn("View Additional Results for", r.content.decode())

        # Perform the same query with DOCKETS search type.
        params["type"] = SEARCH_TYPES.DOCKETS
        # Frontend
        r = await self._test_article_count(params, 1, "text query description")
        # Only 1 child document is shown.
        self._count_child_documents(
            0, r.content.decode(), 1, "text query description"
        )
        # The View Additional Results button is shown.
        self.assertIn("View Additional Results for", r.content.decode())

    def test_match_all_query_and_docket_entries_count(self) -> None:
        """Confirm a RECAP search with no params return a match all query.
        The case and docket entries count is available.
        """

        # Perform a RECAP match all search.
        params = {"type": SEARCH_TYPES.RECAP}
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 2, "match all query"
        )
        # Two cases are returned.
        self.assertIn("2 Cases", r.content.decode())
        # 3 Docket entries in count.
        self.assertIn("3 Docket", r.content.decode())

        with self.captureOnCommitCallbacks(execute=True):
            # Confirm an empty docket is shown in a match_all query.
            empty_docket = DocketFactory(
                court=self.court,
                case_name="America vs Ipsum",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:21-bk-1235",
            )

        r = async_to_sync(self._test_article_count)(
            params, 3, "match all query"
        )
        # 3 cases are returned.
        self.assertIn("3 Cases", r.content.decode())
        # 3 Docket entries in count.
        self.assertIn("3 Docket", r.content.decode())
        with self.captureOnCommitCallbacks(execute=True):
            empty_docket.delete()

    def test_sorting(self) -> None:
        """Can we do sorting on various fields?"""
        sort_fields = [
            "score desc",
            "dateFiled desc",
            "dateFiled asc",
            "random_123 desc",
        ]
        for sort_field in sort_fields:
            r = self.client.get(
                "/", {"type": SEARCH_TYPES.RECAP, "order_by": sort_field}
            )
            self.assertNotIn(
                "an error",
                r.content.decode().lower(),
                msg=f"Got an error when doing a judge search ordered by {sort_field}",
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

    async def test_court_filter(self) -> None:
        """Confirm court filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "court": "canb"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "court")

    async def test_document_description_filter(self) -> None:
        """Confirm description filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "description": "MOTION for Leave to File Amicus Curiae Lorem",
        }

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "description")

    async def test_docket_number_filter(self) -> None:
        """Confirm docket_number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "docket_number": "1:21-bk-1234"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "docket_number")

    async def test_attachment_number_filter(self) -> None:
        """Confirm attachment number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "attachment_number": 2}

        # Frontend
        await self._test_article_count(params, 1, "attachment_number")

    async def test_assigned_to_judge_filter(self) -> None:
        """Confirm assigned_to filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "assigned_to": "Thalassa Miller"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "assigned_to")

    async def test_referred_to_judge_filter(self) -> None:
        """Confirm referred_to_judge filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "referred_to": "Persephone Sinclair",
        }

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "referred_to")

    async def test_nature_of_suit_filter(self) -> None:
        """Confirm nature_of_suit filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "nature_of_suit": "440"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "nature_of_suit")

    async def test_filed_after_filter(self) -> None:
        """Confirm filed_after filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "filed_after": "2016-08-16"}

        # Frontend
        await self._test_article_count(params, 1, "filed_after")

    async def test_filed_before_filter(self) -> None:
        """Confirm filed_before filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "filed_before": "2015-08-17"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "filed_before")

    async def test_document_number_filter(self) -> None:
        """Confirm document number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "document_number": "3"}

        # Frontend
        await self._test_article_count(params, 1, "document_number")

    def test_available_only_field(self) -> None:
        """Confirm available only filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "available_only": True}

        # Frontend
        async_to_sync(self._test_article_count)(params, 1, "available_only")

        # Add docket with no document
        with self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="Reese Exploration v. Williams Natural Gas ",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="5:90-cv-04007",
                nature_of_suit="440",
            )

        # perform the previous query and check we still get one result
        async_to_sync(self._test_article_count)(params, 1, "available_only")

        # perform a text query using the name of the new docket and the available_only filter
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Reese",
            "available_only": True,
        }
        async_to_sync(self._test_article_count)(params, 0, "available_only")

        # add a document that is not available to the new docket
        with self.captureOnCommitCallbacks(execute=True):
            entry = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2015, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem",
            )
            recap_document = RECAPDocumentFactory(
                docket_entry=entry,
                description="New File",
                document_number="1",
                is_available=False,
                page_count=5,
            )

        # Query all documents but only show results with PDFs
        params = {"type": SEARCH_TYPES.RECAP, "available_only": True}
        async_to_sync(self._test_article_count)(params, 1, "available_only")

        # Repeat the text query using the name of the new docket
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Reese",
            "available_only": True,
        }
        async_to_sync(self._test_article_count)(params, 0, "available_only")

        # Update the status of the document to reflect it's available
        with self.captureOnCommitCallbacks(execute=True):
            recap_document.is_available = True
            recap_document.save()

        # Query all documents but only show results with PDFs
        params = {"type": SEARCH_TYPES.RECAP, "available_only": True}
        async_to_sync(self._test_article_count)(params, 2, "available_only")

        # Repeat text search, 1 result expected since the doc is available now
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Reese",
            "available_only": True,
        }
        async_to_sync(self._test_article_count)(params, 1, "available_only")

        with self.captureOnCommitCallbacks(execute=True):
            docket.delete()

    def test_show_documents_when_combining_the_is_available_filter(self):
        """Confirm documents are being shown properly when using the is_available filter"""
        # Add docket with available documents
        with self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="NYU Hospitals Center v. League of Voluntary Hospitals",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:17-cv-04465",
                nature_of_suit="440",
            )
            e_1_d_1 = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2015, 8, 19),
                description="United Healthcare Workers East, League of Voluntary Hospitals and Homes of New York",
            )
            RECAPDocumentFactory(
                docket_entry=e_1_d_1,
                document_number="1",
                is_available=True,
                page_count=5,
            )
            e_2_d_1 = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=2,
                date_filed=datetime.date(2015, 8, 19),
                description="Not available document for the League of Voluntary Hospitals and Homes of New York",
            )
            RECAPDocumentFactory(
                docket_entry=e_2_d_1,
                document_number="2",
                is_available=False,
                page_count=5,
            )

            docket_2 = DocketFactory(
                court=self.court,
                case_name="Eaton Vance AZ Muni v. National Voluntary",
                docket_number="1:17-cv-04465",
            )
            e_28_d_2 = DocketEntryWithParentsFactory(
                docket=docket_2,
                entry_number=28,
                description="ORDER granting 27 Motion to Continue",
            )
            RECAPDocumentFactory(
                docket_entry=e_28_d_2,
                document_number="28",
                is_available=False,
                page_count=5,
            )
            e_29_d_2 = DocketEntryWithParentsFactory(
                docket=docket_2,
                entry_number=29,
                description="ORDER granting 23 Motion for More Definite Statement. Signed by Judge Mary H Murguia",
            )
            RECAPDocumentFactory(
                docket_entry=e_29_d_2,
                document_number="29",
                is_available=True,
            )

            docket_3 = DocketFactory(
                court=self.court,
                case_name="Kathleen B. Thomas",
                docket_number="1:17-cv-04465",
            )
            e_14_d_3 = DocketEntryWithParentsFactory(
                docket=docket_3,
                entry_number=14,
                description="Petition Completed March 29, 2019 Filed by Debtor Kathleen B. Thomas",
            )
            RECAPDocumentFactory(
                docket_entry=e_14_d_3,
                document_number="14",
                is_available=False,
            )
            e_27_d_3 = DocketEntryWithParentsFactory(
                docket=docket_3,
                entry_number=27,
                description="Financial Management Course Certificate Filed by Debtor Kathleen B. Thomas",
            )
            RECAPDocumentFactory(
                docket_entry=e_27_d_3,
                document_number="27",
                is_available=True,
            )

        # Query all documents with the word "Voluntary" in the case name and only show results with PDFs
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "Voluntary",
            "available_only": True,
        }
        r = async_to_sync(self._test_article_count)(
            params, 2, "case_name + available_only"
        )
        self.assertIn("Document #1", r.content.decode())
        self.assertNotIn("Document #28", r.content.decode())
        self.assertIn("Document #29", r.content.decode())

        # Query all documents with the word "Kathleen" in the description and only show results with PDFs
        params = {
            "type": SEARCH_TYPES.RECAP,
            "description": "Kathleen",
            "available_only": True,
        }
        r = async_to_sync(self._test_article_count)(
            params, 1, "description + available_only"
        )
        self.assertIn("Document #27", r.content.decode())
        self.assertNotIn("Document #14", r.content.decode())

        # Query all documents with the word "Voluntary" in the description and case name
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "Voluntary",
            "description": "Voluntary",
        }
        r = async_to_sync(self._test_article_count)(
            params, 1, "case_name + description + available_only"
        )
        self.assertIn("Document #1", r.content.decode())
        self.assertIn("Document #2", r.content.decode())

        # Query all documents with the word "Voluntary" in the description and case name and only show results with PDFs
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "Voluntary",
            "description": "Voluntary",
            "available_only": True,
        }
        r = async_to_sync(self._test_article_count)(
            params, 1, "case_name + description + available_only"
        )
        self.assertIn("Document #1", r.content.decode())

        # test the combination of the text query and the available_only filter
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": '"Voluntary Hospitals"',
            "available_only": True,
        }
        r = async_to_sync(self._test_article_count)(
            params, 1, "case_name + available_only"
        )
        self.assertIn("Document #1", r.content.decode())

        with self.captureOnCommitCallbacks(execute=True):
            docket.delete()
            docket_2.delete()
            docket_3.delete()

    def test_filter_docket_with_no_documents(self) -> None:
        """Confirm we can filter dockets with no documents"""

        # Add dockets with no documents
        with self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="Ready Mix Hampton",
                date_filed=datetime.date(2021, 8, 16),
            )
            BankruptcyInformationFactory(docket=docket, chapter="7")

            docket_2 = DocketFactory(
                court=self.court,
                case_name="Ready Mix Hampton",
                date_filed=datetime.date(2021, 8, 16),
            )
            BankruptcyInformationFactory(docket=docket_2, chapter="8")

        cd = {
            "type": SEARCH_TYPES.RECAP,
            "q": "chapter:7",
            "court": f"{self.court.pk} innb",
            "case_name": "ready mix",
            "filed_after": datetime.date(2020, 1, 1),
        }
        async_to_sync(self._test_article_count)(
            cd, 1, "court + case_name + filed_after + query_string"
        )
        with self.captureOnCommitCallbacks(execute=True):
            docket.delete()
            docket_2.delete()

    async def test_party_name_filter(self) -> None:
        """Confirm party_name filter works properly"""

        params = {
            "type": SEARCH_TYPES.RECAP,
            "party_name": "Defendant Jane Roe",
        }

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "party_name")

    def test_party_name_and_children_filter(self) -> None:
        """Confirm dockets with children are shown when using the party filter"""
        with self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="Mott v. NYU Hospitals Center",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:17-cv-04465",
                nature_of_suit="440",
            )
            e_1_d_1 = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2015, 8, 19),
                description="COMPLAINT against NYU Hospitals Center, Tisch Hospital",
            )
            RECAPDocumentFactory(
                docket_entry=e_1_d_1,
                document_number="1",
                is_available=True,
                page_count=5,
            )
            e_2_d_1 = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=2,
                date_filed=datetime.date(2015, 8, 19),
                description="Not available document for Mott v. NYU Hospitals Center",
            )
            RECAPDocumentFactory(
                docket_entry=e_2_d_1,
                document_number="2",
                is_available=False,
                page_count=5,
            )

        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "hospital",
            "description": "center",
            "party_name": "Frank Paul Sabatini",
        }

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        r = async_to_sync(self._test_article_count)(
            params, 1, "text query + description + party_name"
        )
        self.assertIn("Document #1", r.content.decode())
        self.assertIn("Document #2", r.content.decode())

        with self.captureOnCommitCallbacks(execute=True):
            e_2_d_1.delete()
            e_1_d_1.delete()
            docket.delete()

    async def test_atty_name_filter(self) -> None:
        """Confirm atty_name filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "atty_name": "Debbie Russell"}

        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "atty_name")

    async def test_combine_filters(self) -> None:
        """Confirm that combining filters works properly"""
        # Get results for a broad filter
        params = {"type": SEARCH_TYPES.RECAP, "case_name": "SUBPOENAS SERVED"}

        # Frontend, 2 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 2, "case_name")

        # Constraint results by adding document number filter.
        params["docket_number"] = "12-1235"
        # Frontend, 1 result expected since RECAPDocuments are grouped by case
        await self._test_article_count(params, 1, "case_name + docket_number")

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
            0, r.content.decode(), 1, "child filter + text query"
        )

    @override_settings(VIEW_MORE_CHILD_HITS=6)
    def test_docket_child_documents(self) -> None:
        """Confirm results contain the right number of child documents"""
        # Get results for a broad filter
        with self.captureOnCommitCallbacks(execute=True):
            rd_1 = RECAPDocumentFactory(
                docket_entry=self.de,
                document_number="2",
                is_available=True,
            )
            rd_2 = RECAPDocumentFactory(
                docket_entry=self.de,
                document_number="3",
                is_available=True,
            )
            rd_3 = RECAPDocumentFactory(
                docket_entry=self.de,
                document_number="4",
                is_available=True,
            )
            rd_4 = RECAPDocumentFactory(
                docket_entry=self.de,
                document_number="5",
                is_available=False,
            )
            rd_5 = RECAPDocumentFactory(
                docket_entry=self.de,
                document_number="6",
                is_available=False,
            )

        params = {"type": SEARCH_TYPES.RECAP, "docket_number": "1:21-bk-1234"}
        # Frontend
        r = async_to_sync(self._test_article_count)(params, 1, "docket_number")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 5, "docket_number")

        # Confirm view additional results button is shown.
        self.assertIn("View Additional Results for", r.content.decode())

        # View additional results:
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"docket_id:{self.de.docket.id}",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(params, 1, "docket_number")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 6, "docket_number")
        # The "See full docket for details" button is shown if the case has
        # more entries than VIEW_MORE_CHILD_HITS.
        self.assertIn("See full docket for details", r.content.decode())
        self.assertNotIn("View Additional Results for", r.content.decode())

        # Constraint filter:
        params = {
            "type": SEARCH_TYPES.RECAP,
            "docket_number": "1:21-bk-1234",
            "available_only": True,
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 1, "docket_number + available_only"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 4, "docket_number + available_only"
        )
        # Confirm view additional results button is not shown.
        self.assertNotIn(
            "View Additional Results for this Case", r.content.decode()
        )

        # Remove 1 RECAPDocument to ensure the docket does not contain more than
        # VIEW_MORE_CHILD_HITS entries.
        with self.captureOnCommitCallbacks(execute=True):
            rd_1.delete()
        # View additional results query:
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"docket_id:{self.de.docket.id}",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(params, 1, "docket_number")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 6, "docket_number")
        # The "See full docket for details" button is not shown because the case
        # does not contain more than VIEW_MORE_CHILD_HITS entries.
        self.assertNotIn("See full docket for details", r.content.decode())
        self.assertNotIn("View Additional Results for", r.content.decode())

        with self.captureOnCommitCallbacks(execute=True):
            rd_2.delete()
            rd_3.delete()
            rd_4.delete()
            rd_5.delete()

    async def test_advanced_queries(self) -> None:
        """Confirm advance queries works properly"""
        # Advanced query string, firm
        params = {"type": SEARCH_TYPES.RECAP, "q": "firm:(Associates LLP)"}

        # Frontend
        r = await self._test_article_count(params, 1, "advance firm")
        # No child documents in this query since parties are only indexed
        # at Docket level.
        self._count_child_documents(0, r.content.decode(), 0, "advance firm")

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

        # Advanced query string, pacer_doc_id
        params = {"type": SEARCH_TYPES.RECAP, "q": "pacer_doc_id:018036652436"}

        # Frontend
        r = await self._test_article_count(params, 1, '"pacer_doc_id"')
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 1, '"pacer_doc_id"')

        # Advanced query string, entry_number
        params = {"type": SEARCH_TYPES.RECAP, "q": "entry_number:1"}

        # Frontend
        r = await self._test_article_count(params, 1, '"pacer_doc_id"')
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 2, '"entry_number"')

    def test_advanced_query_cites(self) -> None:
        """Confirm cites advance query works properly"""

        # Advanced query string, cites
        # Frontend
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"cites:({self.opinion.pk})",
        }

        r = async_to_sync(self._test_article_count)(params, 1, "cites")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 1, '"pacer_doc_id"')

        # Add a new OpinionsCitedByRECAPDocument
        with self.captureOnCommitCallbacks(execute=True):
            opinion_2 = OpinionWithParentsFactory()
            OpinionsCitedByRECAPDocument.objects.bulk_create_with_signal(
                [
                    OpinionsCitedByRECAPDocument(
                        citing_document=self.rd_att,
                        cited_opinion=opinion_2,
                        depth=1,
                    )
                ]
            )
        # Frontend
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"cites:({opinion_2.pk} OR {self.opinion.pk})",
        }
        r = async_to_sync(self._test_article_count)(params, 1, "cites")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 2, '"pacer_doc_id"')
        with self.captureOnCommitCallbacks(execute=True):
            opinion_2.cluster.docket.delete()

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

        # Text query description.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Amicus Curiae Lorem"}

        # Frontend
        r = await self._test_article_count(params, 1, "text query description")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "text query description"
        )

        # Text query text.
        params = {"type": SEARCH_TYPES.RECAP, "q": "PACER Document Franklin"}

        # Frontend
        r = await self._test_article_count(params, 1, "text query text")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "text query text"
        )

        # Text query text judge.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Thalassa Miller"}

        # Frontend
        r = await self._test_article_count(params, 1, "text query judge")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "text query judge"
        )

    @override_settings(NO_MATCH_HL_SIZE=50)
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

        # Confirm we can limit the length of the plain_text snippet using the
        # NO_MATCH_HL_SIZE setting.
        tree = html.fromstring(r.content.decode())
        plain_text = tree.xpath(
            '(//article)[1]/div[@class="bottom"]/div[@class="col-md-offset-half"]/p/text()'
        )
        # Clean the plain_text string.
        plain_text_string = plain_text[0].strip()
        cleaned_plain_text = re.sub(r"\s+", " ", plain_text_string)
        cleaned_plain_text = cleaned_plain_text.replace("…", "")
        # The actual no_match_size in this test using fvh is a bit longer due
        # to it includes an extra word.
        self.assertEqual(len(cleaned_plain_text), 58)

        # Highlight assigned_to.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Thalassa Miller"}

        r = await self._test_article_count(params, 1, "highlights assigned_to")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "highlights case name"
        )

        self.assertIn("<mark>Thalassa</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Thalassa</mark>"), 1)

        # Highlight referred_to.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Persephone Sinclair"}

        r = await self._test_article_count(params, 1, "highlights referred_to")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "highlights case name"
        )

        self.assertIn("<mark>Persephone</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Persephone</mark>"), 1
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

        self.assertIn("<mark>1:21-bk-1234", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>1:21-bk-1234</mark>"), 1
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
        self.assertIn("<mark>Lorem</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Lorem</mark>"), 2)

        # Highlight plain_text exact snippet.
        params = {"type": SEARCH_TYPES.RECAP, "q": 'Maecenas nunc "justo"'}

        r = await self._test_article_count(params, 1, "highlights plain_text")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "highlights plain_text"
        )
        self.assertEqual(r.content.decode().count("<mark>Maecenas</mark>"), 1)
        self.assertEqual(r.content.decode().count("<mark>nunc</mark>"), 1)
        self.assertEqual(r.content.decode().count("<mark>justo</mark>"), 1)

        # Highlight plain_text snippet.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Mauris leo"}

        r = await self._test_article_count(params, 1, "highlights plain_text")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "highlights plain_text"
        )
        self.assertEqual(r.content.decode().count("<mark>Mauris</mark>"), 1)
        self.assertEqual(r.content.decode().count("<mark>leo</mark>"), 1)

        # Highlight short_description.
        params = {"type": SEARCH_TYPES.RECAP, "q": '"Document attachment"'}

        r = await self._test_article_count(params, 1, "short_description")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "highlights plain_text"
        )
        self.assertEqual(r.content.decode().count("<mark>Document</mark>"), 1)
        self.assertEqual(
            r.content.decode().count("<mark>attachment</mark>"), 1
        )

        # Highlight filter: caseName
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "SUBPOENAS SERVED ON",
        }
        r = await self._test_article_count(params, 1, "highlights caseName")
        # Count child documents under docket.
        self.assertIn("<mark>SUBPOENAS</mark>", r.content.decode())
        self.assertIn("<mark>SERVED</mark>", r.content.decode())
        self.assertIn("<mark>ON</mark>", r.content.decode())

        # Highlight filter: description
        params = {
            "type": SEARCH_TYPES.RECAP,
            "description": "Amicus Curiae Lorem",
        }
        r = await self._test_article_count(params, 1, "highlights description")
        self.assertIn("<mark>Amicus</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Amicus</mark>"), 2)

        # Highlight filter: docket number
        params = {
            "type": SEARCH_TYPES.RECAP,
            "docket_number": "1:21-bk-1234",
        }
        r = await self._test_article_count(
            params, 1, "highlights docket number"
        )
        self.assertIn("<mark>1:21-bk-1234", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>1:21-bk-1234</mark>"), 1
        )

        # Highlight filter: Nature of Suit
        params = {
            "type": SEARCH_TYPES.RECAP,
            "nature_of_suit": "440",
        }
        r = await self._test_article_count(
            params, 1, "highlights Nature of Suit"
        )
        self.assertIn("<mark>440</mark>", r.content.decode())

        # Highlight filter: Assigned to
        params = {"type": SEARCH_TYPES.RECAP, "assigned_to": "Thalassa Miller"}
        r = await self._test_article_count(
            params, 1, "highlights Nature of Suit"
        )
        self.assertIn("<mark>Thalassa</mark>", r.content.decode())

        # Highlight filter: Referred to
        params = {"type": SEARCH_TYPES.RECAP, "referred_to": "Persephone"}
        r = await self._test_article_count(params, 1, "highlights Referred to")
        self.assertIn("<mark>Persephone</mark>", r.content.decode())

        # Highlight filter + query
        params = {
            "type": SEARCH_TYPES.RECAP,
            "description": "Amicus Curiae Lorem",
            "q": "Document attachment",
        }
        r = await self._test_article_count(params, 1, "filter + query")
        self.assertIn("<mark>Amicus</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Amicus</mark>"), 1)
        self.assertIn("<mark>Document</mark>", r.content.decode())
        self.assertIn("<mark>attachment</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Document</mark>"), 1)
        self.assertEqual(
            r.content.decode().count("<mark>attachment</mark>"), 1
        )

    @override_settings(NO_MATCH_HL_SIZE=50)
    def test_phrase_search_stemming(self) -> None:
        """Confirm stemming doesn't affect a phrase search."""

        with self.captureOnCommitCallbacks(execute=True):
            rd_1 = RECAPDocumentFactory(
                docket_entry=self.de,
                document_number="10",
                is_available=False,
                plain_text="Lorem Dr. Israel also demonstrated a misunderstanding and misapplication of antitrust concepts Ipsum",
            )

        search_phrase = '"Dr. Israel also demonstrated a misunderstanding and misapplication of antitrust concepts"'
        params = {"type": SEARCH_TYPES.RECAP, "q": search_phrase}
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 1, "phrase_search_stemming"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "phrase_search_stemming"
        )

        # Confirm phrase search are properly highlighted.
        terms_list = search_phrase.replace('"', "").split(" ")
        for term in terms_list:
            self.assertIn(f"<mark>{term}</mark>", r.content.decode())

        with self.captureOnCommitCallbacks(execute=True):
            rd_1.delete()

    @override_settings(NO_MATCH_HL_SIZE=50)
    def test_phrase_search_duplicated_terms(self) -> None:
        """Confirm duplicated terms doesn't affect a phrase search."""

        with self.captureOnCommitCallbacks(execute=True):
            rd_1 = RECAPDocumentFactory(
                docket_entry=self.de,
                document_number="11",
                is_available=False,
                plain_text="Lorem this was finished, this unwieldy process has led ipsum,",
            )

        # This phrase shouldn't return results since it doesn't match the
        # original content.
        search_phrase = '"this was finished, unwieldy process"'
        params = {"type": SEARCH_TYPES.RECAP, "q": search_phrase}
        # Frontend
        async_to_sync(self._test_article_count)(
            params, 0, "phrase_search_duplicated_terms"
        )

        # This phrase should match a result.
        search_phrase = '"this was finished, this unwieldy process"'
        params = {"type": SEARCH_TYPES.RECAP, "q": search_phrase}
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 1, "phrase_search_duplicated_terms"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "phrase_search_duplicated_terms"
        )

        # Confirm phrase search are properly highlighted.
        terms_list = search_phrase.replace('"', "").split(" ")
        for term in terms_list:
            self.assertIn(f"<mark>{term}</mark>", r.content.decode())

        # Confirm we're able to HL terms combined with chars like ",", "." or
        # or any other symbols.
        search_phrase = '"this was finished, this unwieldy process" ipsum'
        params = {"type": SEARCH_TYPES.RECAP, "q": search_phrase}
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 1, "phrase_search_duplicated_terms"
        )
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 1, "phrase_search_duplicated_terms"
        )

        # Confirm phrase search are properly highlighted.
        terms_list = search_phrase.replace('"', "").split(" ")
        for term in terms_list:
            self.assertIn(f"<mark>{term}</mark>", r.content.decode())

        with self.captureOnCommitCallbacks(execute=True):
            rd_1.delete()

    def test_results_ordering(self) -> None:
        """Confirm results ordering works properly"""
        # Order by random order.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "random_123 desc",
        }
        # Frontend
        async_to_sync(self._test_article_count)(params, 2, "order random desc")

        # Order by score desc (relevance).
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "score desc",
        }
        # Frontend
        async_to_sync(self._test_article_count)(params, 2, "order score desc")

        with self.captureOnCommitCallbacks(execute=True):
            de_4 = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    docket_number="12-1236",
                    court=self.court_2,
                    case_name="SUBPOENAS SERVED FOUR",
                ),
                entry_number=4,
                date_filed=None,
            )
            rd_4 = RECAPDocumentFactory(
                docket_entry=de_4,
                document_number="4",
            )
            empty_docket = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED FIVE",
                docket_number="12-1237",
            )

        # Order by entry_date_filed desc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "entry_date_filed desc",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 4, "order entry_date_filed desc"
        )
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235")
            < r.content.decode().index("12-1236")
            < r.content.decode().index("12-1237"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by entry_date_filed  desc.",
        )

        # Order by entry_date_filed asc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "entry_date_filed asc",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 4, "order entry_date_filed asc"
        )
        self.assertTrue(
            r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1236")
            < r.content.decode().index("12-1237"),
            msg="'12-1235' should come BEFORE '1:21-bk-1234' when order_by entry_date_filed asc.",
        )
        with self.captureOnCommitCallbacks(execute=True):
            rd_4.docket_entry.docket.delete()
            empty_docket.delete()

        # Order by dateFiled desc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled desc",
        }

        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 2, "order dateFiled desc"
        )
        self.assertTrue(
            r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234"),
            msg="'12-1235' should come BEFORE '1:21-bk-1234' when order_by dateFiled desc.",
        )

        # Order by dateFiled asc
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled asc",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 2, "order dateFiled asc"
        )
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by dateFiled asc.",
        )

        with self.captureOnCommitCallbacks(execute=True):
            de_4.delete()

    @mock.patch("cl.lib.es_signal_processor.chain")
    async def test_avoid_updating_docket_in_es_on_view_count_increment(
        self, mock_es_save_chain
    ) -> None:
        """Confirm a docket is not updated in ES on a view_count increment."""

        with self.captureOnCommitCallbacks(execute=True):
            docket = await sync_to_async(DocketFactory)(
                court=self.court,
                case_name="Lorem Ipsum",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:21-bk-1234",
                assigned_to=None,
                referred_to=None,
                nature_of_suit="440",
            )
        # Restart save chain mock count.
        mock_es_save_chain.reset_mock()
        self.assertEqual(mock_es_save_chain.call_count, 0)

        request_factory = AsyncClient()
        request = await request_factory.get("/docket/")
        with mock.patch("cl.lib.view_utils.is_bot", return_value=False):
            # Increase the view_count.
            await increment_view_count(docket, request)

        # The save chain shouldn't be called.
        self.assertEqual(mock_es_save_chain.call_count, 0)
        with self.captureOnCommitCallbacks(execute=True):
            await docket.adelete()


class RECAPSearchAPIV3Test(RECAPSearchTestCase, IndexedSolrTestCase):
    """
    RECAP Search API V3 Tests
    """

    tests_running_over_solr = True

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def setUp(self) -> None:
        add_docket_to_solr_by_rds(
            [self.rd.pk, self.rd_att.pk], force_commit=True
        )
        add_docket_to_solr_by_rds([self.rd_2.pk], force_commit=True)
        super().setUp()

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

    async def test_case_name_filter(self) -> None:
        """Confirm case_name filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "SUBPOENAS SERVED OFF",
        }

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 1, "case_name")

    async def test_court_filter(self) -> None:
        """Confirm court filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "court": "canb"}

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "court")

    async def test_document_description_filter(self) -> None:
        """Confirm description filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "description": "MOTION for Leave to File Amicus Curiae Lorem",
        }
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "description")

    async def test_docket_number_filter(self) -> None:
        """Confirm docket_number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "docket_number": "1:21-bk-1234"}

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "docket_number")

    async def test_attachment_number_filter(self) -> None:
        """Confirm attachment number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "attachment_number": 2}

        # API
        await self._test_api_results_count(params, 1, "attachment_number")

    async def test_assigned_to_judge_filter(self) -> None:
        """Confirm assigned_to filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "assigned_to": "Thalassa Miller"}

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "assigned_to")

    async def test_referred_to_judge_filter(self) -> None:
        """Confirm referred_to_judge filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "referred_to": "Persephone Sinclair",
        }

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "referred_to")

    async def test_nature_of_suit_filter(self) -> None:
        """Confirm nature_of_suit filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "nature_of_suit": "440"}

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "nature_of_suit")

    async def test_filed_after_filter(self) -> None:
        """Confirm filed_after filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "filed_after": "2016-08-16"}

        # API
        await self._test_api_results_count(params, 1, "filed_after")

    async def test_filed_before_filter(self) -> None:
        """Confirm filed_before filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "filed_before": "2015-08-17"}

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "filed_before")

    async def test_document_number_filter(self) -> None:
        """Confirm document number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "document_number": "3"}

        # API
        await self._test_api_results_count(params, 1, "document_number")

    async def test_available_only_field(self) -> None:
        """Confirm available only filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "available_only": True}

        # API
        await self._test_api_results_count(params, 1, "available_only")

    @unittest.skipIf(
        tests_running_over_solr,
        "Skip in SOlR due to we stopped indexing parties",
    )
    async def test_party_name_filter(self) -> None:
        """Confirm party_name filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "party_name": "Defendant Jane Roe",
        }

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "party_name")

    @unittest.skipIf(
        tests_running_over_solr,
        "Skip in SOlR due to we stopped indexing parties",
    )
    async def test_atty_name_filter(self) -> None:
        """Confirm atty_name filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "atty_name": "Debbie Russell"}

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 2, "atty_name")

    async def test_combine_filters(self) -> None:
        """Confirm that combining filters works properly"""
        # Get results for a broad filter
        params = {"type": SEARCH_TYPES.RECAP, "case_name": "SUBPOENAS SERVED"}

        # API, 3 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 3, "case_name")

        # Constraint results by adding document number filter.
        params["docket_number"] = "12-1235"
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
        # API
        await self._test_api_results_count(params, 6, "docket_number")

        # Constraint filter:
        params = {
            "type": SEARCH_TYPES.RECAP,
            "docket_number": "1:21-bk-1234",
            "available_only": True,
        }
        # API
        await self._test_api_results_count(
            params, 4, "docket_number + available_only"
        )

    @unittest.skipIf(
        tests_running_over_solr,
        "Skip in SOlR due to we stopped indexing parties",
    )
    async def test_advanced_queries(self) -> None:
        """Confirm advance queries works properly"""
        # Advanced query string, firm
        params = {"type": SEARCH_TYPES.RECAP, "q": "firm:(Associates LLP)"}

        # API
        await self._test_api_results_count(params, 2, "advance firm")

        # Advanced query string, firm AND short_description
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": 'firm:(Associates LLP) AND short_description:"Document attachment"',
        }
        # API
        await self._test_api_results_count(
            params, 1, "advance firm AND short_description"
        )

        # Advanced query string, page_count OR document_type
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "page_count:5 OR document_type:Attachment",
        }
        # API
        await self._test_api_results_count(
            params, 2, "page_count OR document_type"
        )

        # Advanced query string, entry_date_filed NOT document_type
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "entry_date_filed:[2015-08-18T00:00:00Z TO 2015-08-20T00:00:00Z] NOT document_type:Attachment",
        }
        # API
        await self._test_api_results_count(
            params, 1, "page_count OR document_type"
        )

        # Advanced query string, "SUBPOENAS SERVED" NOT "OFF"
        params = {"type": SEARCH_TYPES.RECAP, "q": "SUBPOENAS SERVED NOT OFF"}

        # API
        await self._test_api_results_count(
            params, 2, '"SUBPOENAS SERVED" NOT "OFF"'
        )

    async def test_text_queries(self) -> None:
        """Confirm text queries works properly"""
        # Text query case name.
        params = {"type": SEARCH_TYPES.RECAP, "q": "SUBPOENAS SERVED OFF"}
        # API
        await self._test_api_results_count(params, 1, "text query case name")

        # Text query description.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Amicus Curiae Lorem"}

        # API
        await self._test_api_results_count(params, 2, "text query description")

        # Text query text.
        params = {"type": SEARCH_TYPES.RECAP, "q": "PACER Document Franklin"}

        # API
        await self._test_api_results_count(params, 1, "text query text")

        # Text query text judge.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Thalassa Miller"}

        # API
        await self._test_api_results_count(params, 2, "text query judge")

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
        # API
        await self._test_api_results_count(params, 3, "order random")

        # Order by score desc (relevance).
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "score desc",
        }
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
        # API
        r = await self._test_api_results_count(params, 3, "order")
        self.assertTrue(
            r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234"),
            msg="'12-1235' should come BEFORE '1:21-bk-1234' when order_by asc.",
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


class RECAPFeedTest(RECAPSearchTestCase, ESIndexTestCase, TestCase):
    """Tests for RECAP Search Feed"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.rebuild_index("search.Docket")
        super().setUpTestData()
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    def test_do_recap_search_feed_have_content(self) -> None:
        """Can we make a RECAP Search Feed?"""
        with self.captureOnCommitCallbacks(execute=True):
            # Docket entry without date_filed it should be excluded from feed.
            de_1 = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court,
                    case_name="Lorem Ipsum",
                    case_name_full="Jackson & Sons Holdings vs. Bank",
                    date_filed=None,
                    date_argued=datetime.date(2013, 5, 20),
                    docket_number="1:21-bk-1234",
                    assigned_to=self.judge,
                    referred_to=self.judge_2,
                    nature_of_suit="440",
                ),
                date_filed=None,
                description="MOTION for Leave to File Amicus Curiae Lorem",
            )
            RECAPDocumentFactory(
                docket_entry=de_1,
                description="Leave to File",
                document_number="1",
                is_available=True,
                page_count=5,
            )

        # Text query case.
        params = {
            "q": "Leave to File",
            "type": SEARCH_TYPES.RECAP,
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
            ("//atom:entry", 3),
            ("//atom:entry/atom:title", 3),
            ("//atom:entry/atom:link", 3),
            ("//atom:entry/atom:published", 3),
            ("//atom:entry/atom:author/atom:name", 3),
            ("//atom:entry/atom:id", 3),
            ("//atom:entry/atom:summary", 3),
        )
        for test, count in node_tests:
            node_count = len(xml_tree.xpath(test, namespaces=namespaces))  # type: ignore
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (count, test, node_count),
            )

        # Confirm items are ordered by entry_date_filed desc
        published_format = "%Y-%m-%dT%H:%M:%S%z"
        first_item_published_str = str(
            xml_tree.xpath(
                "//atom:entry[2]/atom:published", namespaces=namespaces
            )[0].text
            # type: ignore
        )
        second_item_published_str = str(
            xml_tree.xpath(
                "//atom:entry[3]/atom:published", namespaces=namespaces
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
            "court": self.court.pk,
            "type": SEARCH_TYPES.RECAP,
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

        # Match all case.
        params = {
            "type": SEARCH_TYPES.RECAP,
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


class IndexDocketRECAPDocumentsCommandTest(
    ESIndexTestCase, TransactionTestCase
):
    """cl_index_parent_and_child_docs command tests for Elasticsearch"""

    def setUp(self):
        self.rebuild_index("search.Docket")
        self.court = CourtFactory(id="canb", jurisdiction="FB")
        self.de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                date_filed=datetime.date(2015, 8, 16),
                docket_number="1:21-bk-1234",
                nature_of_suit="440",
            ),
            entry_number=1,
            date_filed=datetime.date(2015, 8, 19),
        )
        self.rd = RECAPDocumentFactory(
            docket_entry=self.de,
            document_number="1",
        )
        self.rd_att = RECAPDocumentFactory(
            docket_entry=self.de,
            document_number="1",
            attachment_number=2,
        )
        self.de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                date_filed=datetime.date(2016, 8, 16),
                date_argued=datetime.date(2012, 6, 23),
            ),
            entry_number=None,
            date_filed=datetime.date(2014, 7, 19),
        )
        self.rd_2 = RECAPDocumentFactory(
            docket_entry=self.de_1,
            document_number="",
        )
        self.delete_index("search.Docket")
        self.create_index("search.Docket")

        self.r = make_redis_interface("CACHE")
        keys = self.r.keys(compose_redis_key(SEARCH_TYPES.RECAP))
        if keys:
            self.r.delete(*keys)

    def test_cl_index_parent_and_child_docs_command(self):
        """Confirm the command can properly index Dockets and their
        RECAPDocuments into the ES."""

        s = DocketDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)
        # Call cl_index_parent_and_child_docs command.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
        )

        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2, msg="Wrong number of Dockets returned.")

        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="recap_document"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of RECAPDocuments returned."
        )

        # RECAPDocuments are indexed.
        rds_pks = [
            self.rd.pk,
            self.rd_att.pk,
            self.rd_2.pk,
        ]
        for rd_pk in rds_pks:
            self.assertTrue(
                ESRECAPDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP)
            )

        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de.docket.pk)
        self.assertEqual(
            s.count(), 2, msg="Wrong number of RECAPDocuments returned."
        )

        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de_1.docket.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of RECAPDocuments returned."
        )

    def test_log_and_get_last_document_id(self):
        """Can we log and get the last docket indexed to/from redis?"""

        last_values = log_last_document_indexed(
            1001, compose_redis_key(SEARCH_TYPES.RECAP)
        )
        self.assertEqual(last_values["last_document_id"], 1001)

        last_values = log_last_document_indexed(
            2001, compose_redis_key(SEARCH_TYPES.RECAP)
        )
        self.assertEqual(last_values["last_document_id"], 2001)

        last_document_id = get_last_parent_document_id_processed(
            SEARCH_TYPES.RECAP
        )
        self.assertEqual(last_document_id, 2001)

        keys = self.r.keys(compose_redis_key(SEARCH_TYPES.RECAP))
        if keys:
            self.r.delete(*keys)

    def test_index_dockets_in_bulk_task(self):
        """Confirm the command can properly index dockets in bulk from the
        ready_mix_cases_project command.
        """

        court = CourtFactory(id="canb", jurisdiction="FB")
        d_1 = DocketFactory(
            court=court,
            date_filed=datetime.date(2019, 8, 16),
        )
        BankruptcyInformationFactory(docket=d_1, chapter="7")

        d_2 = DocketFactory(
            court=court,
            date_filed=datetime.date(2020, 8, 16),
        )
        BankruptcyInformationFactory(docket=d_2, chapter="7")

        d_3 = DocketFactory(
            court=court,
            date_filed=datetime.date(2021, 8, 16),
        )
        BankruptcyInformationFactory(docket=d_3, chapter="7")

        d_4 = DocketFactory(
            court=court,
            date_filed=datetime.date(2021, 8, 16),
        )
        BankruptcyInformationFactory(docket=d_4, chapter="13")

        self.delete_index("search.Docket")
        self.create_index("search.Docket")

        s = DocketDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)
        # Call cl_index_parent_and_child_docs command.
        call_command(
            "ready_mix_cases_project",
            task="re-index-dockets",
            queue="celery",
        )

        s = DocketDocument.search().query("match_all")
        self.assertEqual(s.count(), 3)

        d_1.delete()
        d_2.delete()
        d_3.delete()
        d_4.delete()

    def test_cl_index_only_parent_or_child_documents_command(self):
        """Confirm the command can properly index only RECAPDocuments or only
        Dockets into ES."""

        s = DocketDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)
        # Call cl_index_parent_and_child_docs command for dockets.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            document_type="parent",
        )

        # Two dockets should be indexed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2, msg="Wrong number of Dockets returned.")

        # No RECAPDocuments should be indexed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="recap_document"))
        self.assertEqual(
            s.count(), 0, msg="Wrong number of RECAPDocuments returned."
        )

        # Now index only RECAPDocuments.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            document_type="child",
        )
        s = DocketDocument.search()
        # 3 RECAPDocuments should be indexed.
        s = s.query(Q("match", docket_child="recap_document"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of RECAPDocuments returned."
        )

        # RECAPDocuments are indexed.
        rds_pks = [
            self.rd.pk,
            self.rd_att.pk,
            self.rd_2.pk,
        ]
        for rd_pk in rds_pks:
            self.assertTrue(
                ESRECAPDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP)
            )

        # Confirm parent-child relation.
        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de.docket.pk)
        self.assertEqual(
            s.count(), 2, msg="Wrong number of RECAPDocuments returned."
        )
        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de_1.docket.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of RECAPDocuments returned."
        )

    def test_index_missing_parent_docs_when_indexing_only_child_docs(self):
        """Confirm the command can properly index missing dockets when indexing
        only RECAPDocuments.
        """

        s = DocketDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)
        # Call cl_index_parent_and_child_docs command for RECAPDocuments.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            document_type="child",
        )

        # Dockets and the RECAPDocuments should be indexed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2, msg="Wrong number of Dockets returned.")

        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="recap_document"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of RECAPDocuments returned."
        )

        # RECAPDocuments are indexed.
        rds_pks = [
            self.rd.pk,
            self.rd_att.pk,
            self.rd_2.pk,
        ]
        for rd_pk in rds_pks:
            self.assertTrue(
                ESRECAPDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP)
            )

        # Confirm parent-child relation.
        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de.docket.pk)
        self.assertEqual(
            s.count(), 2, msg="Wrong number of RECAPDocuments returned."
        )
        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de_1.docket.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of RECAPDocuments returned."
        )


class RECAPIndexingTest(
    CountESTasksTestCase, ESIndexTestCase, TransactionTestCase
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")

    def setUp(self):
        self.court = CourtFactory(id="canb", jurisdiction="FB")
        super().setUp()

    def _compare_response_child_value(
        self,
        response,
        parent_index,
        child_index,
        expected_value,
        field_name,
    ):
        self.assertEqual(
            expected_value,
            response["hits"]["hits"][parent_index]["inner_hits"][
                "filter_query_inner_recap_document"
            ]["hits"]["hits"][child_index]["_source"][field_name],
            msg=f"Did not get the right {field_name} value.",
        )

    def _test_main_es_query(self, cd, parent_expected, field_name):
        search_query = DocketDocument.search()
        (
            s,
            total_query_results,
            top_hits_limit,
            total_child_results,
        ) = build_es_main_query(search_query, cd)
        self.assertEqual(
            total_query_results,
            parent_expected,
            msg="Did not get the right number of parent documents %s\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            % (field_name, parent_expected, total_query_results),
        )

        return s.execute().to_dict()

    def test_minute_entry_indexing(self) -> None:
        """Confirm a minute entry can be properly indexed."""

        de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
            ),
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem",
            entry_number=None,
        )
        rd_1 = RECAPDocumentFactory(
            docket_entry=de_1,
            description="Leave to File",
            document_number="",
            is_available=True,
            page_count=5,
        )

        self.assertTrue(DocketDocument.exists(id=ES_CHILD_ID(rd_1.pk).RECAP))
        de_1.docket.delete()

    def test_unnumbered_entry_indexing(self) -> None:
        """Confirm an unnumbered entry which uses the pacer_doc_id as number
        can be properly indexed."""

        de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
            ),
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem",
            entry_number=3010113237867,
        )
        rd_1 = RECAPDocumentFactory(
            docket_entry=de_1,
            description="Leave to File",
            document_number="3010113237867",
            is_available=True,
            page_count=5,
        )

        self.assertTrue(DocketDocument.exists(id=ES_CHILD_ID(rd_1.pk).RECAP))
        de_1.docket.delete()

    def test_index_recap_parent_and_child_objects(self) -> None:
        """Confirm Dockets and RECAPDocuments are properly indexed in ES"""
        docket_entry_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED ON",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:21-bk-1234",
                nature_of_suit="440",
            ),
            entry_number=1,
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem",
        )

        rd = RECAPDocumentFactory(
            docket_entry=docket_entry_1,
            description="Leave to File",
            document_number="1",
            is_available=True,
            page_count=5,
            pacer_doc_id="018036652435",
        )

        rd_att = RECAPDocumentFactory(
            docket_entry=docket_entry_1,
            description="Document attachment",
            document_type=RECAPDocument.ATTACHMENT,
            document_number="1",
            attachment_number=2,
            is_available=False,
            page_count=7,
            pacer_doc_id="018036652436",
        )

        docket_entry_2 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                docket_number="12-1235",
                court=self.court,
                case_name="SUBPOENAS SERVED OFF",
                case_name_full="The State of Franklin v. Solutions LLC",
                date_filed=datetime.date(2016, 8, 16),
                date_argued=datetime.date(2012, 6, 23),
            ),
            entry_number=3,
            date_filed=datetime.date(2014, 7, 19),
            description="MOTION for Leave to File Amicus Discharging Debtor",
        )
        rd_2 = RECAPDocumentFactory(
            docket_entry=docket_entry_2,
            description="Leave to File",
            document_number="3",
            page_count=10,
            plain_text="Mauris iaculis, leo sit amet hendrerit vehicula, Maecenas nunc justo. Integer varius sapien arcu, quis laoreet lacus consequat vel.",
            pacer_doc_id="016156723121",
        )

        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2)

        # RECAPDocuments are indexed.
        rd_pks = [
            rd.pk,
            rd_att.pk,
            rd_2.pk,
        ]
        for rd_pk in rd_pks:
            self.assertTrue(DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP))

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
                assigned_to=None,
                referred_to=None,
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
        firm = AttorneyOrganizationFactory(
            lookup_key="280kingofprussiaroadradnorkesslertopazmeltzercheck19087",
            name="Law Firm LLP",
        )
        attorney = AttorneyFactory(
            name="Emily Green",
            organizations=[firm],
            docket=de_1.docket,
        )
        party_type = PartyTypeFactory.create(
            party=PartyFactory(
                name="Mary Williams Corp.",
                docket=de_1.docket,
                attorneys=[attorney],
            ),
            docket=de_1.docket,
        )

        docket_pk = de_1.docket.pk
        rd_pk = rd_1.pk
        self.assertTrue(DocketDocument.exists(id=docket_pk))

        self.assertTrue(DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP))

        # Confirm parties fields are indexed into DocketDocument.
        # Index docket parties using index_docket_parties_in_es task.
        index_docket_parties_in_es.delay(de_1.docket.pk)

        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertIn(party_type.party.pk, docket_doc.party_id)
        self.assertIn(party_type.party.name, docket_doc.party)
        self.assertIn(attorney.pk, docket_doc.attorney_id)
        self.assertIn(attorney.name, docket_doc.attorney)
        self.assertIn(firm.pk, docket_doc.firm_id)
        self.assertIn(firm.name, docket_doc.firm)
        self.assertEqual(None, docket_doc.assignedTo)
        self.assertEqual(None, docket_doc.referredTo)
        self.assertEqual(None, docket_doc.assigned_to_id)
        self.assertEqual(None, docket_doc.referred_to_id)

        # Confirm assigned_to and referred_to are properly updated in Docket.
        judge = PersonFactory.create(name_first="Thalassa", name_last="Miller")
        judge_2 = PersonFactory.create(
            name_first="Persephone", name_last="Sinclair"
        )

        # Update docket field:
        de_1.docket.case_name = "USA vs Bank"
        de_1.docket.assigned_to = judge
        de_1.docket.referred_to = judge_2

        de_1.docket.docket_number = "21-0000"
        de_1.docket.nature_of_suit = "Test nature of suit"
        de_1.docket.cause = "Test Cause"
        de_1.docket.jury_demand = "50,000"
        de_1.docket.jurisdiction_type = "U.S. Government Defendant"
        de_1.docket.date_argued = datetime.date(2021, 8, 19)
        de_1.docket.date_filed = datetime.date(2022, 8, 19)
        de_1.docket.date_terminated = datetime.date(2023, 8, 19)

        de_1.docket.save()

        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertIn(de_1.docket.case_name, docket_doc.caseName)
        self.assertEqual(de_1.docket.docket_number, docket_doc.docketNumber)
        self.assertEqual(de_1.docket.nature_of_suit, docket_doc.suitNature)
        self.assertEqual(de_1.docket.cause, docket_doc.cause)
        self.assertEqual(de_1.docket.jury_demand, docket_doc.juryDemand)
        self.assertEqual(
            de_1.docket.jurisdiction_type, docket_doc.jurisdictionType
        )
        self.assertEqual(de_1.docket.date_argued, docket_doc.dateArgued.date())
        self.assertEqual(de_1.docket.date_filed, docket_doc.dateFiled.date())
        self.assertEqual(
            de_1.docket.date_terminated, docket_doc.dateTerminated.date()
        )
        self.assertIn(judge.name_full, docket_doc.assignedTo)
        self.assertIn(judge_2.name_full, docket_doc.referredTo)
        self.assertEqual(judge.pk, docket_doc.assigned_to_id)
        self.assertEqual(judge_2.pk, docket_doc.referred_to_id)

        # Confirm docket best case name and slug.
        de_1.docket.case_name = ""
        de_1.docket.case_name_full = ""
        de_1.docket.case_name_short = "USA vs Bank Short"
        de_1.docket.save()
        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertEqual(de_1.docket.case_name_short, docket_doc.caseName)

        de_1.docket.case_name = ""
        de_1.docket.case_name_full = "USA vs Bank Full"
        de_1.docket.save()
        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertEqual(de_1.docket.case_name_full, docket_doc.caseName)
        self.assertEqual(de_1.docket.case_name_full, docket_doc.case_name_full)
        self.assertEqual("usa-vs-bank-full", docket_doc.docket_slug)
        self.assertEqual(
            de_1.docket.get_absolute_url(), docket_doc.docket_absolute_url
        )

        # Update judges name.
        judge.name_first = "William"
        judge.name_last = "Anderson"
        judge.save()

        judge_2.name_first = "Emily"
        judge_2.name_last = "Clark"
        judge_2.save()

        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertIn(judge.name_full, docket_doc.assignedTo)
        self.assertIn(judge_2.name_full, docket_doc.referredTo)

        # Update docket entry field:
        de_1.description = "Notification to File Ipsum"
        de_1.entry_number = 99
        de_1.save()

        rd_doc = DocketDocument.get(id=ES_CHILD_ID(rd_pk).RECAP)
        self.assertEqual("Notification to File Ipsum", rd_doc.description)
        self.assertEqual(99, rd_doc.entry_number)

        # Update RECAPDocument fields.
        f = SimpleUploadedFile("recap_filename", b"file content more content")
        rd_1.description = "RD short description"
        rd_1.document_type = RECAPDocument.ATTACHMENT
        rd_1.document_number = "5"
        rd_1.pacer_doc_id = "103005"
        rd_1.plain_text = "Plain text testing"
        rd_1.attachment_number = "1"
        rd_1.is_available = True
        rd_1.page_count = 5
        rd_1.filepath_local = f
        rd_1.save()
        rd_doc = DocketDocument.get(id=ES_CHILD_ID(rd_pk).RECAP)
        self.assertEqual(rd_1.description, rd_doc.short_description)
        self.assertEqual(
            rd_1.get_document_type_display(), rd_doc.document_type
        )
        self.assertEqual(rd_1.document_number, rd_doc.document_number)
        self.assertEqual(rd_1.pacer_doc_id, rd_doc.pacer_doc_id)
        self.assertEqual(rd_1.plain_text, rd_doc.plain_text)
        self.assertEqual(rd_1.attachment_number, str(rd_doc.attachment_number))
        self.assertEqual(rd_1.is_available, rd_doc.is_available)
        self.assertEqual(rd_1.page_count, rd_doc.page_count)
        self.assertEqual(rd_1.filepath_local, rd_doc.filepath_local)
        self.assertEqual(rd_1.get_absolute_url(), rd_doc.absolute_url)

        # Confirm Docket fields are updated in RDDocument:
        self.assertIn(de_1.docket.case_name, rd_doc.caseName)
        self.assertEqual(de_1.docket.docket_number, rd_doc.docketNumber)
        self.assertEqual(de_1.docket.nature_of_suit, rd_doc.suitNature)
        self.assertEqual(de_1.docket.cause, rd_doc.cause)
        self.assertEqual(de_1.docket.jury_demand, rd_doc.juryDemand)
        self.assertEqual(
            de_1.docket.jurisdiction_type, rd_doc.jurisdictionType
        )
        self.assertEqual(de_1.docket.date_argued, rd_doc.dateArgued.date())
        self.assertEqual(de_1.docket.date_filed, rd_doc.dateFiled.date())
        self.assertEqual(
            de_1.docket.date_terminated, rd_doc.dateTerminated.date()
        )
        self.assertIn(judge.name_full, rd_doc.assignedTo)
        self.assertIn(judge_2.name_full, rd_doc.referredTo)
        self.assertEqual(judge.pk, rd_doc.assigned_to_id)
        self.assertEqual(judge_2.pk, rd_doc.referred_to_id)

        # Update docket entry ID.
        de_2 = DocketEntryWithParentsFactory(
            docket=de_1.docket,
            description="Notification docket entry 2",
        )
        rd_1.docket_entry = de_2
        rd_1.save()
        rd_doc = DocketDocument.get(id=ES_CHILD_ID(rd_pk).RECAP)
        self.assertEqual(de_2.description, rd_doc.description)

        # Add a Bankruptcy document.
        bank = BankruptcyInformationFactory(docket=de_1.docket)
        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertEqual(str(bank.chapter), docket_doc.chapter)
        self.assertEqual(str(bank.trustee_str), docket_doc.trustee_str)

        # Update Bankruptcy document.
        bank.chapter = "98"
        bank.trustee_str = "Victoria, Sherline"
        bank.save()

        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertEqual("98", docket_doc.chapter)
        self.assertEqual("Victoria, Sherline", docket_doc.trustee_str)

        # Remove Bankruptcy document and confirm it gets removed from Docket.
        bank.delete()
        docket_doc = DocketDocument.get(id=docket_pk)
        self.assertEqual(None, docket_doc.chapter)
        self.assertEqual(None, docket_doc.trustee_str)

        # Add another RD:
        rd_2 = RECAPDocumentFactory(
            docket_entry=de_1,
            description="Notification to File",
            document_number="2",
            is_available=True,
            page_count=2,
        )

        rd_2_pk = rd_2.pk
        self.assertTrue(DocketDocument.exists(id=ES_CHILD_ID(rd_2_pk).RECAP))
        rd_2.delete()
        self.assertFalse(DocketDocument.exists(id=ES_CHILD_ID(rd_2_pk).RECAP))

        self.assertTrue(DocketDocument.exists(id=docket_pk))
        self.assertTrue(DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP))

        de_1.docket.delete()
        self.assertFalse(DocketDocument.exists(id=docket_pk))
        self.assertFalse(DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP))

    def test_update_docket_fields_in_recap_documents(self) -> None:
        """Confirm all the docket fields in RECAPDocuments that belong to a
        case are updated in bulk when the docket changes.
        """

        judge = PersonFactory.create(name_first="Thalassa", name_last="Miller")
        judge_2 = PersonFactory.create(
            name_first="Persephone", name_last="Sinclair"
        )
        de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                case_name="USA vs Bank Lorem",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:21-bk-1234",
                assigned_to=judge,
                nature_of_suit="440",
            ),
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem",
        )

        # Create two RECAPDocuments within the same case.
        rd_created_pks = []
        for i in range(2):
            rd = RECAPDocumentFactory(
                docket_entry=de,
                description=f"Leave to File {i}",
                document_number=f"{i}",
                is_available=True,
                page_count=5,
            )
            rd_created_pks.append(rd.pk)

        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "USA vs Bank Lorem",
        }

        # Query the parent docket and confirm is indexed with the right content
        response = self._test_main_es_query(params, 1, "q")
        for i in range(2):
            self._compare_response_child_value(
                response, 0, i, judge.name_full, "assignedTo"
            )
            self._compare_response_child_value(response, 0, i, None, "chapter")
            self._compare_response_child_value(
                response, 0, i, None, "trustee_str"
            )

        # Add BankruptcyInformation and confirm is indexed with the right content
        bank_data = BankruptcyInformationFactory(docket=de.docket)

        response = self._test_main_es_query(params, 1, "q")
        for i in range(2):
            self._compare_response_child_value(
                response, 0, i, bank_data.chapter, "chapter"
            )
            self._compare_response_child_value(
                response, 0, i, bank_data.trustee_str, "trustee_str"
            )

        # Update some docket fields.
        de.docket.case_name = "America vs Doe Enterprise"
        de.docket.docket_number = "21-45632"
        de.docket.case_name_full = "Teachers Union v. Board of Education"
        de.docket.nature_of_suit = "500"
        de.docket.cause = "Civil Rights Act"
        de.docket.jury_demand = "1300"
        de.docket.jurisdiction_type = "U.S. Government Lorem"
        de.docket.date_filed = datetime.date(2020, 4, 19)
        de.docket.date_argued = datetime.date(2020, 4, 18)
        de.docket.date_terminated = datetime.date(2022, 6, 10)
        de.docket.assigned_to = judge_2
        de.docket.referred_to = judge
        de.docket.save()

        # Query the parent docket by its updated name.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "America vs Doe Enterprise",
        }
        response = self._test_main_es_query(params, 1, "q")

        # Confirm all docket fields in the RDs were updated.
        for i in range(2):
            self._compare_response_child_value(
                response, 0, i, "America vs Doe Enterprise", "caseName"
            )
            self._compare_response_child_value(
                response, 0, i, "21-45632", "docketNumber"
            )

            self._compare_response_child_value(
                response,
                0,
                i,
                "Teachers Union v. Board of Education",
                "case_name_full",
            )

            self._compare_response_child_value(
                response, 0, i, "500", "suitNature"
            )

            self._compare_response_child_value(
                response, 0, i, "Civil Rights Act", "cause"
            )
            self._compare_response_child_value(
                response, 0, i, "1300", "juryDemand"
            )
            self._compare_response_child_value(
                response, 0, i, "U.S. Government Lorem", "jurisdictionType"
            )
            self._compare_response_child_value(
                response,
                0,
                i,
                de.docket.date_argued.strftime("%Y-%m-%d"),
                "dateArgued",
            )
            self._compare_response_child_value(
                response,
                0,
                i,
                de.docket.date_filed.strftime("%Y-%m-%d"),
                "dateFiled",
            )
            self._compare_response_child_value(
                response,
                0,
                i,
                de.docket.date_terminated.strftime("%Y-%m-%d"),
                "dateTerminated",
            )

            self._compare_response_child_value(
                response, 0, i, de.docket.referred_to.name_full, "referredTo"
            )
            self._compare_response_child_value(
                response, 0, i, de.docket.assigned_to.name_full, "assignedTo"
            )
            self._compare_response_child_value(
                response, 0, i, de.docket.referred_to.pk, "referred_to_id"
            )
            self._compare_response_child_value(
                response, 0, i, de.docket.assigned_to.pk, "assigned_to_id"
            )
        # Update judge name.
        judge.name_first = "William"
        judge.name_last = "Anderson"
        judge.save()

        judge_2.name_first = "Emily"
        judge_2.name_last = "Clark"
        judge_2.save()

        response = self._test_main_es_query(params, 1, "q")
        # Confirm all docket fields in the RDs were updated.
        for i in range(2):
            self._compare_response_child_value(
                response, 0, i, judge.name_full, "referredTo"
            )
            self._compare_response_child_value(
                response, 0, i, judge_2.name_full, "assignedTo"
            )

        bank_data.chapter = "15"
        bank_data.trustee_str = "Jessica Taylor"
        bank_data.save()

        response = self._test_main_es_query(params, 1, "q")
        # Confirm all docket fields in the RDs were updated.
        for i in range(2):
            self._compare_response_child_value(response, 0, i, "15", "chapter")
            self._compare_response_child_value(
                response, 0, i, "Jessica Taylor", "trustee_str"
            )

        # Remove BankruptcyInformation and confirm it's removed from RDs.
        bank_data.delete()
        response = self._test_main_es_query(params, 1, "q")
        # Confirm all docket fields in the RDs were updated.
        for i in range(2):
            self._compare_response_child_value(response, 0, i, None, "chapter")
            self._compare_response_child_value(
                response, 0, i, None, "trustee_str"
            )

        # Also confirm the assigned_to_str and referred_to_str are being
        # tracked for changes in case assigned_to and referred_to are None.
        de.docket.assigned_to = None
        de.docket.referred_to = None
        de.docket.assigned_to_str = "Sarah Williams"
        de.docket.referred_to_str = "Laura Davis"
        de.docket.save()

        response = self._test_main_es_query(params, 1, "q")
        for i in range(2):
            self._compare_response_child_value(
                response, 0, i, "Laura Davis", "referredTo"
            )
            self._compare_response_child_value(
                response, 0, i, "Sarah Williams", "assignedTo"
            )
            self._compare_response_child_value(
                response, 0, i, None, "referred_to_id"
            )
            self._compare_response_child_value(
                response, 0, i, None, "assigned_to_id"
            )

        de.docket.delete()
        # After the docket is removed all the RECAPDocuments are also removed
        # from ES.
        for rd_pk in rd_created_pks:
            self.assertFalse(
                DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP)
            )

    def test_docket_indexing_and_tasks_count(self) -> None:
        """Confirm a Docket is properly indexed in ES with the right number of
        indexing tasks.
        """

        # Index docket on creation.
        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            docket = DocketFactory(
                court=self.court,
                pacer_case_id="asdf",
                docket_number="12-cv-02354",
                case_name="Vargas v. Wilkins",
            )

        # Only one es_save_document task should be called on creation.
        self.reset_and_assert_task_count(expected=1)
        self.assertTrue(DocketDocument.exists(id=docket.pk))

        # Restart task counter.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            docket_2 = DocketFactory(
                court=self.court,
                pacer_case_id="aaaaa",
                docket_number="12-cv-02358",
            )

        # No update_es_document task should be called on creation.
        self.reset_and_assert_task_count(expected=0)
        self.assertTrue(DocketDocument.exists(id=docket_2.pk))

        # Update a Docket without changes.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            docket.save()

        # update_es_document task shouldn't be called on save() without changes
        self.reset_and_assert_task_count(expected=0)

        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            docket.save()

        # es_save_document task shouldn't be called on save() without changes
        self.reset_and_assert_task_count(expected=0)

        # Update a Docket untracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            docket.blocked = True
            docket.save()
        # update_es_document task shouldn't be called on save() for untracked
        # fields
        self.reset_and_assert_task_count(expected=0)

        # Update a Docket tracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            docket.docket_number = "21-43434"
            docket.case_name = "Vargas v. Lorem"
            docket.save()

        # update_es_document task should be called 1 on tracked fields updates
        self.reset_and_assert_task_count(expected=1)
        d_doc = DocketDocument.get(id=docket.pk)
        self.assertEqual(d_doc.docketNumber, "21-43434")

        # Confirm a Docket is indexed if it doesn't exist in the
        # index on a tracked field update.
        self.delete_index("search.Docket")
        self.create_index("search.Docket")

        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            docket.docket_number = "21-43435"
            docket.save()

        # update_es_document task should be called 1 on tracked fields update
        self.reset_and_assert_task_count(expected=1)
        d_doc = DocketDocument.get(id=docket.pk)
        self.assertEqual(d_doc.docketNumber, "21-43435")
        self.assertEqual(d_doc.caseName, "Vargas v. Lorem")

        docket.delete()
        docket_2.delete()

    def test_recap_document_indexing_and_tasks_count(self) -> None:
        """Confirm a RECAPDocument is properly indexed in ES with the right
        number of indexing tasks.
        """
        docket = DocketFactory(
            court=self.court,
            pacer_case_id="asdf",
            docket_number="12-cv-02354",
            case_name="Vargas v. Wilkins",
        )

        # RECAP Document creation:
        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            de_1 = DocketEntryWithParentsFactory(
                docket=docket,
                date_filed=datetime.date(2015, 8, 19),
                description="MOTION for Leave to File Amicus Curiae Lorem",
                entry_number=None,
            )
            rd_1 = RECAPDocumentFactory(
                docket_entry=de_1,
                description="Leave to File",
                document_number="",
                is_available=True,
                page_count=5,
            )
        # Only 1 es_save_document task should be called on creation.
        self.reset_and_assert_task_count(expected=1)
        r_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertEqual(r_doc.docket_child["parent"], docket.pk)

        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            de_2 = DocketEntryWithParentsFactory(
                docket=docket,
            )
            RECAPDocumentFactory(
                docket_entry=de_2,
            )

        # No update_es_document task should be called on creation.
        self.reset_and_assert_task_count(expected=0)

        # Update a RECAPDocument without changes.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            rd_1.save()
        # update_es_document task shouldn't be called on save() without changes
        self.reset_and_assert_task_count(expected=0)

        # Update a RECAPDocument untracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            rd_1.is_sealed = True
            rd_1.save()
        # update_es_document task shouldn't be called on save() for untracked
        # fields
        self.reset_and_assert_task_count(expected=0)

        # Update a RECAPDocument tracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            rd_1.description = "Lorem Ipsum"
            rd_1.page_count = 5
            rd_1.save()

        # update_es_document task should be called 1 on tracked fields updates
        self.reset_and_assert_task_count(expected=1)
        r_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertEqual(r_doc.short_description, "Lorem Ipsum")
        self.assertEqual(r_doc.page_count, 5)

        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            rd_1.page_count = 6
            rd_1.save()

        # es_save_document task shouldn't be called on document updates.
        self.reset_and_assert_task_count(expected=0)

        # Create a new Docket and DocketEntry.
        docket_2 = DocketFactory(court=self.court, docket_number="21-0000")
        de_2 = DocketEntryWithParentsFactory(
            docket=docket_2,
            date_filed=datetime.date(2016, 8, 19),
            description="Notification for Lorem Ipsum",
            entry_number=2,
        )
        # Update the RECAPDocument docket_entry.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            rd_1.docket_entry = de_2
            rd_1.save()

        # update_es_document task should be called 1 on tracked fields updates
        self.reset_and_assert_task_count(expected=1)
        r_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertEqual(r_doc.description, de_2.description)
        self.assertEqual(r_doc.entry_number, de_2.entry_number)
        self.assertEqual(r_doc.docketNumber, docket_2.docket_number)

        # Confirm a RECAPDocument is indexed if it doesn't exist in the
        # index on a tracked field update.
        # Clean the RECAP index.
        self.delete_index("search.Docket")
        self.create_index("search.Docket")

        # Index Docket
        docket_2.docket_number = "21-43436"
        docket_2.save()

        self.assertFalse(DocketDocument.exists(id=ES_CHILD_ID(rd_1.pk).RECAP))
        # RECAP Document creation on update.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            rd_1.pacer_doc_id = "99999999"
            rd_1.save()

        # update_es_document task should be called 1 on tracked fields update
        self.reset_and_assert_task_count(expected=1)
        r_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertEqual(r_doc.pacer_doc_id, "99999999")
        self.assertEqual(r_doc.docket_child["parent"], docket_2.pk)

        # Add cites to RECAPDocument.
        opinion = OpinionWithParentsFactory()
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            OpinionsCitedByRECAPDocument.objects.bulk_create_with_signal(
                [
                    OpinionsCitedByRECAPDocument(
                        citing_document=rd_1,
                        cited_opinion=opinion,
                        depth=1,
                    )
                ]
            )

        # update_es_document task should be called 1 on tracked fields update
        self.reset_and_assert_task_count(expected=1)
        r_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertIn(opinion.pk, r_doc.cites)

        # Confirm OpinionsCitedByRECAPDocument delete doesn't trigger a update.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            OpinionsCitedByRECAPDocument.objects.filter(
                citing_document=rd_1.pk
            ).delete()

        self.reset_and_assert_task_count(expected=0)
        r_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertIn(opinion.pk, r_doc.cites)

        # Update cites to RECAPDocument.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            opinion = OpinionWithParentsFactory()
            opinion_2 = OpinionWithParentsFactory()
            o_cited = OpinionsCitedByRECAPDocument(
                citing_document=rd_1,
                cited_opinion=opinion,
                depth=1,
            )
            o_cited_2 = OpinionsCitedByRECAPDocument(
                citing_document=rd_1,
                cited_opinion=opinion_2,
                depth=1,
            )
            OpinionsCitedByRECAPDocument.objects.bulk_create_with_signal(
                [o_cited, o_cited_2]
            )

        self.reset_and_assert_task_count(expected=3)
        r_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertIn(opinion.pk, r_doc.cites)
        self.assertIn(opinion_2.pk, r_doc.cites)

        docket_2.delete()

    def test_search_pagination_results_limit(self) -> None:
        """Confirm that the last page in the pagination is properly computed
        based on the number of results returned by Elasticsearch.
        """
        d_created = []
        for i in range(21):
            d = DocketFactory(
                court=self.court,
            )
            d_created.append(d)

        # Test pagination requests.
        search_params = {
            "type": SEARCH_TYPES.RECAP,
        }

        # 100 results, 5 pages.
        with mock.patch(
            "cl.search.views.build_es_main_query",
            side_effect=lambda x, y: (
                DocketDocument.search().query("match_all"),
                100,
                5,
                1000,
            ),
        ):
            r = self.client.get(
                reverse("show_results"),
                search_params,
            )
        self.assertIn("100 Results", r.content.decode())
        self.assertIn("1 of 5", r.content.decode())

        # 101 results, 6 pages.
        with mock.patch(
            "cl.search.views.build_es_main_query",
            side_effect=lambda x, y: (
                DocketDocument.search().query("match_all"),
                101,
                5,
                1000,
            ),
        ):
            r = self.client.get(
                reverse("show_results"),
                search_params,
            )
        self.assertIn("101 Results", r.content.decode())
        self.assertIn("1 of 6", r.content.decode())

        # 20,000 results, 1,000 pages.
        with mock.patch(
            "cl.search.views.build_es_main_query",
            side_effect=lambda x, y: (
                DocketDocument.search().query("match_all"),
                20_000,
                5,
                1000,
            ),
        ):
            r = self.client.get(
                reverse("show_results"),
                search_params,
            )
        self.assertIn("20,000 Results", r.content.decode())
        self.assertIn("1 of 1,000", r.content.decode())

        for d in d_created:
            d.delete()
