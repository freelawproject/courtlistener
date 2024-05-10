import datetime
import math
import re
import unittest
from http import HTTPStatus
from unittest import mock

import time_machine
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import AsyncClient, override_settings
from django.urls import reverse
from django.utils.timezone import now
from elasticsearch_dsl import Q
from lxml import etree, html
from rest_framework.serializers import CharField

from cl.lib.elasticsearch_utils import (
    build_es_main_query,
    fetch_es_results,
    merge_unavailable_fields_on_parent_document,
    set_results_highlights,
)
from cl.lib.redis_utils import get_redis_interface
from cl.lib.test_helpers import (
    IndexedSolrTestCase,
    RECAPSearchTestCase,
    docket_v4_api_keys,
    rd_type_v4_api_keys,
    recap_document_v4_api_keys,
    skip_if_common_tests_skipped,
)
from cl.lib.view_utils import increment_view_count
from cl.people_db.factories import (
    AttorneyFactory,
    AttorneyOrganizationFactory,
    PartyFactory,
    PartyTypeFactory,
    PersonFactory,
)
from cl.search.api_serializers import (
    BaseRECAPDocumentESResultSerializer,
    DocketESResultSerializer,
    RECAPESResultSerializer,
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
    Docket,
    OpinionsCitedByRECAPDocument,
    RECAPDocument,
)
from cl.search.tasks import (
    add_docket_to_solr_by_rds,
    es_save_document,
    index_docket_parties_in_es,
    index_related_cites_fields,
    update_es_document,
)
from cl.search.types import EventTable
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

    def _assert_results_header_content(self, html_content, expected_text):
        h2_element = html.fromstring(html_content).xpath(
            '//h2[@id="result-count"]'
        )
        h2_content = html.tostring(
            h2_element[0], method="text", encoding="unicode"
        ).replace("\xa0", " ")
        self.assertIn(
            expected_text,
            h2_content.strip(),
            msg=f"'{expected_text}' was not found within the results header.",
        )

    def _test_main_es_query(self, cd, parent_expected, field_name):
        search_query = DocketDocument.search()
        (s, child_docs_count_query, *_) = build_es_main_query(search_query, cd)
        hits, _, _, total_query_results, child_total = fetch_es_results(
            cd,
            s,
            child_docs_count_query,
            1,
        )
        self.assertEqual(
            total_query_results,
            parent_expected,
            msg="Did not get the right number of parent documents %s\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            % (field_name, parent_expected, total_query_results),
        )
        return hits.to_dict()

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
                source=Docket.RECAP,
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

        params["description"] = (
            '"leave to file" AND "amicus" "Discharging Debtor"'
        )
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
        self.assertEqual(r.status_code, HTTPStatus.OK)
        r = await self.async_client.get(
            reverse("show_results"),
            {"type": SEARCH_TYPES.RECAP, "attachment_number": "1"},
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)

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
                source=Docket.RECAP,
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
                source=Docket.RECAP,
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
                source=Docket.RECAP,
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
                source=Docket.RECAP,
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
                source=Docket.RECAP,
            )
            BankruptcyInformationFactory(docket=docket, chapter="7")

            docket_2 = DocketFactory(
                court=self.court,
                case_name="Ready Mix Hampton",
                date_filed=datetime.date(2021, 8, 16),
                source=Docket.RECAP,
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
                case_name="America v. Lorem",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:17-cv-04465",
                nature_of_suit="440",
                source=Docket.RECAP,
            )
            e_1_d_1 = DocketEntryWithParentsFactory(
                docket=docket,
                entry_number=1,
                date_filed=datetime.date(2015, 8, 19),
                description="COMPLAINT against NYU Hospitals Center, Tisch Hospital",
            )
            firm = AttorneyOrganizationFactory(
                name="Lawyers LLP", lookup_key="6201in816"
            )
            attorney = AttorneyFactory(
                name="Harris Martin",
                organizations=[firm],
                docket=docket,
            )
            PartyTypeFactory.create(
                party=PartyFactory(
                    name="Bill Lorem",
                    docket=docket,
                    attorneys=[attorney],
                ),
                docket=docket,
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

            docket_2 = DocketFactory(
                case_name="America v. Lorem",
                court=self.court,
                docket_number="3:98-ms-148395",
                source=Docket.RECAP,
            )
            firm_2 = AttorneyOrganizationFactory(
                name="America LLP", lookup_key="4421in816"
            )
            attorney_2 = AttorneyFactory(
                name="Harris Martin",
                organizations=[firm_2],
                docket=docket_2,
            )
            PartyTypeFactory.create(
                party=PartyFactory(
                    name="Bill Lorem",
                    docket=docket_2,
                    attorneys=[attorney_2],
                ),
                docket=docket_2,
            )
            d3 = DocketEntryWithParentsFactory(
                docket=docket_2,
                entry_number=3,
                date_filed=datetime.date(2015, 8, 19),
                description="COMPLAINT against NYU Hospitals Center, Tisch Hospital",
            )
            RECAPDocumentFactory(
                docket_entry=d3,
                document_number="3",
                is_available=True,
                page_count=5,
                description="Ut lobortis urna at condimentum lacinia",
            )
            docket_3 = DocketFactory(
                case_name="America v. Lorem",
                court=self.court,
                docket_number="1:56-ms-1000",
                source=Docket.RECAP,
            )
            firm_3 = AttorneyOrganizationFactory(
                name="America LLP", lookup_key="4421in818"
            )
            attorney_3 = AttorneyFactory(
                name="Harris Martin",
                organizations=[firm_3],
                docket=docket_3,
            )
            PartyTypeFactory.create(
                party=PartyFactory(
                    name="Other Party",
                    docket=docket_3,
                    attorneys=[attorney_3],
                ),
                docket=docket_3,
            )
            d4 = DocketEntryWithParentsFactory(
                docket=docket_3,
                entry_number=4,
                date_filed=datetime.date(2015, 8, 19),
                description="COMPLAINT against Lorem",
            )
            RECAPDocumentFactory(
                docket_entry=d4,
                document_number="4",
                is_available=True,
                page_count=5,
                description="Ut lobortis urna at condimentum lacinia",
            )
            RECAPDocumentFactory(
                docket_entry=d4,
                document_number="5",
                is_available=False,
                page_count=5,
                description="Suspendisse bibendum eu",
            )

            empty_docket = DocketFactory(
                court=self.court,
                case_name="California v. America",
                date_filed=datetime.date(2010, 8, 16),
                docket_number="1:19-cv-04400",
                source=Docket.RECAP,
            )
            PartyTypeFactory.create(
                party=PartyFactory(
                    name="Bill Lorem",
                    docket=empty_docket,
                    attorneys=[attorney],
                ),
                docket=empty_docket,
            )

        ## The party filter does not match any documents for the given search criteria
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "hospital",
            "description": "center",
            "party_name": "Frank Paul Sabatini",
        }
        # 0 result expected. The party_name doesn't match any case.
        async_to_sync(self._test_article_count)(
            params, 0, "text query + description + party_name"
        )

        ## The party filter can constrain the results returned, along with a parent filter.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "court": "canb ca1",
            "party_name": "Defendant Jane Roe",
        }
        # 1 result expected. The party_name field match one case with two RDs.
        r = async_to_sync(self._test_article_count)(
            params, 1, "court + party_name"
        )
        self._count_child_documents(
            0, r.content.decode(), 2, "court + party_name"
        )
        self._assert_results_header_content(r.content.decode(), "1 Case")
        self._assert_results_header_content(
            r.content.decode(), "2 Docket Entries"
        )

        ## The party filter can constrain the results returned, along with
        # case_name filter.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": '"America"',
            "party_name": "Bill Lorem",
        }
        # 3 results expected. It matches 2 cases: one with 2 RDs and one with 1
        # and 1 empty docket.
        r = async_to_sync(self._test_article_count)(
            params, 3, "case_name + party_name"
        )
        self._count_child_documents(
            0, r.content.decode(), 2, "case_name + party_name"
        )
        self._count_child_documents(
            1, r.content.decode(), 1, "case_name + party_name"
        )
        self.assertIn("Document #1", r.content.decode())
        self.assertIn("Document #2", r.content.decode())
        self.assertIn("Document #3", r.content.decode())
        self.assertIn(docket.docket_number, r.content.decode())
        self.assertIn(docket_2.docket_number, r.content.decode())
        self.assertIn(empty_docket.docket_number, r.content.decode())
        self._assert_results_header_content(r.content.decode(), "3 Cases")
        self._assert_results_header_content(
            r.content.decode(), "3 Docket Entries"
        )

        ## The party filter can constrain the results returned, along with
        # parent and child filters. The empty docket is excluded from results.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "America",
            "party_name": "Bill Lorem",
            "available_only": True,
        }
        # 2 results expected. It matches 2 cases each with 1 RD
        r = async_to_sync(self._test_article_count)(
            params, 2, "case_name + party_name + available_only "
        )
        self._count_child_documents(
            0, r.content.decode(), 1, "case_name + party_name +available_only"
        )
        self._count_child_documents(
            1, r.content.decode(), 1, "case_name + party_name +available_only"
        )
        self.assertIn("Document #1", r.content.decode())
        self.assertIn("Document #3", r.content.decode())
        self.assertIn(docket.docket_number, r.content.decode())
        self.assertIn(docket_2.docket_number, r.content.decode())
        self._assert_results_header_content(r.content.decode(), "2 Cases")
        self._assert_results_header_content(
            r.content.decode(), "2 Docket Entries"
        )

        ## The party filter can constrain the results returned, along with
        # query string and child filters.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "against",
            "description": "COMPLAINT",
            "available_only": True,
            "party_name": "Other Party",
        }
        # 1 result expected. It matches 1 case with one RD.
        r = async_to_sync(self._test_article_count)(
            params, 1, "text query + description + party_name"
        )
        self._count_child_documents(
            0, r.content.decode(), 1, "text query + description + party_name"
        )
        self.assertIn("Document #4", r.content.decode())
        self._assert_results_header_content(r.content.decode(), "1 Case")
        self._assert_results_header_content(
            r.content.decode(), "1 Docket Entry"
        )

        ## The attorney filter can constrain the results returned, along with
        # child filters.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "party_name": "Bill Lorem",
            "document_number": 3,
        }
        # 1 result expected. It matches only one RD.
        r = async_to_sync(self._test_article_count)(
            params, 1, "case_name + description + atty_name + document_number"
        )
        self._count_child_documents(
            0,
            r.content.decode(),
            1,
            "case_name + description + atty_name + document_number",
        )
        self.assertIn("Document #3", r.content.decode())
        self._assert_results_header_content(r.content.decode(), "1 Case")
        self._assert_results_header_content(
            r.content.decode(), "1 Docket Entry"
        )

        ## The party_name and attorney filter can constrain the results
        # returned, along with parent and child filters.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": '"America v. Lorem"',
            "description": "COMPLAINT against",
            "party_name": "Bill Lorem",
            "atty_name": "Harris Martin",
        }
        # 2 results expected. Each of them with one RD.
        r = async_to_sync(self._test_article_count)(
            params, 2, "case_name + description + party_name + atty_name"
        )
        self._count_child_documents(
            0,
            r.content.decode(),
            1,
            "case_name + description + party_name + atty_name",
        )
        self._count_child_documents(
            1,
            r.content.decode(),
            1,
            "case_name + description + party_name + atty_name",
        )
        self.assertIn("Document #1", r.content.decode())
        self.assertIn("Document #3", r.content.decode())
        self._assert_results_header_content(r.content.decode(), "2 Cases")
        self._assert_results_header_content(
            r.content.decode(), "2 Docket Entries"
        )

        ## The party_name and attorney filter can constrain the results
        # returned, along with string query.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "America",
            "party_name": "Bill Lorem",
            "atty_name": "Harris Martin",
        }
        # It matches 3 cases: one with 2 RDs and one with 1 and an empty docket
        r = async_to_sync(self._test_article_count)(
            params, 3, "text query + party_name + attorney"
        )
        self._count_child_documents(
            0, r.content.decode(), 2, "text query + party_name + attorney"
        )
        self._count_child_documents(
            1, r.content.decode(), 1, "text query + party_name + attorney"
        )
        self.assertIn("Document #1", r.content.decode())
        self.assertIn("Document #2", r.content.decode())
        self.assertIn("Document #3", r.content.decode())
        self.assertIn(docket.docket_number, r.content.decode())
        self.assertIn(docket_2.docket_number, r.content.decode())
        self.assertIn(empty_docket.docket_number, r.content.decode())
        self._assert_results_header_content(r.content.decode(), "3 Cases")
        self._assert_results_header_content(
            r.content.decode(), "3 Docket Entries"
        )

        ## To search for a docket without filings by parties, it is possible to
        # use the Advanced Search syntax and combine docket-level fields.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "party:(Bill Lorem) AND attorney:(Harris Martin)",
            "case_name": "California",
        }
        # It matches 1 case without filings.
        r = async_to_sync(self._test_article_count)(
            params, 1, "text query + case_name"
        )
        self.assertIn(empty_docket.docket_number, r.content.decode())

        ## The attorney filter can constrain the results returned at document
        # level, along with string query, parent and child filters.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "Ut lobortis urna",
            "case_name": '"America v. Lorem"',
            "description": "COMPLAINT against",
            "party_name": "Other Party",
        }
        # It matches 1 cases with one RD.
        r = async_to_sync(self._test_article_count)(
            params, 1, "text query + case_name + description + party_name"
        )
        self._count_child_documents(
            0,
            r.content.decode(),
            1,
            "text query + case_name + description + party_name",
        )
        self.assertIn("Document #4", r.content.decode())
        self._assert_results_header_content(r.content.decode(), "1 Case")
        self._assert_results_header_content(
            r.content.decode(), "1 Docket Entry"
        )

        ## Only filter by party and attorney. It returns the cases that match
        # the filters and all their RDs (max 5 per case).
        params = {
            "type": SEARCH_TYPES.RECAP,
            "party_name": "Bill Lorem",
            "atty_name": "Harris Martin",
        }
        # It matches 3 cases. One with 2 RDs, one with 1 and one without RDs
        r = async_to_sync(self._test_article_count)(
            params, 3, "party_name + attorney"
        )
        self._count_child_documents(
            0, r.content.decode(), 2, "party_name + attorney"
        )
        self._count_child_documents(
            1, r.content.decode(), 1, "party_name + attorney"
        )
        self.assertIn("Document #1", r.content.decode())
        self.assertIn("Document #2", r.content.decode())
        self.assertIn("Document #3", r.content.decode())

        self.assertIn(docket.docket_number, r.content.decode())
        self.assertIn(docket_2.docket_number, r.content.decode())
        self.assertIn(empty_docket.docket_number, r.content.decode())
        self._assert_results_header_content(r.content.decode(), "3 Cases")
        self._assert_results_header_content(
            r.content.decode(), "3 Docket Entries"
        )

        with self.captureOnCommitCallbacks(execute=True):
            docket.delete()
            docket_2.delete()
            docket_3.delete()
            empty_docket.delete()

    async def test_atty_name_filter(self) -> None:
        """Confirm atty_name filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "atty_name": "Debbie Russell"}

        # Frontend, 2 result expected since RECAPDocuments are grouped by case
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

        # Advanced query string, pacer_case_id
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"pacer_case_id:{self.de_1.docket.pacer_case_id}",
        }
        # Frontend
        r = await self._test_article_count(params, 1, "pacer_case_id")
        # 1 Child document matched.
        self._count_child_documents(0, r.content.decode(), 1, "pacer_case_id")

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

        self._count_child_documents(0, r.content.decode(), 1, '"cites"')

        # Add a new OpinionsCitedByRECAPDocument
        with self.captureOnCommitCallbacks(execute=True):
            opinion_2 = OpinionWithParentsFactory()
            OpinionsCitedByRECAPDocument.objects.bulk_create(
                [
                    OpinionsCitedByRECAPDocument(
                        citing_document=self.rd_att,
                        cited_opinion=opinion_2,
                        depth=1,
                    )
                ]
            )
            # Update changes in ES using index_related_cites_fields
            index_related_cites_fields.delay(
                OpinionsCitedByRECAPDocument.__name__, self.rd_att.pk
            )
        # Frontend
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"cites:({opinion_2.pk} OR {self.opinion.pk})",
        }
        r = async_to_sync(self._test_article_count)(params, 1, "cites")
        # Count child documents under docket.
        self._count_child_documents(0, r.content.decode(), 2, '"cites"')
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

        self.assertIn("<mark>SUBPOENAS SERVED OFF</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>SUBPOENAS SERVED OFF</mark>"), 1
        )

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

        self.assertIn("<mark>Thalassa Miller</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Thalassa Miller</mark>"), 1
        )

        # Highlight referred_to.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Persephone Sinclair"}

        r = await self._test_article_count(params, 1, "highlights referred_to")
        # Count child documents under docket.
        self._count_child_documents(
            0, r.content.decode(), 2, "highlights case name"
        )

        self.assertIn("<mark>Persephone Sinclair</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Persephone Sinclair</mark>"), 1
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

        self.assertIn("<mark>Discharging Debtor</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Discharging Debtor</mark>"), 1
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
        self.assertEqual(
            r.content.decode().count("<mark>Maecenas nunc</mark>"), 1
        )
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
        self.assertEqual(
            r.content.decode().count("<mark>Document attachment</mark>"), 1
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
        self.assertIn("<mark>Miller</mark>", r.content.decode())

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
        self.assertIn("<mark>Document attachment</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Document attachment</mark>"), 1
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
        search_term = search_phrase.replace('"', "")
        self.assertIn(f"<mark>{search_term}</mark>", r.content.decode())

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
        search_term = search_phrase.replace('"', "")
        self.assertIn(f"<mark>{search_term}</mark>", r.content.decode())

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
        self.assertIn(
            "<mark>this was finished, this unwieldy process</mark>",
            r.content.decode(),
        )
        self.assertIn("<mark>ipsum</mark>", r.content.decode())

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
                    source=Docket.RECAP,
                ),
                entry_number=4,
                date_filed=None,
            )
            RECAPDocumentFactory(
                docket_entry=de_4,
                document_number="4",
            )
            firm = AttorneyOrganizationFactory(
                lookup_key="280kingofi",
                name="Law Firm LLP",
            )
            attorney = AttorneyFactory(
                name="Debbie Russell",
                organizations=[firm],
                docket=de_4.docket,
            )
            PartyTypeFactory.create(
                party=PartyFactory(
                    name="Defendant Jane Roe",
                    docket=de_4.docket,
                    attorneys=[attorney],
                ),
                docket=de_4.docket,
            )
            index_docket_parties_in_es.delay(de_4.docket.pk)

            de_5 = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    docket_number="12-1238",
                    court=self.court_2,
                    case_name="Macenas Justo",
                    source=Docket.RECAP,
                ),
                date_filed=datetime.date(2013, 6, 19),
            )
            RECAPDocumentFactory(
                docket_entry=de_5,
                document_number="5",
            )

            # Docket entry with a very old date_filed.
            de_6 = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    docket_number="12-0000",
                    court=self.court_2,
                    case_name="SUBPOENAS SERVED OLD",
                    source=Docket.RECAP,
                ),
                entry_number=6,
                date_filed=datetime.date(1732, 2, 23),
            )
            RECAPDocumentFactory(
                docket_entry=de_6,
                document_number="6",
            )
            PartyTypeFactory.create(
                party=PartyFactory(
                    name="Defendant Jane Roe",
                    docket=de_5.docket,
                    attorneys=[attorney],
                ),
                docket=de_5.docket,
            )
            index_docket_parties_in_es.delay(de_5.docket.pk)

            empty_docket = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED FIVE",
                docket_number="12-1237",
                source=Docket.RECAP,
            )

            PartyTypeFactory.create(
                party=PartyFactory(
                    name="Defendant Jane Roe",
                    docket=empty_docket,
                    attorneys=[attorney],
                ),
                docket=empty_docket,
            )
            index_docket_parties_in_es.delay(empty_docket.pk)

        # Order by entry_date_filed desc
        # Ordering by a child field, dockets without entries should come last.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "entry_date_filed desc",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 5, "order entry_date_filed desc"
        )

        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235")
            < r.content.decode().index("12-0000")
            < r.content.decode().index("12-1236")
            < r.content.decode().index("12-1237"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by entry_date_filed  desc.",
        )

        # Order by entry_date_filed asc
        # Ordering by a child field, dockets without entries should come last.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "entry_date_filed asc",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 5, "order entry_date_filed asc"
        )
        self.assertTrue(
            r.content.decode().index("12-0000")
            < r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1236")
            < r.content.decode().index("12-1237"),
            msg="'12-0000' should come BEFORE '12-1235' when order_by entry_date_filed asc.",
        )

        # Order by entry_date_filed desc in match all queries.
        # Ordering by a child field, dockets without entries should come last.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "entry_date_filed desc",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 6, "order entry_date_filed desc"
        )
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1235")
            < r.content.decode().index("12-1238")
            < r.content.decode().index("12-0000")
            < r.content.decode().index("12-1236")
            < r.content.decode().index("12-1237"),
            msg="'1:21-bk-1234' should come BEFORE '12-1235' when order_by entry_date_filed  desc.",
        )

        # Order by entry_date_filed asc in match all queries.
        # Ordering by a child field, dockets without entries should come last.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "entry_date_filed asc",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 6, "order entry_date_filed asc"
        )
        self.assertTrue(
            r.content.decode().index("12-0000")
            < r.content.decode().index("12-1238")
            < r.content.decode().index("12-1235")
            < r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1236")
            < r.content.decode().index("12-1237"),
            msg="'12-0000' should come BEFORE '12-1238' when order_by entry_date_filed asc.",
        )

        # Order by entry_date_filed desc filtering only parties
        # Ordering by a child field, dockets without entries should come last.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "entry_date_filed desc",
            "party_name": "Defendant Jane Roe",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 4, "order entry_date_filed desc"
        )
        self.assertTrue(
            r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1238")
            < r.content.decode().index("12-1236")
            < r.content.decode().index("12-1237"),
            msg="'1:21-bk-1234' should come BEFORE '12-1238' when order_by entry_date_filed  desc.",
        )

        # Order by entry_date_filed asc filtering only parties.
        # Ordering by a child field, dockets without entries should come last.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "entry_date_filed asc",
            "party_name": "Defendant Jane Roe",
        }
        # Frontend
        r = async_to_sync(self._test_article_count)(
            params, 4, "order entry_date_filed asc"
        )
        self.assertTrue(
            r.content.decode().index("12-1238")
            < r.content.decode().index("1:21-bk-1234")
            < r.content.decode().index("12-1236")
            < r.content.decode().index("12-1237"),
            msg="'12-1238' should come BEFORE '1:21-bk-1234' when order_by entry_date_filed asc.",
        )

        with self.captureOnCommitCallbacks(execute=True):
            de_4.docket.delete()
            de_5.docket.delete()
            de_6.docket.delete()
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
                source=Docket.RECAP,
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


class RECAPSearchAPICommonTests(RECAPSearchTestCase):

    version_api = "v3"
    skip_common_tests = True

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

    @skip_if_common_tests_skipped
    async def test_case_name_filter(self) -> None:
        """Confirm case_name filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "SUBPOENAS SERVED OFF",
        }

        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 1, "case_name")

    @skip_if_common_tests_skipped
    async def test_court_filter(self) -> None:
        """Confirm court filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "court": "canb"}

        # Double the results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(params, expected_results, "court")

    @skip_if_common_tests_skipped
    async def test_document_description_filter(self) -> None:
        """Confirm description filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "description": "MOTION for Leave to File Amicus Curiae Lorem",
        }
        # # More results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(
            params, expected_results, "description"
        )

    @skip_if_common_tests_skipped
    async def test_docket_number_filter(self) -> None:
        """Confirm docket_number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "docket_number": "1:21-bk-1234"}

        # # More results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(
            params, expected_results, "docket_number"
        )

    @skip_if_common_tests_skipped
    async def test_attachment_number_filter(self) -> None:
        """Confirm attachment number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "attachment_number": 2}

        await self._test_api_results_count(params, 1, "attachment_number")

    @skip_if_common_tests_skipped
    async def test_assigned_to_judge_filter(self) -> None:
        """Confirm assigned_to filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "assigned_to": "Thalassa Miller"}

        # # More results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(
            params, expected_results, "assigned_to"
        )

    @skip_if_common_tests_skipped
    async def test_referred_to_judge_filter(self) -> None:
        """Confirm referred_to_judge filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "referred_to": "Persephone Sinclair",
        }

        # # More results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(
            params, expected_results, "referred_to"
        )

    @skip_if_common_tests_skipped
    async def test_nature_of_suit_filter(self) -> None:
        """Confirm nature_of_suit filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "nature_of_suit": "440"}

        # # More results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(
            params, expected_results, "nature_of_suit"
        )

    @skip_if_common_tests_skipped
    async def test_filed_after_filter(self) -> None:
        """Confirm filed_after filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "filed_after": "2016-08-16"}

        await self._test_api_results_count(params, 1, "filed_after")

    @skip_if_common_tests_skipped
    async def test_filed_before_filter(self) -> None:
        """Confirm filed_before filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "filed_before": "2015-08-17"}

        # # More results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(
            params, expected_results, "filed_before"
        )

    @skip_if_common_tests_skipped
    async def test_document_number_filter(self) -> None:
        """Confirm document number filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "document_number": "3"}

        await self._test_api_results_count(params, 1, "document_number")

    @skip_if_common_tests_skipped
    async def test_available_only_field(self) -> None:
        """Confirm available only filter works properly"""
        params = {"type": SEARCH_TYPES.RECAP, "available_only": True}

        # API
        await self._test_api_results_count(params, 1, "available_only")

    @skip_if_common_tests_skipped
    async def test_combine_filters(self) -> None:
        """Confirm that combining filters works properly"""
        # Get results for a broad filter
        params = {"type": SEARCH_TYPES.RECAP, "case_name": "SUBPOENAS SERVED"}

        # More results expected in v3 since the results are not grouped.
        expected_results = 3 if self.version_api == "v3" else 2
        await self._test_api_results_count(
            params, expected_results, "case_name"
        )

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

    @skip_if_common_tests_skipped
    async def test_text_queries(self) -> None:
        """Confirm text queries works properly"""
        # Text query case name.
        params = {"type": SEARCH_TYPES.RECAP, "q": "SUBPOENAS SERVED OFF"}
        # API
        await self._test_api_results_count(params, 1, "text query case name")

        # Text query description.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Amicus Curiae Lorem"}

        # More results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(
            params, expected_results, "text query description"
        )

        # Text query text.
        params = {"type": SEARCH_TYPES.RECAP, "q": "PACER Document Franklin"}

        # API
        await self._test_api_results_count(params, 1, "text query text")

        # Text query text judge.
        params = {"type": SEARCH_TYPES.RECAP, "q": "Thalassa Miller"}

        # More results expected in v3 since the results are not grouped.
        expected_results = 2 if self.version_api == "v3" else 1
        await self._test_api_results_count(
            params, expected_results, "text query judge"
        )


class RECAPSearchAPIV3Test(RECAPSearchAPICommonTests, IndexedSolrTestCase):
    """
    RECAP Search API V3 Tests
    """

    tests_running_over_solr = True
    skip_common_tests = False

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def setUp(self) -> None:
        add_docket_to_solr_by_rds(
            [self.rd.pk, self.rd_att.pk], force_commit=True
        )
        add_docket_to_solr_by_rds([self.rd_2.pk], force_commit=True)
        super().setUp()

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


class DocketESResultSerializerTest(DocketESResultSerializer):
    """The serializer class for testing DOCKETS search type results. Includes a
    date_score field for testing purposes.
    """

    date_score = CharField(read_only=True)


class BaseRECAPDocumentESResultSerializerTest(
    BaseRECAPDocumentESResultSerializer
):
    """The serializer class for testing RECAP_DOCUMENT search type results.
    Includes a date_score field for testing purposes.
    """

    date_score = CharField(read_only=True)


class RECAPESResultSerializerTest(RECAPESResultSerializer):
    """The serializer class for resting RECAP search type results. Includes a
    date_score field for testing purposes.
    """

    date_score = CharField(read_only=True)


class RECAPSearchAPIV4Test(
    RECAPSearchAPICommonTests, ESIndexTestCase, TestCase
):
    """
    RECAP Search API V4 Tests
    """

    version_api = "v4"
    skip_common_tests = False

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")
        super().setUpTestData()

        cls.mock_date = now().replace(day=15, hour=0)
        with time_machine.travel(cls.mock_date, tick=False):
            cls.judge_api = PersonFactory.create(
                name_first="George", name_last="Doe", name_suffix="2"
            )
            cls.court_api = CourtFactory(
                id="ca9", jurisdiction="F", citation_string="Appeals. CA9."
            )
            cls.de_api = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=cls.court_api,
                    case_name="America vs API Lorem",
                    case_name_full="America vs API Lorem vs. Bank",
                    date_filed=datetime.date(2016, 4, 16),
                    date_argued=datetime.date(2022, 5, 20),
                    date_reargued=datetime.date(2023, 5, 21),
                    date_terminated=datetime.date(2023, 7, 21),
                    docket_number="1:24-bk-0000",
                    assigned_to=cls.judge_api,
                    referred_to=cls.judge_api,
                    nature_of_suit="569",
                    source=Docket.RECAP,
                    cause="401 Civil",
                    jury_demand="Plaintiff",
                    jurisdiction_type="U.S. Government Defendant",
                ),
                entry_number=1,
                date_filed=datetime.date(2020, 8, 19),
                description="MOTION for Leave Lorem vs America",
            )
            cls.firm_api = AttorneyOrganizationFactory(
                name="Associates America", lookup_key="firm_api"
            )
            cls.attorney_api = AttorneyFactory(
                name="John Doe",
                organizations=[cls.firm_api],
                docket=cls.de_api.docket,
            )
            cls.party_type = PartyTypeFactory.create(
                party=PartyFactory(
                    name="Defendant John Doe",
                    docket=cls.de_api.docket,
                    attorneys=[cls.attorney_api],
                ),
                docket=cls.de_api.docket,
            )
            cls.rd_api = RECAPDocumentFactory(
                docket_entry=cls.de_api,
                description="Order Letter",
                document_number="2",
                is_available=False,
                page_count=100,
                pacer_doc_id="019036000435",
                plain_text="This a plain text to be shown in the API",
            )
            OpinionsCitedByRECAPDocument.objects.create(
                citing_document=cls.rd_api,
                cited_opinion=cls.opinion,
                depth=1,
            )
            BankruptcyInformationFactory(docket=cls.de_api.docket)

            cls.de_empty_fields_api = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=cls.court_api,
                    date_reargued=None,
                    source=Docket.RECAP_AND_SCRAPER,
                    pacer_case_id=None,
                    case_name="",
                    case_name_full="",
                ),
                description="",
            )
            cls.rd_empty_fields_api = RECAPDocumentFactory(
                docket_entry=cls.de_empty_fields_api,
                description="empty fields",
                pacer_doc_id="",
            )

            cls.empty_docket_api = DocketFactory(
                court=cls.court_api,
                date_argued=None,
                source=Docket.RECAP_AND_IDB,
            )
            call_command(
                "cl_index_parent_and_child_docs",
                search_type=SEARCH_TYPES.RECAP,
                queue="celery",
                pk_offset=0,
                testing_mode=True,
            )
            # Index parties in ES.
            index_docket_parties_in_es.delay(cls.de_api.docket.pk)

    @staticmethod
    def mock_merge_unavailable_fields_on_parent_document(*args, **kwargs):
        """Mock function that first deletes a specific RECAPDocument
        and then calls the original merge function with the provided arguments.
        """

        rd = RECAPDocument.objects.get(pacer_doc_id="rd_to_delete")
        rd.delete()
        return merge_unavailable_fields_on_parent_document(*args, **kwargs)

    @staticmethod
    def mock_set_results_highlights(results, search_type):
        """Intercepts set_results_highlights as a helper to append the
        date_score for testing purposes.
        """
        set_results_highlights(results, search_type)
        for result in results:
            if hasattr(result.meta, "sort"):
                result["date_score"] = result.meta.sort[0]

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

    async def _test_api_fields_content(
        self, api_response, content_to_compare, fields_to_compare
    ):
        for (
            field,
            get_expected_value,
        ) in fields_to_compare.items():
            with self.subTest(field=field):
                actual_value = api_response.data["results"][0].get(field)
                if field == "recap_documents":
                    for child_field, child_value in actual_value[0].items():
                        with self.subTest(child_field=child_field):
                            get_child_expected_value = (
                                recap_document_v4_api_keys.get(child_field)
                            )
                            child_expected_value = await sync_to_async(
                                get_child_expected_value
                            )(content_to_compare)
                            self.assertEqual(
                                child_value,
                                child_expected_value,
                                f"Child field '{field}' does not match.",
                            )
                else:
                    expected_value = await sync_to_async(get_expected_value)(
                        content_to_compare
                    )
                    self.assertEqual(
                        actual_value,
                        expected_value,
                        f"Parent field '{field}' does not match.",
                    )

    def _test_results_ordering(self, test, field):
        """Ensure dockets appear in the response in a specific order."""

        with self.subTest(test=test, msg=f'{test["name"]}'):
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}),
                test["search_params"],
            )
            self.assertEqual(len(r.data["results"]), test["expected_results"])
            # Note that dockets where the date_field is null are sent to the bottom
            # of the results
            actual_order = [result[field] for result in r.data["results"]]
            self.assertEqual(
                actual_order,
                test["expected_order"],
                msg=f'Expected order {test["expected_order"]}, but got {actual_order}',
            )

    def _test_page_variables(
        self, response, test_case, current_page, search_type
    ):
        """Ensure the page variables are the correct ones according to the
        current page."""

        # Test page
        self.assertEqual(
            len(response.data["results"]),
            test_case["results"],
            msg="Results in page didn't match.",
        )
        self.assertEqual(
            response.data["count"],
            test_case["count_exact"],
            msg="Results count didn't match.",
        )
        if search_type == SEARCH_TYPES.RECAP:
            self.assertEqual(
                response.data["document_count"],
                test_case["document_count"],
                msg="Document count didn't match.",
            )
        else:
            self.assertNotIn(
                "document_count",
                response.data,
                msg="Document count should not be present.",
            )

        next_page = response.data["next"]
        expected_next_page = test_case["next"]
        if expected_next_page:
            self.assertTrue(next_page, msg="Next page value didn't match")
            current_page = next_page
        else:
            self.assertFalse(next_page, msg="Next page value didn't match")

        previous_page = response.data["previous"]
        expected_previous_page = test_case["previous"]
        if expected_previous_page:
            self.assertTrue(
                previous_page,
                msg="Previous page value didn't match",
            )
        else:
            self.assertFalse(
                previous_page,
                msg="Previous page value didn't match",
            )
        return next_page, previous_page, current_page

    async def test_case_name_filter(self) -> None:
        """Confirm case_name filter works properly"""
        params = {
            "type": SEARCH_TYPES.RECAP,
            "case_name": "SUBPOENAS SERVED OFF",
        }
        # API, 2 result expected since RECAPDocuments are not grouped.
        await self._test_api_results_count(params, 1, "case_name")

    async def test_results_api_fields(self) -> None:
        """Confirm fields in V4 RECAP Search API results."""
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"id:{self.rd_api.pk}",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")

        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, len(docket_v4_api_keys))
        rd_keys_count = len(r.data["results"][0]["recap_documents"][0])
        self.assertEqual(rd_keys_count, len(recap_document_v4_api_keys))
        content_to_compare = {"result": self.rd_api}
        await self._test_api_fields_content(
            r, content_to_compare, docket_v4_api_keys
        )

    async def test_results_api_empty_fields(self) -> None:
        """Confirm empty fields values in V4 RECAP Search API results."""

        # Confirm expected values for empty fields.
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"id:{self.rd_empty_fields_api.pk}",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")

        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, len(docket_v4_api_keys))
        rd_keys_count = len(r.data["results"][0]["recap_documents"][0])
        self.assertEqual(rd_keys_count, len(recap_document_v4_api_keys))
        content_to_compare = {"result": self.rd_empty_fields_api}
        await self._test_api_fields_content(
            r, content_to_compare, docket_v4_api_keys
        )

        # Query a docket with no filings.
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"docket_id:{self.empty_docket_api.pk}",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, len(docket_v4_api_keys))
        recap_documents = r.data["results"][0].get("recap_documents")
        self.assertEqual(recap_documents, [])

    async def test_results_api_highlighted_fields(self) -> None:
        """Confirm highlighted fields in V4 RECAP Search API results."""
        # API HL disabled.
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"id:{self.rd_api.pk} cause:(401 Civil) court_citation_string:Appeals juryDemand:Plaintiff short_description:(Order Letter) plain_text:(shown in the API)",
            "assigned_to": "George",
            "referred_to": "George",
            "case_name": "America vs API",
            "docket_number": "1:24-bk-0000",
            "nature_of_suit": "569",
            "description": "MOTION for Leave",
        }

        # RECAP Search type HL disabled.
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, len(docket_v4_api_keys))
        rd_keys_count = len(r.data["results"][0]["recap_documents"][0])
        self.assertEqual(rd_keys_count, len(recap_document_v4_api_keys))
        content_to_compare = {
            "result": self.rd_api,
        }
        await self._test_api_fields_content(
            r, content_to_compare, docket_v4_api_keys
        )

        # RECAP_DOCUMENT Search type HL disabled.
        search_params["type"] = SEARCH_TYPES.RECAP_DOCUMENT
        r = await self._test_api_results_count(search_params, 1, "API fields")
        await self._test_api_fields_content(
            r, content_to_compare, recap_document_v4_api_keys
        )

        # RECAP Search type HL enabled.
        search_params["type"] = SEARCH_TYPES.RECAP
        search_params["highlight"] = True
        r = await self._test_api_results_count(search_params, 1, "API fields")
        content_to_compare = {
            "result": self.rd_api,
            "assignedTo": "<mark>George</mark> Doe II",
            "caseName": "<mark>America</mark> <mark>vs</mark> <mark>API</mark> Lorem",
            "cause": "<mark>401</mark> <mark>Civil</mark>",
            "court_citation_string": "<mark>Appeals</mark>. CA9.",
            "docketNumber": "<mark>1:24-bk-0000</mark>",
            "juryDemand": "<mark>Plaintiff</mark>",
            "referredTo": "<mark>George</mark> Doe II",
            "suitNature": "<mark>569</mark>",
            "description": "<mark>MOTION</mark> <mark>for</mark> <mark>Leave</mark> Lorem vs America",
            "short_description": "<mark>Order Letter</mark>",
            "snippet": "This a plain text to be <mark>shown in the API</mark>",
        }
        await self._test_api_fields_content(
            r, content_to_compare, docket_v4_api_keys
        )

        # RECAP_DOCUMENT Search type HL enabled.
        search_params["type"] = SEARCH_TYPES.RECAP_DOCUMENT
        r = await self._test_api_results_count(search_params, 1, "API fields")
        await self._test_api_fields_content(
            r, content_to_compare, recap_document_v4_api_keys
        )

    def test_date_filed_sorting_function_score(self) -> None:
        """Test if the function score used for the dateFiled sorting in the V4
        of the RECAP Search API works as expected."""

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            # This Docket will be matched only by its RECAPDocument.
            docket_entry_recent = DocketEntryWithParentsFactory(
                docket__source=Docket.RECAP,
                docket__case_name="Lorem Ipsum",
                docket__date_filed=datetime.date(2024, 2, 23),
                date_filed=datetime.date(2022, 2, 23),
            )
            RECAPDocumentFactory(
                docket_entry=docket_entry_recent,
                description="SUBPOENAS SERVED NEW",
            )
            docket_old = DocketFactory(
                case_name="SUBPOENAS SERVED OLD",
                source=Docket.RECAP,
                date_filed=datetime.date(1732, 2, 23),
            )
            docket_null_date_filed = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED NULL",
                source=Docket.RECAP,
            )

        # Query string, order by dateFiled desc
        search_params = {
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled desc",
            "highlight": False,
        }

        params_date_filed_asc = search_params.copy()
        params_date_filed_asc["order_by"] = "dateFiled asc"

        params_entry_date_filed_asc = search_params.copy()
        params_entry_date_filed_asc["order_by"] = "entry_date_filed asc"

        params_match_all_date_filed_desc = search_params.copy()
        del params_match_all_date_filed_desc["q"]
        params_match_all_date_filed_desc["order_by"] = "dateFiled desc"

        params_match_all_date_filed_asc = search_params.copy()
        del params_match_all_date_filed_asc["q"]
        params_match_all_date_filed_asc["order_by"] = "dateFiled asc"

        params_match_all_entry_date_filed_asc = search_params.copy()
        del params_match_all_entry_date_filed_asc["q"]
        params_match_all_entry_date_filed_asc["order_by"] = (
            "entry_date_filed asc"
        )

        test_cases = [
            {
                "name": "Query string, order by dateFiled desc",
                "search_params": search_params,
                "expected_results": 5,
                "expected_order": [
                    docket_entry_recent.docket.pk,  # 2024/02/23
                    self.de_1.docket.pk,  # 2016/08/16
                    self.de.docket.pk,  # 2015/8/16
                    docket_old.pk,  # 1732/2/23
                    docket_null_date_filed.pk,  # Null date_filed, pk 1
                ],
            },
            {
                "name": "Query string, order by dateFiled asc",
                "search_params": params_date_filed_asc,
                "expected_results": 5,
                "expected_order": [
                    docket_old.pk,  # 1732/2/23
                    self.de.docket.pk,  # 2015/8/16
                    self.de_1.docket.pk,  # 2016/08/16
                    docket_entry_recent.docket.pk,  # 2024/02/23
                    docket_null_date_filed.pk,  # Null date_filed, pk 1
                ],
            },
            {
                "name": "Match all query, order by dateFiled desc",
                "search_params": params_match_all_date_filed_desc,
                "expected_results": 8,
                "expected_order": [
                    docket_entry_recent.docket.pk,  # 2024/2/23
                    self.de_1.docket.pk,  # 2016/8/16
                    self.de_api.docket.pk,  # 2016/4/16
                    self.de.docket.pk,  # 2015/8/16
                    docket_old.pk,  # 1732/2/23
                    docket_null_date_filed.pk,  # Null date_filed, pk 3
                    self.empty_docket_api.pk,  # Null date_filed, pk 2
                    self.de_empty_fields_api.docket.pk,  # Null date_filed, pk 1
                ],
            },
            {
                "name": "Match all query, order by dateFiled asc",
                "search_params": params_match_all_date_filed_asc,
                "expected_results": 8,
                "expected_order": [
                    docket_old.pk,  # 1732/2/23
                    self.de.docket.pk,  # 2015/8/16
                    self.de_api.docket.pk,  # 2016/4/16
                    self.de_1.docket.pk,  # 2016/8/16
                    docket_entry_recent.docket.pk,  # 2024/2/23
                    docket_null_date_filed.pk,  # Null date_filed, pk 3
                    self.empty_docket_api.pk,  # Null date_filed, pk 2
                    self.de_empty_fields_api.docket.pk,  # Null date_filed, pk 1
                ],
            },
            {
                "name": "Query string, order by entry_date_filed asc",
                "search_params": params_entry_date_filed_asc,
                "expected_results": 5,
                "expected_order": [
                    self.de_1.docket.pk,  # 2014/7/19
                    self.de.docket.pk,  # 2015/8/16
                    docket_entry_recent.docket.pk,  # 2022/2/23
                    docket_null_date_filed.pk,  # Null date_filed, pk 3
                    docket_old.pk,  # 1732/2/23 No RD, pk 2
                ],
            },
            {
                "name": "Match all query, order by  entry_date_filed asc",
                "search_params": params_match_all_entry_date_filed_asc,
                "expected_results": 8,
                "expected_order": [
                    self.de_1.docket.pk,  # 2014/7/19
                    self.de.docket.pk,  # 2015/8/16
                    self.de_api.docket.pk,  # 2020/8/19
                    docket_entry_recent.docket.pk,  # 2022/2/23
                    self.de_empty_fields_api.docket.pk,  # Null entry_date_filed but RD document, pk 1
                    docket_null_date_filed.pk,  # No RD, pk 4 *
                    docket_old.pk,  # No RD, pk 3 *
                    self.empty_docket_api.pk,  # Null entry_date_filed, pk 2 *
                ],
            },
        ]

        search_types = [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]
        for search_type in search_types:
            for test in test_cases:
                test["search_params"]["type"] = search_type
                self._test_results_ordering(test, "docket_id")

        with self.captureOnCommitCallbacks(execute=True):
            docket_entry_recent.docket.delete()
            docket_old.delete()
            docket_null_date_filed.delete()

    @override_settings(SEARCH_API_PAGE_SIZE=1)
    @mock.patch(
        "cl.search.api_views.DocketESResultSerializer",
        new=DocketESResultSerializerTest,
    )
    @mock.patch(
        "cl.search.api_views.BaseRECAPDocumentESResultSerializer",
        new=BaseRECAPDocumentESResultSerializerTest,
    )
    @mock.patch(
        "cl.search.api_views.RECAPESResultSerializer",
        new=RECAPESResultSerializerTest,
    )
    @mock.patch(
        "cl.search.api_utils.set_results_highlights",
        side_effect=mock_set_results_highlights,
    )
    def test_stable_scores_date_sort(
        self, mock_set_results_highlights
    ) -> None:
        """Test if the function's score remains stable when used for sorting by
        dateFiled asc and entry_date_filed asc across pagination, avoiding
        the impact of time running on the scores.
        """

        # Query string, order by dateFiled desc
        search_params = {
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled asc",
            "highlight": False,
        }

        # string query date_filed asc
        date_filed_asc_string_query = search_params
        # match_all query date_filed asc
        date_filed_asc_match_all = search_params.copy()
        del date_filed_asc_match_all["q"]
        # string query entry_date_filed asc
        entry_filed_asc_string_query = search_params.copy()
        entry_filed_asc_string_query["order_by"] = "entry_date_filed asc"
        # match_all query entry_date_filed asc
        entry_filed_asc_match_all = entry_filed_asc_string_query.copy()
        del entry_filed_asc_match_all["q"]

        tests_params = [
            date_filed_asc_string_query,
            date_filed_asc_match_all,
            entry_filed_asc_string_query,
            entry_filed_asc_match_all,
        ]
        # Generate tests for all the search types.
        all_tests = []
        for test_param in tests_params:
            for search_type in [
                SEARCH_TYPES.RECAP,
                SEARCH_TYPES.DOCKETS,
                SEARCH_TYPES.RECAP_DOCUMENT,
            ]:
                test_param_copy = test_param.copy()
                test_param_copy["type"] = search_type
                all_tests.append(test_param_copy)

        for search_params in all_tests:
            with self.subTest(
                search_params=search_params, msg="Test stable scores."
            ):
                original_datetime = now().replace(day=1, hour=5, minute=0)
                # Two first-page requests (no cursor) made on the same day will now
                # have consistent scores because scores are now computed based on the
                # same day's date.
                with time_machine.travel(original_datetime, tick=False):
                    r = self.client.get(
                        reverse("search-list", kwargs={"version": "v4"}),
                        search_params,
                    )
                    date_score_1 = r.data["results"][0]["date_score"]

                with time_machine.travel(
                    original_datetime + datetime.timedelta(minutes=1),
                    tick=False,
                ):
                    r = self.client.get(
                        reverse("search-list", kwargs={"version": "v4"}),
                        search_params,
                    )
                    date_score_2 = r.data["results"][0]["date_score"]

                self.assertEqual(date_score_1, date_score_2)

                # Two first-page requests (no cursor) made on different days will
                # present scores variations, due to it being a different day and
                # date_filed and entry_date_filed are day granular.
                with time_machine.travel(
                    original_datetime + datetime.timedelta(days=1), tick=False
                ):
                    r = self.client.get(
                        reverse("search-list", kwargs={"version": "v4"}),
                        search_params,
                    )
                    date_score_1 = r.data["results"][0]["date_score"]

                with time_machine.travel(
                    original_datetime + datetime.timedelta(days=2), tick=False
                ):
                    r = self.client.get(
                        reverse("search-list", kwargs={"version": "v4"}),
                        search_params,
                    )
                    date_score_2 = r.data["results"][0]["date_score"]

                self.assertNotEqual(date_score_2, date_score_1)

                # Two next_page requests preserver the same scores even thought they
                # are executed on different days. Since scores are computed base on the
                # cursor context date.
                next_page = r.data["next"]
                with time_machine.travel(
                    original_datetime + datetime.timedelta(days=3), tick=False
                ):
                    r = self.client.get(next_page)
                date_score_next_1 = r.data["results"][0]["date_score"]

                # Two next_page requests preserve the same scores even though they are
                # executed on different days. Since scores are computed based on the
                # cursor context date.
                with time_machine.travel(
                    original_datetime + datetime.timedelta(days=4), tick=False
                ):
                    r = self.client.get(next_page)
                date_score_next_2 = r.data["results"][0]["date_score"]
                previous_page = r.data["previous"]
                self.assertEqual(date_score_next_1, date_score_next_2)

                # Now, going to the previous day, the score should be the same as the
                # first request that showed the document.
                with time_machine.travel(
                    original_datetime + datetime.timedelta(days=4), tick=False
                ):
                    r = self.client.get(previous_page)

                date_score_previous_2 = r.data["results"][0]["date_score"]
                self.assertEqual(date_score_2, date_score_previous_2)

    @override_settings(SEARCH_API_PAGE_SIZE=6)
    def test_recap_results_cursor_api_pagination_for_r_type(self) -> None:
        """Test cursor pagination for V4 RECAP Search API."""

        created_dockets = []
        dockets_to_create = 20
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            for _ in range(dockets_to_create):
                docket_entry = DocketEntryWithParentsFactory(
                    docket__source=Docket.RECAP,
                )
                RECAPDocumentFactory(
                    docket_entry=docket_entry,
                )
                created_dockets.append(docket_entry.docket)

        total_dockets = Docket.objects.all().count()
        total_rds = RECAPDocument.objects.all().count()
        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "score desc",
            "highlight": False,
        }
        tests = [
            {
                "results": 6,
                "count_exact": total_dockets,
                "document_count": total_rds,
                "next": True,
                "previous": False,
            },
            {
                "results": 6,
                "count_exact": total_dockets,
                "document_count": total_rds,
                "next": True,
                "previous": True,
            },
            {
                "results": 6,
                "count_exact": total_dockets,
                "document_count": total_rds,
                "next": True,
                "previous": True,
            },
            {
                "results": 6,
                "count_exact": total_dockets,
                "document_count": total_rds,
                "next": True,
                "previous": True,
            },
            {
                "results": 1,
                "count_exact": total_dockets,
                "document_count": total_rds,
                "next": False,
                "previous": True,
            },
        ]
        order_types = [
            "score desc",
            "dateFiled desc",
            "dateFiled asc",
            "entry_date_filed asc",
            "entry_date_filed desc",
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
                    total_dockets,
                    msg="Wrong number of dockets.",
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
                        _, previous_page, current_page = (
                            self._test_page_variables(
                                r, test, current_page, search_params["type"]
                            )
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
                            msg="Wrong dockets.",
                        )

                # Confirm all the documents were shown when paginating backwards.
                self.assertEqual(
                    len(all_ids_prev),
                    total_dockets,
                    msg="Wrong number of dockets.",
                )

        with self.captureOnCommitCallbacks(execute=True):
            # Remove Docket objects to avoid affecting other tests.
            for created_docket in created_dockets:
                created_docket.delete()

    def test_recap_cursor_api_pagination_count(self) -> None:
        """Test cursor pagination count for V4 RECAP Search API."""

        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "score desc",
            "highlight": False,
        }
        total_dockets = Docket.objects.all().count()
        total_rds = RECAPDocument.objects.all().count()

        ## Get count from cardinality.
        with override_settings(ELASTICSEARCH_MAX_RESULT_COUNT=total_dockets):
            # RECAP Search request, count dockets.
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_dockets,
                msg="Results count didn't match.",
            )
            self.assertEqual(
                r.data["document_count"],
                total_rds,
                msg="Document count didn't match.",
            )

            # DOCKETS Search request, count dockets.
            search_params["type"] = SEARCH_TYPES.DOCKETS
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_dockets,
                msg="Results count didn't match.",
            )
            self.assertNotIn(
                "document_count",
                r.data,
                msg="Document count should not be present.",
            )

        with override_settings(ELASTICSEARCH_MAX_RESULT_COUNT=total_rds):
            # RECAP_DOCUMENT Search request, count RDs.
            search_params["type"] = SEARCH_TYPES.RECAP_DOCUMENT
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_rds,
                msg="Results count didn't match.",
            )
            self.assertNotIn(
                "document_count",
                r.data,
                msg="Document count should not be present.",
            )

        ## Get count from main query.
        with override_settings(
            ELASTICSEARCH_MAX_RESULT_COUNT=total_dockets + 1
        ):
            # RECAP Search request, count dockets.
            search_params["type"] = SEARCH_TYPES.RECAP
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_dockets,
                msg="Results count didn't match.",
            )
            # Document count is always retrieved from a cardinality query.
            self.assertEqual(
                r.data["document_count"],
                total_rds,
                msg="Document count didn't match.",
            )

            # DOCKETS Search request, count dockets.
            search_params["type"] = SEARCH_TYPES.DOCKETS
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_dockets,
                msg="Results count didn't match.",
            )
            self.assertNotIn(
                "document_count",
                r.data,
                msg="Document count should not be present.",
            )

        with override_settings(ELASTICSEARCH_MAX_RESULT_COUNT=total_rds + 1):
            # RECAP_DOCUMENT Search request, count RDs.
            search_params["type"] = SEARCH_TYPES.RECAP_DOCUMENT
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_rds,
                msg="Results count didn't match.",
            )
            self.assertNotIn(
                "document_count",
                r.data,
                msg="Document count should not be present.",
            )

    def test_recap_cursor_api_pagination_next_and_previous_page(self) -> None:
        """Test cursor pagination previous_page for V4 RECAP Search API."""

        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "score desc",
            "highlight": False,
        }
        total_dockets = Docket.objects.all().count()

        # Fewer results than page_size, no next page, no previous page.
        with override_settings(SEARCH_API_PAGE_SIZE=total_dockets + 1):
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertIsNone(r.data["next"], msg="Next page doesn't match")
            self.assertIsNone(
                r.data["previous"], msg="Next page doesn't match"
            )

        with override_settings(SEARCH_API_PAGE_SIZE=total_dockets - 1):
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            # No previous page link since we're in the first page, but next.
            self.assertIsNone(
                r.data["previous"], msg="Previous page doesn't macht"
            )
            next_page = r.data["next"]
            self.assertTrue(next_page, msg="Next page doesn't macht")

            # Go to next page, not next page but previous.
            r = self.client.get(next_page)
            self.assertIsNone(r.data["next"], msg="Next page doesn't macht")
            previous_page = r.data["previous"]
            self.assertTrue(previous_page, msg="Previous page doesn't macht")

            # Go back to previous page, first page no previous page but next.
            r = self.client.get(previous_page)
            self.assertTrue(r.data["next"], msg="Next page doesn't macht")
            self.assertIsNone(
                r.data["previous"], msg="Previous page doesn't macht"
            )

    def test_recap_cursor_results_equals_page_size(self) -> None:
        """Test cursor pagination previous and next page when the number of
        equals the page_size."""

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            docket = DocketFactory(source=Docket.RECAP)

        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "score desc",
            "highlight": False,
        }
        total_dockets = Docket.objects.all().count()
        page_size = int(total_dockets / 2)
        with override_settings(SEARCH_API_PAGE_SIZE=page_size):
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            # No previous page link since we're in the first page, but next.
            self.assertIsNone(
                r.data["previous"], msg="Previous page doesn't macht"
            )
            next_page = r.data["next"]
            self.assertTrue(next_page, msg="Next page doesn't macht")

            # Go to next page, previous page but no next since results in page
            # are equal to page_size.
            r = self.client.get(next_page)
            previous_page = r.data["previous"]
            self.assertTrue(previous_page, msg="Previous page doesn't macht")
            self.assertEqual(len(r.data["results"]), page_size)
            self.assertIsNone(r.data["next"], msg="Next page doesn't macht")

            # Go back previous page, next page but no previous since results in
            # page are equal to page_size.
            r = self.client.get(previous_page)
            self.assertIsNone(
                r.data["previous"], msg="Previous page doesn't macht"
            )
            self.assertEqual(len(r.data["results"]), page_size)
            self.assertTrue(r.data["next"], msg="Next page doesn't macht")

        with self.captureOnCommitCallbacks(execute=True):
            docket.delete()

    @override_settings(SEARCH_API_PAGE_SIZE=2)
    def test_recap_cursor_results_consistency(self) -> None:
        """Test cursor pagination results consistency when documents are indexed
        or removed."""

        with self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED 1",
                source=Docket.RECAP,
                date_filed=datetime.date(2023, 2, 23),
            )
            docket_1 = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED 2",
                source=Docket.RECAP,
                date_filed=datetime.date(2022, 2, 23),
            )

        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled desc",
            "highlight": False,
        }

        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}),
            search_params,
        )
        self.assertEqual(len(r.data["results"]), 2)
        self.assertEqual(r.data["count"], 4)
        self.assertEqual(r.data["document_count"], 3)
        next_page = r.data["next"]
        with self.captureOnCommitCallbacks(execute=True):
            docket_0 = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED 0",
                source=Docket.RECAP,
                date_filed=datetime.date(2024, 2, 23),
            )

        ids_in_previous_page = {docket.pk, docket_1.pk, docket_0.pk}
        r = self.client.get(next_page)
        self.assertEqual(len(r.data["results"]), 2)
        self.assertEqual(r.data["count"], 5)
        self.assertEqual(r.data["document_count"], 3)

        current_page_ids = set()
        for result in r.data["results"]:
            current_page_ids.add(result["docket_id"])

        # No Dockets from the previous page are shown in the next page.
        self.assertFalse(ids_in_previous_page & current_page_ids)

        with self.captureOnCommitCallbacks(execute=True):
            docket_0.delete()

        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}),
            search_params,
        )
        self.assertEqual(len(r.data["results"]), 2)
        self.assertEqual(r.data["count"], 4)
        self.assertEqual(r.data["document_count"], 3)
        next_page = r.data["next"]

        with self.captureOnCommitCallbacks(execute=True):
            docket_3 = DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED 3",
                source=Docket.RECAP,
                date_filed=datetime.date(2017, 2, 23),
            )

        r = self.client.get(next_page)
        self.assertEqual(len(r.data["results"]), 2)
        self.assertEqual(r.data["count"], 5)
        self.assertEqual(r.data["document_count"], 3)
        self.assertTrue(r.data["next"])

        current_page_ids = set()
        for result in r.data["results"]:
            current_page_ids.add(result["docket_id"])

        expected_ids = {docket_3.pk, self.de_1.docket.pk}
        # No Dockets from the previous page are shown in the next page.
        self.assertEqual(expected_ids, current_page_ids)

        next_page = r.data["next"]
        r = self.client.get(next_page)
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["count"], 5)
        self.assertEqual(r.data["document_count"], 3)
        self.assertIsNone(r.data["next"])
        self.assertEqual(r.data["results"][0]["docket_id"], self.de.docket.pk)

        with self.captureOnCommitCallbacks(execute=True):
            docket.delete()
            docket_1.delete()
            docket_3.delete()

    @override_settings(SEARCH_API_PAGE_SIZE=6)
    def test_recap_results_more_docs_field(self) -> None:
        """Test the more_docs fields to be shown properly when a docket has
        more than 5 RECAPDocuments matched."""

        rds_to_create = settings.CHILD_HITS_PER_RESULT + 1
        with self.captureOnCommitCallbacks(execute=True):
            docket_entry = DocketEntryWithParentsFactory(
                docket__source=Docket.RECAP,
            )
            for i in range(rds_to_create):
                RECAPDocumentFactory(
                    docket_entry=docket_entry,
                    document_number=i,
                )

        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "score desc",
            "highlight": False,
            "q": f"docket_id:{docket_entry.docket.pk}",
        }

        test_cases = [
            {
                "expected_results": settings.CHILD_HITS_PER_RESULT,
                "more_docs": True,
            },
            {
                "expected_results": settings.CHILD_HITS_PER_RESULT,
                "more_docs": False,
            },
            {
                "expected_results": settings.CHILD_HITS_PER_RESULT - 1,
                "more_docs": False,
            },
        ]

        for test_case in test_cases:
            with self.subTest(test_case=test_case, msg="More docs test."):
                r = self.client.get(
                    reverse("search-list", kwargs={"version": "v4"}),
                    search_params,
                )
                self.assertEqual(len(r.data["results"]), 1)
                self.assertEqual(
                    len(r.data["results"][0]["recap_documents"]),
                    test_case["expected_results"],
                )
                self.assertEqual(
                    r.data["results"][0]["more_docs"], test_case["more_docs"]
                )

                with self.captureOnCommitCallbacks(execute=True):
                    RECAPDocument.objects.filter(
                        docket_entry__docket=docket_entry.docket
                    ).first().delete()

        with self.captureOnCommitCallbacks(execute=True):
            docket_entry.docket.delete()

    async def test_results_fields_for_d_type(self) -> None:
        """Confirm fields in V4 RECAP Search API results for the d type."""

        search_params = {
            "type": SEARCH_TYPES.DOCKETS,
            "q": f"docket_id:{self.rd_api.docket_entry.docket.pk}",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_count = len(r.data["results"][0])

        d_type_v4_api_keys = docket_v4_api_keys.copy()
        del d_type_v4_api_keys["recap_documents"]
        del d_type_v4_api_keys["more_docs"]
        self.assertEqual(keys_count, len(d_type_v4_api_keys))

        content_to_compare = {"result": self.rd_api}
        await self._test_api_fields_content(
            r, content_to_compare, d_type_v4_api_keys
        )

    async def test_results_fields_for_rd_type(self) -> None:
        """Confirm fields in V4 RECAP Search API results for the rd type."""

        search_params = {
            "type": SEARCH_TYPES.RECAP_DOCUMENT,
            "q": f"id:{self.rd_api.pk}",
            "order_by": "score desc",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, len(rd_type_v4_api_keys))

        content_to_compare = {"result": self.rd_api}
        await self._test_api_fields_content(
            r, content_to_compare, rd_type_v4_api_keys
        )

    def test_render_missing_fields_from_es_document(self) -> None:
        """Confirm that missing fields from an ES document can be properly
        rendered in the API response.

        This can occur when fields are added to the document mapping but have
        not yet been indexed in the document because a document reindex is
        required.
        """

        with self.captureOnCommitCallbacks(execute=True):
            de_no_cites = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court_api,
                    date_reargued=None,
                    source=Docket.RECAP_AND_SCRAPER,
                ),
                description="",
            )

        rd_no_cites = RECAPDocumentFactory(
            docket_entry=de_no_cites,
            description="latest null rd",
            pacer_doc_id="",
        )

        doc = ESRECAPDocument().prepare(rd_no_cites)
        doc_id = ES_CHILD_ID(rd_no_cites.pk).OPINION
        es_args = {"_routing": de_no_cites.docket.pk, "meta": {"id": doc_id}}
        doc.pop("cites")
        ESRECAPDocument(**es_args, **doc).save(
            skip_empty=False,
            return_doc_meta=True,
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
        )
        search_params = {
            "type": SEARCH_TYPES.RECAP_DOCUMENT,
            "q": f"id:{rd_no_cites.pk}",
            "order_by": "score desc",
        }
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}),
            search_params,
        )
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["results"][0]["cites"], [])

    def test_handle_missing_documents_merging_values_from_db(self) -> None:
        """Confirm that we can gracefully handle documents returned by ES on a
        page that have been removed from the DB.
        """

        with self.captureOnCommitCallbacks(execute=True):
            docket_entry = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court_api,
                    source=Docket.RECAP_AND_SCRAPER,
                ),
                description="",
            )
            rd = RECAPDocumentFactory(
                docket_entry=docket_entry,
                pacer_doc_id="rd_to_delete",
                plain_text="Lorem ipsum",
            )

        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"id:{rd.pk}",
            "order_by": "score desc",
        }

        with mock.patch(
            "cl.search.api_utils.merge_unavailable_fields_on_parent_document",
            side_effect=self.mock_merge_unavailable_fields_on_parent_document,
        ):
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}),
                search_params,
            )
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(
            r.data["results"][0]["recap_documents"][0]["snippet"], ""
        )

        docket_entry.docket.delete()

    def test_dates_sorting_function_score_for_rd_type(self) -> None:
        """Test if the function score used for the dateFiled and entry_date_filed
        sorting in the V4 of the RECAP Search API works as expected for the RD type.
        """

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            latest_null_date_filed = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court_api,
                    date_reargued=None,
                    source=Docket.RECAP_AND_SCRAPER,
                ),
                description="",
            )
            rd_null_date_filed = RECAPDocumentFactory(
                docket_entry=latest_null_date_filed,
                description="latest null rd",
                pacer_doc_id="",
            )

        search_params = {
            "q": "SUBPOENAS SERVED",
            "order_by": "dateFiled desc",
            "highlight": False,
            "type": SEARCH_TYPES.RECAP_DOCUMENT,
        }

        params_match_all = search_params.copy()
        del params_match_all["q"]

        test_cases = [
            # dateFiled test cases for RECAP_DOCUMENT type. RDs are sorted
            # based on their docket dateFiled.
            {
                "name": "Query string, order by dateFiled desc",
                "order_by": "dateFiled desc",
                "search_params": search_params,
                "expected_results": 3,
                "expected_order": [
                    self.rd_2.pk,  # 2016/08/16
                    self.rd_att.pk,  # 2015/08/16 pk 2
                    self.rd.pk,  # 2015/08/16 pk 1
                ],
            },
            {
                "name": "Query string, order by dateFiled asc",
                "order_by": "dateFiled asc",
                "search_params": search_params,
                "expected_results": 3,
                "expected_order": [
                    self.rd_att.pk,  # 2015/08/16 pk 2
                    self.rd.pk,  # 2015/08/16 pk 1
                    self.rd_2.pk,  # 2016/08/16
                ],
            },
            {
                "name": "Match all query, order by dateFiled desc",
                "order_by": "dateFiled desc",
                "search_params": params_match_all,
                "expected_results": 6,
                "expected_order": [
                    self.rd_2.pk,  # 2016/08/16
                    self.rd_api.pk,  # 2016/04/16
                    self.rd_att.pk,  # 2015/08/16 pk 2
                    self.rd.pk,  # 2015/08/16 pk 1
                    rd_null_date_filed.pk,  # None pk 4
                    self.rd_empty_fields_api.pk,  # None pk 3
                ],
            },
            {
                "name": "Match all query, order by dateFiled asc",
                "order_by": "dateFiled asc",
                "search_params": params_match_all,
                "expected_results": 6,
                "expected_order": [
                    self.rd_att.pk,  # 2015/08/16 pk 2
                    self.rd.pk,  # 2015/08/16 pk 1
                    self.rd_api.pk,  # 2016/04/16
                    self.rd_2.pk,  # 2016/08/16
                    rd_null_date_filed.pk,  # None pk 4
                    self.rd_empty_fields_api.pk,  # None pk 3
                ],
            },
            # entry_date_filed test cases for RECAP_DOCUMENT type. RDs are
            # sorted based on their entry_date_filed.
            {
                "name": "Query string, order by entry_date_filed desc",
                "order_by": "entry_date_filed desc",
                "search_params": search_params,
                "expected_results": 3,
                "expected_order": [
                    self.rd_att.pk,  # 2015/08/19 pk 2
                    self.rd.pk,  # 2015/08/19 pk 1
                    self.rd_2.pk,  # 2014/07/19
                ],
            },
            {
                "name": "Query string, order by entry_date_filed asc",
                "order_by": "entry_date_filed asc",
                "search_params": search_params,
                "expected_results": 3,
                "expected_order": [
                    self.rd_2.pk,  # 2014/07/19
                    self.rd_att.pk,  # 2015/08/19 pk 2
                    self.rd.pk,  # 2015/08/19 pk 1
                ],
            },
            {
                "name": "Match all query, order by entry_date_filed desc",
                "order_by": "entry_date_filed desc",
                "search_params": params_match_all,
                "expected_results": 6,
                "expected_order": [
                    self.rd_api.pk,  # 2020/08/19
                    self.rd_att.pk,  # 2015/08/19 pk 2
                    self.rd.pk,  # 2015/08/19 pk 1
                    self.rd_2.pk,  # 2014/07/19
                    rd_null_date_filed.pk,  # None pk 4
                    self.rd_empty_fields_api.pk,  # None pk 3
                ],
            },
            {
                "name": "Match all query, order by entry_date_filed asc",
                "order_by": "entry_date_filed asc",
                "search_params": params_match_all,
                "expected_results": 6,
                "expected_order": [
                    self.rd_2.pk,  # 2014/07/19
                    self.rd_att.pk,  # 2015/08/19 pk 2
                    self.rd.pk,  # 2015/08/19 pk 1
                    self.rd_api.pk,  # 2020/08/19
                    rd_null_date_filed.pk,  # None pk 4
                    self.rd_empty_fields_api.pk,  # None pk 3
                ],
            },
        ]
        for test in test_cases:
            test["search_params"]["order_by"] = test["order_by"]
            self._test_results_ordering(test, "id")

        with self.captureOnCommitCallbacks(execute=True):
            latest_null_date_filed.docket.delete()

    @override_settings(SEARCH_API_PAGE_SIZE=4)
    def test_recap_results_cursor_api_pagination_rd(self) -> None:
        """Test cursor pagination for V4 RECAP Search API."""

        created_dockets = []
        dockets_to_create = 10
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            for _ in range(dockets_to_create):
                docket_entry = DocketEntryWithParentsFactory(
                    docket__source=Docket.RECAP,
                )
                RECAPDocumentFactory(
                    docket_entry=docket_entry,
                )
                created_dockets.append(docket_entry.docket)

        total_rds = RECAPDocument.objects.all().count()
        search_params = {
            "type": SEARCH_TYPES.RECAP_DOCUMENT,
            "order_by": "score desc",
            "highlight": False,
        }
        tests = [
            {
                "results": 4,
                "count_exact": total_rds,
                "next": True,
                "previous": False,
            },
            {
                "results": 4,
                "count_exact": total_rds,
                "next": True,
                "previous": True,
            },
            {
                "results": 4,
                "count_exact": total_rds,
                "next": True,
                "previous": True,
            },
            {
                "results": 3,
                "count_exact": total_rds,
                "next": False,
                "previous": True,
            },
        ]
        order_types = [
            "score desc",
            "dateFiled desc",
            "dateFiled asc",
            "entry_date_filed asc",
            "entry_date_filed desc",
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
                            all_document_ids.append(result["id"])
                            ids_in_page.add(result["id"])
                        ids_per_page.append(ids_in_page)

                # Confirm all the documents were shown when paginating forwards.
                self.assertEqual(
                    len(all_document_ids),
                    total_rds,
                    msg="Wrong number of dockets.",
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
                        _, previous_page, current_page = (
                            self._test_page_variables(
                                r, test, current_page, search_params["type"]
                            )
                        )
                        ids_in_page_got = set()
                        for result in r.data["results"]:
                            all_ids_prev.append(result["id"])
                            ids_in_page_got.add(result["id"])
                        current_page_ids_prev = ids_per_page.pop()
                        # Check if IDs obtained with forward pagination match
                        # the IDs obtained when paginating backwards.
                        self.assertEqual(
                            current_page_ids_prev,
                            ids_in_page_got,
                            msg="Wrong dockets.",
                        )

                # Confirm all the documents were shown when paginating backwards.
                self.assertEqual(
                    len(all_ids_prev),
                    total_rds,
                    msg="Wrong number of dockets.",
                )

        with self.captureOnCommitCallbacks(execute=True):
            # Remove Docket objects to avoid affecting other tests.
            for created_docket in created_dockets:
                created_docket.delete()

    def test_invalid_pagination_cursor(self) -> None:
        """Test to confirm that an invalid cursor error message is sent when
        an invalid cursor or incompatible search type to the cursor is
        requested in the V4 RECAP Search API."""

        search_params = {
            "type": SEARCH_TYPES.RECAP,
            "order_by": "score desc",
            "highlight": False,
            "cursor": "x-invalid_cursor-y",
        }
        total_dockets = Docket.objects.all().count()
        # Invalid cursor string.
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}), search_params
        )
        self.assertEqual(r.data["detail"], "Invalid cursor")

        # If a cursor is generated for an initial search type and then the search
        # type is changed without restarting the whole request, the cursor
        # will be incompatible with the new search type. Raise an Invalid Cursor
        # Error.
        del search_params["cursor"]
        with override_settings(SEARCH_API_PAGE_SIZE=total_dockets - 1):
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            next = r.data["next"].replace(
                "type=r", f"type={SEARCH_TYPES.DOCKETS}"
            )
            r = self.client.get(next)
            self.assertEqual(r.data["detail"], "Invalid cursor")


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
                    source=Docket.RECAP,
                ),
                date_filed=None,
                description="MOTION for Leave to File Document attachment",
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
        xml_tree = self.assert_es_feed_content(
            node_tests, response, namespaces
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
        self.assert_es_feed_content(node_tests, response, namespaces)

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

        # Parent Filter + Child Filter + Query string + Parties
        params = {
            "type": SEARCH_TYPES.RECAP,
            "court": self.court.pk,
            "document_number": 1,
            "q": "Document attachment",
            "party_name": "Defendant Jane Roe",
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
            ("//atom:entry", 1),
            ("//atom:entry/atom:title", 1),
            ("//atom:entry/atom:link", 1),
            ("//atom:entry/atom:published", 1),
            ("//atom:entry/atom:author/atom:name", 1),
            ("//atom:entry/atom:id", 1),
            ("//atom:entry/atom:summary", 1),
        )
        self.assert_es_feed_content(node_tests, response, namespaces)

        # Only party filters. Return all the RECAPDocuments where parent dockets
        # match the party filters.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "party_name": "Defendant Jane Roe",
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
        self.assert_es_feed_content(node_tests, response, namespaces)

    def test_cleanup_control_characters_for_xml_rendering(self) -> None:
        """Can we remove control characters in the plain_text for a proper XML
        rendering?
        """
        with mock.patch(
            "cl.search.documents.escape",
            return_value="Lorem ipsum control chars \x07\x08\x0B.",
        ), self.captureOnCommitCallbacks(execute=True):
            de_1 = DocketEntryWithParentsFactory(
                docket=DocketFactory(
                    court=self.court,
                    case_name="Lorem Ipsum",
                    date_filed=datetime.date(2020, 5, 20),
                    source=Docket.RECAP,
                ),
                date_filed=datetime.date(2020, 5, 20),
                description="MOTION for Leave to File Document attachment",
            )
            RECAPDocumentFactory(
                docket_entry=de_1,
                description="Control chars test",
                document_number="1",
                is_available=True,
                plain_text="Lorem ipsum control chars \x07\x08\x0B.",
            )

        params = {
            "q": "Lorem ipsum control chars",
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
        entry_summary = "//atom:entry/atom:summary"

        # Confirm the summary is properly rendered without control chars.
        # And without highlighting
        expected_summary = "Lorem ipsum control chars ."
        actual_summary = xml_tree.xpath(entry_summary, namespaces=namespaces)[
            0
        ].text
        self.assertIn(expected_summary, actual_summary)
        with self.captureOnCommitCallbacks(execute=True):
            de_1.delete()

    def test_catch_es_errors(self) -> None:
        """Can we catch es errors and just render an empy feed?"""

        # Bad syntax error.
        params = {
            "q": "Leave /:",
            "type": SEARCH_TYPES.RECAP,
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
            "type": SEARCH_TYPES.RECAP,
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


class IndexDocketRECAPDocumentsCommandTest(
    ESIndexTestCase, TransactionTestCase
):
    """cl_index_parent_and_child_docs command tests for Elasticsearch"""

    def setUp(self):
        self.rebuild_index("search.Docket")
        self.court = CourtFactory(id="canb", jurisdiction="FB")
        # Non-recap Docket
        DocketFactory(
            court=self.court,
            date_filed=datetime.date(2016, 8, 16),
            date_argued=datetime.date(2012, 6, 23),
            source=Docket.HARVARD,
        )
        self.de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                date_filed=datetime.date(2015, 8, 16),
                docket_number="1:21-bk-1234",
                nature_of_suit="440",
                source=Docket.RECAP,
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
                source=Docket.RECAP,
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

        self.r = get_redis_interface("CACHE")
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
            source=Docket.RECAP,
        )
        BankruptcyInformationFactory(docket=d_1, chapter="7")

        d_2 = DocketFactory(
            court=court,
            date_filed=datetime.date(2020, 8, 16),
            source=Docket.RECAP,
        )
        BankruptcyInformationFactory(docket=d_2, chapter="7")

        d_3 = DocketFactory(
            court=court,
            date_filed=datetime.date(2021, 8, 16),
            source=Docket.RECAP,
        )
        BankruptcyInformationFactory(docket=d_3, chapter="7")

        d_4 = DocketFactory(
            court=court,
            date_filed=datetime.date(2021, 8, 16),
            source=Docket.RECAP,
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

    def test_index_only_child_docs_when_parent_docs_are_missed(self):
        """Confirm that the command can index only RECAP Documents when the
        parent Docket is missed. Afterward, when the Docket is indexed, the
        RDs are properly linked to the Docket.
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

        # Dockets are not indexed yet.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 0, msg="Wrong number of Dockets returned.")

        # RECAPDocuments should be indexed.
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

        # Call cl_index_parent_and_child_docs command for RECAPDocuments.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            document_type="parent",
        )

        # Confirm parent-child relation.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": f"docket_id:{self.de.docket.pk}",
        }
        r = self.client.get("/", params)
        tree = html.fromstring(r.content.decode())
        article = tree.xpath("//article")
        parent_count = len(article)
        self.assertEqual(1, parent_count)
        child_count = len(article[0].xpath(".//h4"))
        self.assertEqual(2, child_count)


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
        (s, child_docs_count_query, *_) = build_es_main_query(search_query, cd)
        hits, _, _, total_query_results, child_total = fetch_es_results(
            cd,
            s,
            child_docs_count_query,
            1,
        )
        self.assertEqual(
            total_query_results,
            parent_expected,
            msg="Did not get the right number of parent documents %s\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            % (field_name, parent_expected, total_query_results),
        )
        return hits.to_dict()

    def test_minute_entry_indexing(self) -> None:
        """Confirm a minute entry can be properly indexed."""

        de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(court=self.court, source=Docket.RECAP),
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
            docket=DocketFactory(court=self.court, source=Docket.RECAP),
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

        non_recap_docket = DocketFactory(
            court=self.court,
            case_name="SUBPOENAS SERVED ON",
            case_name_full="Jackson & Sons Holdings vs. Bank",
            date_filed=datetime.date(2015, 8, 16),
            date_argued=datetime.date(2013, 5, 20),
            docket_number="1:21-bk-1234",
            nature_of_suit="440",
            source=Docket.HARVARD,
        )

        docket_entry_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                case_name="SUBPOENAS SERVED ON",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:21-bk-1234",
                nature_of_suit="440",
                source=Docket.RECAP,
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
                source=Docket.HARVARD_AND_RECAP,
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

        # The non-recap docket shouldn't be indexed.
        self.assertFalse(DocketDocument.exists(id=non_recap_docket.pk))

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

        non_recap_docket = DocketFactory(
            court=self.court,
            date_filed=datetime.date(2013, 8, 16),
            date_argued=datetime.date(2010, 5, 20),
            docket_number="1:21-bk-0000",
            nature_of_suit="440",
            source=Docket.HARVARD,
        )
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
                source=Docket.COLUMBIA_AND_SCRAPER_AND_HARVARD,
                pacer_case_id="973390",
            ),
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem",
        )
        # The Docket is not indexed yet here because it doesn't belong to RECAP
        self.assertFalse(DocketDocument.exists(id=de_1.docket.pk))

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
        # After adding a RECAPDocument. The docket is automatically indexed.
        self.assertTrue(DocketDocument.exists(id=docket_pk))
        self.assertTrue(DocketDocument.exists(id=ES_CHILD_ID(rd_pk).RECAP))

        # The non-recap Docket is not indexed.
        self.assertFalse(DocketDocument.exists(id=non_recap_docket.pk))

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
        self.assertEqual(de_1.docket.date_created, docket_doc.date_created)
        self.assertEqual(de_1.docket.pacer_case_id, docket_doc.pacer_case_id)

        # Confirm assigned_to and referred_to are properly updated in Docket.
        judge = PersonFactory.create(name_first="Thalassa", name_last="Miller")
        judge_2 = PersonFactory.create(
            name_first="Persephone", name_last="Sinclair"
        )

        # Update docket fields:
        de_1.docket.source = Docket.RECAP
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
        de_1.docket.pacer_case_id = "288700"

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
        self.assertEqual(de_1.docket.pacer_case_id, docket_doc.pacer_case_id)
        self.assertIn(judge.name_full, docket_doc.assignedTo)
        self.assertIn(judge_2.name_full, docket_doc.referredTo)
        self.assertEqual(judge.pk, docket_doc.assigned_to_id)
        self.assertEqual(judge_2.pk, docket_doc.referred_to_id)

        # Track source changes in a non-recap Docket.
        # First update to a different non-recap source.
        non_recap_docket.source = Docket.COLUMBIA
        non_recap_docket.save()
        # The non-recap Docket shouldn't be indexed yet.
        self.assertFalse(DocketDocument.exists(id=non_recap_docket.pk))

        # Update it to a RECAP Source.
        non_recap_docket.source = Docket.COLUMBIA_AND_RECAP
        non_recap_docket.save()
        # The non-recap Docket is now indexed.
        self.assertTrue(DocketDocument.exists(id=non_recap_docket.pk))

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
        self.assertEqual(rd_1.date_created, rd_doc.date_created)

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
                source=Docket.RECAP,
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
        de.docket.pacer_case_id = "3456783"
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
            self._compare_response_child_value(
                response, 0, i, de.docket.pacer_case_id, "pacer_case_id"
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

        # Avoid calling es_save_document for a non-recap docket.
        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            non_recap_docket = DocketFactory(
                court=self.court,
                pacer_case_id="asdf0",
                docket_number="12-cv-02354",
                case_name="Vargas v. Wilkins",
                source=Docket.COLUMBIA,
            )

        # No es_save_document task should be called on a non-recap docket creation
        self.reset_and_assert_task_count(expected=0)
        self.assertFalse(DocketDocument.exists(id=non_recap_docket.pk))

        # Update a non-recap docket to a different non-recap source
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            non_recap_docket.source = Docket.HARVARD
            non_recap_docket.save()
        # No update_es_document task should be called on a non-recap source change
        self.reset_and_assert_task_count(expected=0)
        self.assertFalse(DocketDocument.exists(id=non_recap_docket.pk))

        # Update a non-recap docket to a recap source
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            non_recap_docket.source = Docket.RECAP_AND_IDB_AND_HARVARD
            non_recap_docket.save()
        # update_es_document task should be called 1 time
        self.reset_and_assert_task_count(expected=1)
        # The docket should now be indexed.
        self.assertTrue(DocketDocument.exists(id=non_recap_docket.pk))

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
                source=Docket.RECAP,
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
                source=Docket.RECAP,
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
            source=Docket.RECAP,
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
        docket_2 = DocketFactory(
            court=self.court, docket_number="21-0000", source=Docket.RECAP
        )
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
            OpinionsCitedByRECAPDocument.objects.bulk_create(
                [
                    OpinionsCitedByRECAPDocument(
                        citing_document=rd_1,
                        cited_opinion=opinion,
                        depth=1,
                    )
                ]
            )
            # No update_es_document task should be called on bulk creation or update
            self.reset_and_assert_task_count(expected=0)

        # Update changes in ES using index_related_cites_fields
        index_related_cites_fields.delay(
            OpinionsCitedByRECAPDocument.__name__, rd_1.pk
        )

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

        opinion = OpinionWithParentsFactory()
        opinion_2 = OpinionWithParentsFactory()
        # Update cites to RECAPDocument.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
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
            OpinionsCitedByRECAPDocument.objects.bulk_create(
                [o_cited, o_cited_2]
            )

        self.reset_and_assert_task_count(expected=0)
        # Update changes in ES using index_related_cites_fields
        index_related_cites_fields.delay(
            OpinionsCitedByRECAPDocument.__name__, rd_1.pk
        )
        r_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertIn(opinion.pk, r_doc.cites)
        self.assertIn(opinion_2.pk, r_doc.cites)

        docket_2.delete()

    def test_search_pagination_results_limit(self) -> None:
        """Confirm that the last page in the pagination is properly computed
        based on the number of results returned by Elasticsearch.
        """
        # Test pagination requests.
        search_params = {
            "type": SEARCH_TYPES.RECAP,
        }

        results_per_page = settings.RECAP_SEARCH_PAGE_SIZE
        # 100 results, 10 pages.
        total_results = 100
        with mock.patch(
            "cl.search.views.fetch_es_results",
            side_effect=lambda *x: (
                [],
                1,
                False,
                total_results,
                1000,
            ),
        ):
            r = self.client.get(
                reverse("show_results"),
                search_params,
            )
        expected_page = math.ceil(total_results / results_per_page)
        self.assertIn("100 Results", r.content.decode())
        self.assertIn(f"1 of {expected_page:,}", r.content.decode())

        # 101 results, 11 pages.
        total_results = 101
        with mock.patch(
            "cl.search.views.fetch_es_results",
            side_effect=lambda *x: (
                [],
                1,
                False,
                total_results,
                1000,
            ),
        ):
            r = self.client.get(
                reverse("show_results"),
                search_params,
            )
        expected_page = math.ceil(total_results / results_per_page)
        self.assertIn("101 Results", r.content.decode())
        self.assertIn(f"1 of {expected_page:,}", r.content.decode())

        # 20,000 results, 2,000 pages.
        total_results = 20_000
        with mock.patch(
            "cl.search.views.fetch_es_results",
            side_effect=lambda *x: (
                [],
                1,
                False,
                total_results,
                1000,
            ),
        ):
            r = self.client.get(
                reverse("show_results"),
                search_params,
            )
        expected_page = math.ceil(total_results / results_per_page)
        self.assertIn("20,000 Results", r.content.decode())
        self.assertIn(f"1 of {expected_page:,}", r.content.decode())

    def test_remove_control_chars_on_plain_text_indexing(self) -> None:
        """Confirm control chars are removed at indexing time."""

        de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(court=self.court, source=Docket.RECAP),
            date_filed=datetime.date(2024, 8, 19),
            entry_number=1,
        )
        rd_1 = RECAPDocumentFactory(
            docket_entry=de_1,
            description="Leave to File",
            document_number="1",
            plain_text="Lorem ipsum control chars \x07\x08\x0B.",
        )

        r_doc = ESRECAPDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertEqual(r_doc.plain_text, "Lorem ipsum control chars .")
        de_1.docket.delete()

    def test_prepare_parties(self) -> None:
        """Confirm prepare_parties return the expected values."""

        d = docket = DocketFactory(court=self.court, source=Docket.RECAP)
        firm = AttorneyOrganizationFactory(
            lookup_key="00kingofprussiaroadradnorkesslertopazmeltzercheck1908",
            name="Law Firm LLP",
        )
        attorney = AttorneyFactory(
            name="Emily Green",
            organizations=[firm],
            docket=d,
        )
        firm_2 = AttorneyOrganizationFactory(
            lookup_key="280kingofprussiaroadradnorkesslertopazmeltzercheck000",
            name="Law Firm LLP 2",
        )
        firm_2_1 = AttorneyOrganizationFactory(
            lookup_key="280kingofprussiaroadradnorkesslertopazmeltzercheck111",
            name="Law Firm LLP 2_1",
        )
        attorney_2 = AttorneyFactory(
            name="Atty Lorem",
            organizations=[firm_2, firm_2_1],
            docket=d,
        )
        party_type = PartyTypeFactory.create(
            party=PartyFactory(
                name="Mary Williams Corp.",
                docket=d,
                attorneys=[attorney, attorney_2],
            ),
            docket=d,
        )

        firm_1_2 = AttorneyOrganizationFactory(
            lookup_key="280kingofprussiaroadradnorkesslertopazmeltzercheck1908",
            name="Law Firm LLP",
        )
        attorney_1_2 = AttorneyFactory(
            name="Emily Green",
            organizations=[firm_1_2],
            docket=d,
        )
        party_type_1_2 = PartyTypeFactory.create(
            party=PartyFactory(
                name="Mary Williams Corp.",
                docket=d,
                attorneys=[attorney_1_2],
            ),
            docket=d,
        )

        parties_prepared = DocketDocument().prepare_parties(docket)
        self.assertEqual(
            parties_prepared["party_id"],
            {party_type.party.pk, party_type_1_2.party.pk},
        )
        self.assertEqual(
            parties_prepared["party"],
            {party_type.party.name, party_type_1_2.party.name},
        )
        self.assertEqual(
            parties_prepared["attorney_id"],
            {attorney.pk, attorney_2.pk, attorney_1_2.pk},
        )
        self.assertEqual(
            parties_prepared["attorney"],
            {attorney.name, attorney_2.name, attorney_1_2.name},
        )
        self.assertEqual(
            parties_prepared["firm_id"],
            {firm.pk, firm_2.pk, firm_2_1.pk, firm_1_2.pk},
        )
        self.assertEqual(
            parties_prepared["firm"],
            {firm.name, firm_2.name, firm_2_1.name, firm_1_2.name},
        )


class RECAPHistoryTablesIndexingTest(
    RECAPSearchTestCase, ESIndexTestCase, TestCase
):
    """RECAP Document indexing from history tables events."""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")
        super().setUpTestData()
        # Non-RECAP Docket.
        cls.non_recap_docket = DocketFactory(
            court=cls.court,
            date_filed=datetime.date(2010, 8, 16),
            docket_number="45-bk-2632",
            nature_of_suit="440",
            source=Docket.HARVARD,
        )

    def setUp(self):
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )
        self.r = get_redis_interface("CACHE")
        keys = self.r.keys(compose_redis_key(SEARCH_TYPES.RECAP))
        if keys:
            self.r.delete(*keys)

    def test_docket_history_table_indexing(self) -> None:
        """Confirm that dockets and their child documents are properly updated
        based on events from their history tables.
        """

        # Trigger docket events based on changes.
        docket_instance = self.de.docket
        docket_instance.case_name = "SUBPOENAS SERVED LOREM"
        docket_instance.docket_number = "1:21-bk-0000"
        docket_instance.save()

        docket_instance_2 = self.de_1.docket
        docket_instance_2.cause = "Test cause"
        docket_instance_2.save()

        # Data remains the same after update.
        docket_doc = DocketDocument.get(id=docket_instance.pk)
        self.assertEqual(docket_doc.caseName, "SUBPOENAS SERVED ON")
        self.assertEqual(docket_doc.docketNumber, "1:21-bk-1234")
        rd_1_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd.pk).RECAP)
        self.assertEqual(rd_1_doc.caseName, "SUBPOENAS SERVED ON")
        self.assertEqual(rd_1_doc.docketNumber, "1:21-bk-1234")
        rd_2_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd_att.pk).RECAP)
        self.assertEqual(rd_2_doc.caseName, "SUBPOENAS SERVED ON")
        self.assertEqual(rd_2_doc.docketNumber, "1:21-bk-1234")

        docket_doc_2 = DocketDocument.get(id=docket_instance_2.pk)
        self.assertEqual(docket_doc_2.cause, "")
        rd_3_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd_2.pk).RECAP)
        self.assertEqual(rd_3_doc.cause, "")

        with self.captureOnCommitCallbacks(execute=True):
            # Trigger a change in a non-recap Docket.
            self.non_recap_docket.docket_number = "12-45324"
            self.non_recap_docket.save()

        # The docket shouldn't be indexed.
        self.assertFalse(DocketDocument.exists(id=self.non_recap_docket.pk))

        # Call the indexing command for "docket" to update documents based on
        # events within the specified date range.
        start_date = datetime.datetime.now() - datetime.timedelta(days=2)
        end_date = datetime.datetime.now() + datetime.timedelta(days=2)
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            testing_mode=True,
            update_from_event_tables=EventTable.DOCKET.value,
            start_date=start_date.date().isoformat(),
            end_date=end_date.date().isoformat(),
        )

        # The non-recap docket shouldn't be indexed.
        self.assertFalse(DocketDocument.exists(id=self.non_recap_docket.pk))

        # New data should now be updated in the docket and its child documents
        docket_doc = DocketDocument.get(id=docket_instance.pk)
        self.assertEqual(docket_doc.caseName, "SUBPOENAS SERVED LOREM")
        self.assertEqual(docket_doc.docketNumber, "1:21-bk-0000")

        rd_1_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd.pk).RECAP)
        self.assertEqual(rd_1_doc.caseName, "SUBPOENAS SERVED LOREM")
        self.assertEqual(rd_1_doc.docketNumber, "1:21-bk-0000")
        rd_2_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd_att.pk).RECAP)
        self.assertEqual(rd_2_doc.caseName, "SUBPOENAS SERVED LOREM")
        self.assertEqual(rd_2_doc.docketNumber, "1:21-bk-0000")

        docket_doc_2 = DocketDocument.get(id=docket_instance_2.pk)
        self.assertEqual(docket_doc_2.cause, "Test cause")

        rd_3_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd_2.pk).RECAP)
        self.assertEqual(rd_3_doc.cause, "Test cause")

        # Deletion of docket.
        docket_instance_id = docket_instance.pk
        with mock.patch(
            "cl.lib.es_signal_processor.remove_document_from_es_index"
        ):
            docket_instance.delete()
            docket_instance_2.delete()

        # Documents should still exist in the index at this stage.
        docket_doc_exists = DocketDocument.exists(id=docket_instance_id)
        self.assertTrue(docket_doc_exists)
        rd_1_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(self.rd.pk).RECAP
        )
        rd_2_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(self.rd_att.pk).RECAP
        )
        self.assertTrue(rd_1_doc_exists)
        self.assertTrue(rd_2_doc_exists)

        # Call the indexing command for "docket" to update documents based on
        # events within the specified date range.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            testing_mode=True,
            update_from_event_tables=EventTable.DOCKET.value,
            start_date=start_date.date().isoformat(),
            end_date=end_date.date().isoformat(),
        )
        # The docket should be removed from the index.
        docket_doc_exists = DocketDocument.exists(id=docket_instance_id)
        self.assertFalse(docket_doc_exists)

        # RECAPDocuments should be also removed from the index.
        rd_1_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(self.rd.pk).RECAP
        )
        rd_2_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(self.rd_att.pk).RECAP
        )
        self.assertFalse(rd_1_doc_exists)
        self.assertFalse(rd_2_doc_exists)

        # Clean up last_pk indexed.
        keys = self.r.keys(
            compose_redis_key(SEARCH_TYPES.RECAP, EventTable.DOCKET)
        )
        if keys:
            self.r.delete(*keys)

    def test_docket_entry_history_table_indexing(self) -> None:
        """Confirm that docket entries changes are properly updated into
        ESRECAPDocuments based on events from their history tables."""

        # Trigger docket entry events based on changes.
        de_instance = self.de
        de_instance.description = "Hearing for Leave to File Amicus"
        de_instance.entry_number = 10
        de_instance.save()

        # Data remains the same after update.
        rd_1_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd.pk).RECAP)
        rd_2_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd_att.pk).RECAP)
        self.assertEqual(
            rd_1_doc.description,
            "MOTION for Leave to File Amicus Curiae Lorem",
        )
        self.assertEqual(rd_1_doc.entry_number, 1)
        self.assertEqual(
            rd_2_doc.description,
            "MOTION for Leave to File Amicus Curiae Lorem",
        )
        self.assertEqual(rd_2_doc.entry_number, 1)

        # Call the indexing command for "de" to update documents based on
        # events within the specified date range.
        start_date = datetime.datetime.now() - datetime.timedelta(days=2)
        end_date = datetime.datetime.now() + datetime.timedelta(days=2)
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            testing_mode=True,
            update_from_event_tables=EventTable.DOCKET_ENTRY.value,
            start_date=start_date.date().isoformat(),
            end_date=end_date.date().isoformat(),
        )
        # New data should now be updated in the RECAP Documents.
        rd_1_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd.pk).RECAP)
        rd_2_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd_att.pk).RECAP)
        self.assertEqual(
            rd_1_doc.description, "Hearing for Leave to File Amicus"
        )
        self.assertEqual(rd_1_doc.entry_number, 10)
        self.assertEqual(
            rd_2_doc.description, "Hearing for Leave to File Amicus"
        )
        self.assertEqual(rd_2_doc.entry_number, 10)

        # Deletion of docket entry.
        with mock.patch(
            "cl.lib.es_signal_processor.remove_document_from_es_index"
        ):
            de_instance.delete()

        # Documents should still exist in the index at this stage.
        rd_1_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(self.rd.pk).RECAP
        )
        rd_2_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(self.rd_att.pk).RECAP
        )
        self.assertTrue(rd_1_doc_exists)
        self.assertTrue(rd_2_doc_exists)
        # Call the indexing command for "de" to update documents based on
        # events within the specified date range.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            testing_mode=True,
            update_from_event_tables=EventTable.DOCKET_ENTRY.value,
            start_date=start_date.date().isoformat(),
            end_date=end_date.date().isoformat(),
        )
        # RECAPDocuments should be from the index.
        rd_1_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(self.rd.pk).RECAP
        )
        rd_2_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(self.rd_att.pk).RECAP
        )
        self.assertFalse(rd_1_doc_exists)
        self.assertFalse(rd_2_doc_exists)

        # Clean up last_pk indexed.
        keys = self.r.keys(
            compose_redis_key(SEARCH_TYPES.RECAP, EventTable.DOCKET_ENTRY)
        )
        if keys:
            self.r.delete(*keys)

    def test_recap_history_table_indexing(self) -> None:
        """Confirm that RECAPDocument changes are properly updated into
        ESRECAPDocuments based on events from their history tables."""

        # Trigger RECAPDocument events based on changes.
        rd_instance = self.rd
        rd_instance.description = "Leave to File Amicus"
        rd_instance.document_number = "5"
        rd_instance.save()

        rd_instance_2 = self.rd_att
        rd_instance_2.description = "Leave Attachment"
        rd_instance_2.plain_text = "Lorem ipsum attachment text"
        rd_instance_2.save()

        # Data remains the same after update.
        rd_1_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd.pk).RECAP)
        self.assertEqual(
            rd_1_doc.short_description,
            "Leave to File",
        )
        self.assertEqual(rd_1_doc.document_number, 1)

        rd_2_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd_att.pk).RECAP)
        self.assertEqual(
            rd_2_doc.short_description,
            "Document attachment",
        )
        self.assertEqual(rd_2_doc.plain_text, "")

        # Call the indexing command for "rd" to update documents based on
        # events within the specified date range.
        start_date = datetime.datetime.now() - datetime.timedelta(days=2)
        end_date = datetime.datetime.now() + datetime.timedelta(days=2)
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            testing_mode=True,
            update_from_event_tables=EventTable.RECAP_DOCUMENT.value,
            start_date=start_date.date().isoformat(),
            end_date=end_date.date().isoformat(),
        )
        # New data should now be updated in the RECAP Documents.
        rd_1_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd.pk).RECAP)
        self.assertEqual(rd_1_doc.short_description, "Leave to File Amicus")
        self.assertEqual(rd_1_doc.document_number, 5)
        rd_2_doc = ESRECAPDocument.get(id=ES_CHILD_ID(self.rd_att.pk).RECAP)
        self.assertEqual(rd_2_doc.short_description, "Leave Attachment")
        self.assertEqual(rd_2_doc.plain_text, "Lorem ipsum attachment text")

        rd_instance_id = rd_instance.pk
        rd_instance_2_id = rd_instance_2.pk
        # Deletion of RECAPDocument.
        with mock.patch(
            "cl.lib.es_signal_processor.remove_document_from_es_index"
        ):
            rd_instance.delete()
            rd_instance_2.delete()

        # Documents should still exist in the index at this stage.
        rd_1_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(rd_instance_id).RECAP
        )
        rd_2_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(rd_instance_2_id).RECAP
        )
        self.assertTrue(rd_1_doc_exists)
        self.assertTrue(rd_2_doc_exists)

        # Call the indexing command for "rd" to update documents based on
        # events within the specified date range.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            testing_mode=True,
            update_from_event_tables=EventTable.RECAP_DOCUMENT.value,
            start_date=start_date.date().isoformat(),
            end_date=end_date.date().isoformat(),
        )

        # RECAPDocuments should be from the index.
        rd_1_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(rd_instance_id).RECAP
        )
        rd_2_doc_exists = ESRECAPDocument.exists(
            id=ES_CHILD_ID(rd_instance_2_id).RECAP
        )
        self.assertFalse(rd_1_doc_exists)
        self.assertFalse(rd_2_doc_exists)

        # Clean up last_pk indexed.
        keys = self.r.keys(
            compose_redis_key(SEARCH_TYPES.RECAP, EventTable.RECAP_DOCUMENT)
        )
        if keys:
            self.r.delete(*keys)
