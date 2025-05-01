import datetime
import io
import re
from datetime import date
from http import HTTPStatus
from unittest import mock
from urllib.parse import parse_qs

import pytz
import time_machine
from asgiref.sync import async_to_sync
from dateutil.tz import tzoffset, tzutc
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, override_settings
from django.urls import reverse
from django.utils.timezone import now
from elasticsearch_dsl import Q
from factory import RelatedFactory
from lxml import html
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from timeout_decorator import timeout_decorator
from waffle.testutils import override_flag

from cl.audio.factories import AudioFactory
from cl.lib.elasticsearch_utils import simplify_estimated_count
from cl.lib.indexing_utils import log_last_document_indexed
from cl.lib.redis_utils import get_redis_interface
from cl.lib.storage import clobbering_get_name
from cl.lib.test_helpers import AudioTestCase, CourtTestCase, PeopleTestCase
from cl.lib.utils import (
    cleanup_main_query,
    get_child_court_ids_for_parents,
    modify_court_id_queries,
)
from cl.people_db.factories import PersonFactory, PositionFactory
from cl.recap.constants import COURT_TIMEZONES
from cl.recap.factories import DocketEntriesDataFactory, DocketEntryDataFactory
from cl.recap.mergers import add_docket_entries
from cl.search.documents import (
    ES_CHILD_ID,
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    PersonDocument,
    PositionDocument,
)
from cl.search.factories import (
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionFactory,
    OpinionWithChildrenFactory,
    OpinionWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.search.management.commands.cl_index_parent_and_child_docs import (
    get_unique_oldest_history_rows,
)
from cl.search.management.commands.cl_remove_content_from_es import (
    compose_redis_key_remove_content,
)
from cl.search.management.commands.sweep_indexer import log_indexer_last_status
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Citation,
    Court,
    Docket,
    DocketEntry,
    DocketEvent,
    Opinion,
    OpinionCluster,
    RECAPDocument,
    SearchQuery,
    sort_cites,
)
from cl.search.tasks import get_es_doc_id_and_parent_id, index_dockets_in_bulk
from cl.search.types import EventTable
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.tests.utils import get_with_wait
from cl.users.factories import UserProfileWithParentsFactory


class ModelTest(TestCase):
    fixtures = ["test_court.json"]

    def setUp(self) -> None:
        self.docket = Docket.objects.create(
            case_name="Blah", court_id="test", source=Docket.DEFAULT
        )
        self.oc = OpinionCluster.objects.create(
            case_name="Blah", docket=self.docket, date_filed=date(2010, 1, 1)
        )
        self.o = Opinion.objects.create(cluster=self.oc, type="Lead Opinion")
        self.c = Citation.objects.create(
            cluster=self.oc,
            volume=22,
            reporter="U.S.",
            page=44,
            type=Citation.FEDERAL,
        )

    def tearDown(self) -> None:
        self.docket.delete()
        self.oc.delete()
        self.o.delete()
        self.c.delete()

    @mock.patch(
        "cl.lib.storage.get_name_by_incrementing",
        side_effect=clobbering_get_name,
    )
    def test_save_old_opinion(self, mock) -> None:
        """Can we save opinions older than 1900?"""
        docket = Docket(
            case_name="Blah", court_id="test", source=Docket.DEFAULT
        )
        docket.save()
        self.oc.date_filed = date(1899, 1, 1)
        self.oc.save()

        try:
            cf = ContentFile(io.BytesIO(b"blah").read())
            self.o.file_with_date = date(1899, 1, 1)
            self.o.local_path.save("file_name.pdf", cf, save=False)
            self.o.save()
        except ValueError:
            raise ValueError(
                "Unable to save a case older than 1900. Did you "
                "try to use `strftime`...again?"
            )

    def test_custom_manager_simple_filters(self) -> None:
        """Do simple queries on our custom manager work?"""
        expected_count = 1
        cluster_count = OpinionCluster.objects.filter(
            citation="22 U.S. 44"
        ).count()
        self.assertEqual(cluster_count, expected_count)

        expected_count = 0
        cluster_count = OpinionCluster.objects.filter(
            docket__case_name="Wrong case name"
        ).count()
        self.assertEqual(cluster_count, expected_count)

    def test_custom_manager_kwargs_filter(self) -> None:
        """Can we do filters that involve additional kwargs?"""
        expected_count = 1
        cluster_count = OpinionCluster.objects.filter(
            citation="22 U.S. 44", docket__case_name="Blah"
        ).count()
        self.assertEqual(cluster_count, expected_count)

    def test_custom_manager_chained_filter(self) -> None:
        """Do chained filters work?"""
        expected_count = 1
        cluster_count = (
            OpinionCluster.objects.filter(citation="22 U.S. 44")
            .exclude(
                # Note this doesn't actually exclude anything,
                # but it helps ensure chaining is working.
                docket__case_name="Not the right case name",
            )
            .count()
        )
        self.assertEqual(cluster_count, expected_count)

        cluster_count = (
            OpinionCluster.objects.filter(citation="22 U.S. 44")
            .filter(docket__case_name="Blah")
            .count()
        )
        self.assertEqual(cluster_count, expected_count)

    def test_opinions_order(self) -> None:
        """Test opinions order"""

        # Create court
        court = CourtFactory(id="nyappdiv")

        # Create cluster
        cluster = OpinionClusterFactory(
            case_name="Foo v. Bar",
            case_name_short="Foo v. Bar",
            docket=DocketFactory(
                court=court,
            ),
            date_filed=date(1978, 3, 10),
            source="U",
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )

        # Create three opinions
        op_1 = OpinionFactory(
            cluster=cluster,
            type=Opinion.LEAD,
            ordering_key=1,
        )
        op_2 = OpinionFactory(
            cluster=cluster,
            type=Opinion.CONCURRENCE,
            ordering_key=2,
        )
        op_3 = OpinionFactory(
            cluster=cluster,
            type=Opinion.DISSENT,
            ordering_key=3,
        )

        # Test that the value of the order field matches the order in which
        # they were created
        self.assertEqual(op_1.ordering_key, 1)
        self.assertEqual(op_2.ordering_key, 2)
        self.assertEqual(op_3.ordering_key, 3)

        # Can we swap orders?
        op_1.ordering_key = None
        op_1.save()

        op_2.ordering_key = 1
        op_2.save()

        op_1.ordering_key = 2
        op_1.save()

        # Can we update an opinion using an existing position?
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                op_3.ordering_key = 2
                op_3.save()

        # Validate unique cluster/order
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                op = OpinionFactory(
                    cluster=cluster,
                    type=Opinion.ADDENDUM,
                )
                op.ordering_key = 3
                op.save()

        # Can we use avoid negative positions?
        with transaction.atomic():
            with self.assertRaises(ValidationError):
                op = OpinionFactory(cluster=cluster, type=Opinion.LEAD)
                op.ordering_key = -1
                op.save()

        # Can we order the opinions from a cluster using the field?
        qs = (
            cluster.sub_opinions.all()
            .order_by("ordering_key")
            .values_list("ordering_key", flat=True)
        )
        self.assertEqual(list(qs), [1, 2, 3, None])

        # Order default value is null
        op_5 = OpinionFactory(cluster=cluster, type="Lead Opinion")
        self.assertEqual(op_5.ordering_key, None)


class DocketValidationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_appellate = CourtFactory(id="ca1", jurisdiction="F")

    def tearDown(self) -> None:
        Docket.objects.all().delete()

    def test_creating_a_recap_docket_with_blanks(self) -> None:
        """Are blank values denied?"""
        with self.assertRaises(ValidationError):
            Docket.objects.create(source=Docket.RECAP)

    def test_creating_a_recap_docket_with_pacer_case_id_blank(self) -> None:
        """Is blank pacer_case_id denied in not appellate dockets?"""
        with self.assertRaises(ValidationError):
            Docket.objects.create(
                source=Docket.RECAP, court=self.court, docket_number="12-1233"
            )

        appellate = Docket.objects.create(
            source=Docket.RECAP,
            court=self.court_appellate,
            docket_number="12-1234",
        )
        self.assertEqual(appellate.docket_number, "12-1234")

    def test_creating_a_recap_docket_with_docket_number_blank(self) -> None:
        """Is blank docket_number denied?"""
        with self.assertRaises(ValidationError):
            Docket.objects.create(
                source=Docket.RECAP, court=self.court, pacer_case_id="1234"
            )
        with self.assertRaises(ValidationError):
            Docket.objects.create(
                source=Docket.RECAP,
                court=self.court_appellate,
                pacer_case_id="1234",
            )

    def test_cannot_create_duplicate(self) -> None:
        """Do duplicate values throw an error?"""
        Docket.objects.create(
            source=Docket.RECAP,
            docket_number="asdf",
            pacer_case_id="asdf",
            court_id=self.court.pk,
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Docket.objects.create(
                    source=Docket.RECAP_AND_SCRAPER,
                    docket_number="asdf",
                    pacer_case_id="asdf",
                    court_id=self.court.pk,
                )


class RECAPDocumentValidationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.docket_entry = DocketEntryWithParentsFactory()

    def test_attachment_with_attachment_number(self):
        """Attachments with attachment_number should not raise ValidationError."""
        document = RECAPDocument.objects.create(
            docket_entry=self.docket_entry,
            document_type=RECAPDocument.ATTACHMENT,
            attachment_number=1,
        )
        self.assertIsNotNone(document.id)

    def test_attachment_without_attachment_number(self):
        """Attachments without attachment_number should raise ValidationError."""
        with self.assertRaises(ValidationError) as cm:
            RECAPDocument.objects.create(
                docket_entry=self.docket_entry,
                document_type=RECAPDocument.ATTACHMENT,
                attachment_number=None,
            )
        # Assert that the error message is as expected
        self.assertIn("attachment_number", cm.exception.message_dict)
        self.assertEqual(
            cm.exception.message_dict["attachment_number"],
            ["attachment_number cannot be null for an attachment."],
        )

    def test_main_document_with_attachment_number(self):
        """Main PACER documents with attachment_number should raise ValidationError."""
        with self.assertRaises(ValidationError) as cm:
            RECAPDocument.objects.create(
                docket_entry=self.docket_entry,
                document_type=RECAPDocument.PACER_DOCUMENT,
                attachment_number=1,
            )
        # Assert that the error message is as expected
        self.assertIn("attachment_number", cm.exception.message_dict)
        self.assertEqual(
            cm.exception.message_dict["attachment_number"],
            ["attachment_number must be null for a main PACER document."],
        )

    def test_main_document_without_attachment_number(self):
        """Main PACER documents without attachment_number should not raise ValidationError."""
        document = RECAPDocument.objects.create(
            docket_entry=self.docket_entry,
            document_type=RECAPDocument.PACER_DOCUMENT,
            attachment_number=None,
        )
        self.assertIsNotNone(document.id)


@mock.patch(
    "cl.lib.courts.get_cache_key_for_court_list",
    return_value="common_search:minimal-court-list",
)
class ESCommonSearchTest(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.OpinionCluster")
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.child_court_1 = CourtFactory(
            id="ny_child_l1_1", jurisdiction="FB", parent_court=cls.court
        )
        cls.child_court_2 = CourtFactory(
            id="ny_child_l2_1",
            jurisdiction="FB",
            parent_court=cls.child_court_1,
        )
        cls.child_court_2_2 = CourtFactory(
            id="ny_child_l2_2",
            jurisdiction="FB",
            parent_court=cls.child_court_1,
        )
        cls.child_court_3 = CourtFactory(
            id="ny_child_l3_1",
            jurisdiction="FB",
            parent_court=cls.child_court_2,
        )

        cls.court_gand = CourtFactory(id="gand", jurisdiction="FB")
        cls.child_gand_2 = CourtFactory(
            id="ga_child_l1_1", jurisdiction="FB", parent_court=cls.court_gand
        )

        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Washington.",
            case_name_full="Strickland v. Washington.",
            docket=DocketFactory(
                court=cls.court, docket_number="1:21-cv-1234"
            ),
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                html_columbia="<p>Code, &#167; 1-815 </p>",
                plain_text="",
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Lorem.",
            case_name_full="Strickland v. Lorem.",
            docket=DocketFactory(court=cls.court, docket_number="123456"),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                plain_text="Motion",
            ),
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="America vs Bank",
            case_name_full="America vs Bank",
            docket=DocketFactory(
                court=cls.child_court_1, docket_number="34-2535"
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                plain_text="Strickland Motion",
            ),
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Johnson v. National",
            case_name_full="Johnson v. National",
            docket=DocketFactory(
                court=cls.child_court_2_2, docket_number="36-2000"
            ),
            judges="Computer point",
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                plain_text="Computer point",
            ),
        )

        OpinionClusterFactoryWithChildrenAndParents(
            case_name="California v. Nevada",
            case_name_full="California v. Nevada",
            docket=DocketFactory(
                court=cls.child_gand_2, docket_number="38-1000"
            ),
            judges="Composition plant",
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                plain_text="Composition plant",
            ),
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    @staticmethod
    def get_article_count(r):
        """Get the article count in a query response"""
        return len(html.fromstring(r.content.decode()).xpath("//article"))

    def test_get_child_court_ids_for_parents(
        self, court_cache_key_mock
    ) -> None:
        def compare_strings_regardless_order(str1, str2):
            set1 = {s.strip('" ').strip() for s in str1.split("OR")}
            set2 = {s.strip('" ').strip() for s in str2.split("OR")}
            return set1 == set2

        # Get all the courts of 'canb' at all lower levels.
        parent_child_courts = get_child_court_ids_for_parents('"canb"')
        self.assertTrue(
            compare_strings_regardless_order(
                parent_child_courts,
                '"canb" OR "ny_child_l1_1" OR "ny_child_l2_1" OR "ny_child_l2_2" OR "ny_child_l3_1"',
            )
        )

        with self.assertNumQueries(0):
            # Get all the courts of ny_child_l1_1 at all lower levels.
            parent_child_courts = get_child_court_ids_for_parents(
                '"ny_child_l1_1"'
            )
            self.assertTrue(
                compare_strings_regardless_order(
                    parent_child_courts,
                    '"ny_child_l1_1" OR "ny_child_l2_1" OR "ny_child_l2_2" OR "ny_child_l3_1"',
                )
            )

            # Get all the courts of ny_child_l1_2 at all lower levels.
            parent_child_courts = get_child_court_ids_for_parents(
                '"ny_child_l2_1"'
            )
            self.assertTrue(
                compare_strings_regardless_order(
                    parent_child_courts, '"ny_child_l2_1" OR "ny_child_l3_1"'
                )
            )

            # Get all the courts of ny_child_l3_1, no child courts, retrieve itself.
            parent_child_courts = get_child_court_ids_for_parents(
                '"ny_child_l3_1"'
            )
            self.assertTrue(
                compare_strings_regardless_order(
                    parent_child_courts, '"ny_child_l3_1"'
                )
            )

            # Confirm courts are not duplicated if a parent-child court is included
            # in the query:
            parent_child_courts = get_child_court_ids_for_parents(
                '"ny_child_l1_1" OR "ny_child_l2_1"'
            )
            self.assertTrue(
                compare_strings_regardless_order(
                    parent_child_courts,
                    '"ny_child_l1_1" OR "ny_child_l2_1" OR "ny_child_l2_2" OR "ny_child_l3_1"',
                )
            )

            # Get all courts from 2 different parent courts 'canb' and 'gand'.
            parent_child_courts = get_child_court_ids_for_parents(
                '"canb" OR "gand"'
            )
            self.assertTrue(
                compare_strings_regardless_order(
                    parent_child_courts,
                    '"canb" OR "ny_child_l1_1" OR "ny_child_l2_1" OR "ny_child_l2_2" OR "ny_child_l3_1" OR "gand" OR "ga_child_l1_1"',
                )
            )

    def test_modify_court_id_queries(self, court_cache_key_mock) -> None:
        """Test parse_court_id_query method, it should properly parse a
        court_id query
        """
        tests = [
            {"input": "court_id:cabc", "output": 'court_id:("cabc")'},
            {"input": "court_id:(cabc)", "output": 'court_id:("cabc")'},
            {
                "input": "court_id:(cabc OR nysupctnewyork)",
                "output": 'court_id:("cabc" OR "nysupctnewyork")',
            },
            {
                "input": "court_id:(cabc OR nysupctnewyork OR nysd)",
                "output": 'court_id:("cabc" OR "nysd" OR "nysupctnewyork")',
            },
            {
                "input": "court_id:cabc something_else:test",
                "output": 'court_id:("cabc") something_else:test',
            },
            {
                "input": "court_id:(cabc OR nysupctnewyork) something_else",
                "output": 'court_id:("cabc" OR "nysupctnewyork") something_else',
            },
            {
                "input": "docketNumber:23-3434 OR court_id:canb something_else",
                "output": 'docketNumber:23-3434 OR court_id:("canb" OR "ny_child_l1_1" OR "ny_child_l2_1" OR "ny_child_l2_2" OR "ny_child_l3_1") something_else',
            },
            {
                "input": "docketNumber:23-3434 OR court_id:ny_child_l2_1 something_else court_id:gand",
                "output": 'docketNumber:23-3434 OR court_id:("ny_child_l2_1" OR "ny_child_l3_1") something_else court_id:("ga_child_l1_1" OR "gand")',
            },
            {
                "input": "docketNumber:23-3434 OR court_id:(ny_child_l2_1 OR gand) something_else",
                "output": 'docketNumber:23-3434 OR court_id:("ga_child_l1_1" OR "gand" OR "ny_child_l2_1" OR "ny_child_l3_1") something_else',
            },
        ]
        for test in tests:
            output_str = modify_court_id_queries(test["input"])
            self.assertEqual(output_str, test["output"])

    async def test_filter_parent_child_courts(
        self, court_cache_key_mock
    ) -> None:
        """Does filtering in a given parent court return opinions from the
        parent and its child courts?
        """

        r = await self.async_client.get(
            reverse("show_results"), {"q": "*", "court": "canb"}
        )
        actual = self.get_article_count(r)
        self.assertEqual(actual, 4)
        self.assertIn("Washington", r.content.decode())
        self.assertIn("Lorem", r.content.decode())
        self.assertIn("Bank", r.content.decode())
        self.assertIn("National", r.content.decode())

        r = await self.async_client.get(
            reverse("show_results"), {"q": "*", "court": "ny_child_l1_1"}
        )
        actual = self.get_article_count(r)
        self.assertEqual(actual, 2)
        self.assertIn("Bank", r.content.decode())
        self.assertIn("National", r.content.decode())

        r = await self.async_client.get(
            reverse("show_results"),
            {"q": "*", "court": "gand canb"},
        )
        actual = self.get_article_count(r)
        self.assertEqual(actual, 5)
        self.assertIn("Washington", r.content.decode())
        self.assertIn("Lorem", r.content.decode())
        self.assertIn("Bank", r.content.decode())
        self.assertIn("National", r.content.decode())
        self.assertIn("Nevada", r.content.decode())

    async def test_advanced_search_parent_child_courts(
        self, court_cache_key_mock
    ) -> None:
        """Does querying in a given parent court return opinions from the
        parent and its child courts?
        """
        r = await self.async_client.get(
            reverse("show_results"), {"q": "court_id:canb"}
        )
        actual = self.get_article_count(r)
        self.assertEqual(actual, 4)
        self.assertIn("Washington", r.content.decode())
        self.assertIn("Lorem", r.content.decode())
        self.assertIn("Bank", r.content.decode())
        self.assertIn("National", r.content.decode())

        r = await self.async_client.get(
            reverse("show_results"), {"q": "court_id:(canb OR gand)"}
        )
        actual = self.get_article_count(r)
        self.assertEqual(actual, 5)
        self.assertIn("Washington", r.content.decode())
        self.assertIn("Lorem", r.content.decode())
        self.assertIn("Bank", r.content.decode())
        self.assertIn("National", r.content.decode())
        self.assertIn("Nevada", r.content.decode())

        r = await self.async_client.get(
            reverse("show_results"),
            {"q": "caseName:something OR court_id:canb OR caseName:something"},
        )
        actual = self.get_article_count(r)
        self.assertEqual(actual, 4)
        self.assertIn("Washington", r.content.decode())
        self.assertIn("Lorem", r.content.decode())
        self.assertIn("Bank", r.content.decode())
        self.assertIn("National", r.content.decode())

        r = await self.async_client.get(
            reverse("show_results"),
            {
                "q": "caseName:something OR court_id:(canb) OR docketNumber:23-2345 OR court_id:gand"
            },
        )
        actual = self.get_article_count(r)
        self.assertEqual(actual, 5)
        self.assertIn("Washington", r.content.decode())
        self.assertIn("Lorem", r.content.decode())
        self.assertIn("Bank", r.content.decode())
        self.assertIn("National", r.content.decode())
        self.assertIn("Nevada", r.content.decode())

    async def test_es_bad_syntax_proximity_tokens(
        self, court_cache_key_mock
    ) -> None:
        """Can we make a suggestion for queries that use unrecognized proximity
        search?
        """

        # On string queries
        r = await self.async_client.get(
            reverse("show_results"),
            {"q": "This query contains /s proximity token"},
        )
        self.assertIn(
            "Are you attempting to perform a proximity search?",
            r.content.decode(),
        )
        self.assertNotIn("Did you mean:", r.content.decode())

        r = await self.async_client.get(
            reverse("show_results"),
            {"q": "This query contains /p proximity token"},
        )
        self.assertIn(
            "Are you attempting to perform a proximity search?",
            r.content.decode(),
        )
        self.assertNotIn("Did you mean:", r.content.decode())

        # On filters
        r = await self.async_client.get(
            reverse("show_results"),
            {"case_name": "This query contains /p proximity token"},
        )
        self.assertIn(
            "Are you attempting to perform a proximity search within a filter?",
            r.content.decode(),
        )
        r = await self.async_client.get(
            reverse("show_results"),
            {"docket_number": "12-2345 /p"},
        )
        self.assertIn(
            "Are you attempting to perform a proximity search within a filter?",
            r.content.decode(),
        )

    async def test_es_unbalanced_quotes(self, court_cache_key_mock) -> None:
        """Can we make a suggestion for queries that use include unbalanced
        quotes?
        """

        # On string queries
        r = await self.async_client.get(
            reverse("show_results"), {"q": 'Test query with "quotes'}
        )
        self.assertIn(
            "Did you forget to close one or more quotes?", r.content.decode()
        )
        self.assertIn("Did you mean:", r.content.decode())
        self.assertIn("Test query with quotes", r.content.decode())
        r = await self.async_client.get(
            reverse("show_results"), {"q": 'Test query with "quotes""'}
        )
        self.assertIn(
            "Did you forget to close one or more quotes?", r.content.decode()
        )
        self.assertIn("Did you mean:", r.content.decode())
        self.assertIn("Test query with &quot;quotes&quot;", r.content.decode())

        # On filters
        r = await self.async_client.get(
            reverse("show_results"), {"case_name": 'Test query with "quotes""'}
        )
        self.assertIn(
            "Did you forget to close one or more quotes?", r.content.decode()
        )
        self.assertNotIn("Did you mean:", r.content.decode())

    def test_handle_unbalanced_parentheses(self, court_cache_key_mock) -> None:
        """Can we make a suggestion for queries that use include unbalanced
        parentheses?
        """

        # On string queries
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "(Loretta OR (SEC) AND Jose",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertIn(
            "Did you forget to close one or more parentheses?",
            r.content.decode(),
        )
        self.assertIn("Did you mean", r.content.decode())
        self.assertIn("(Loretta OR SEC) AND Jose", r.content.decode())

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "(Loretta AND Jose",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertIn(
            "Did you forget to close one or more parentheses?",
            r.content.decode(),
        )
        self.assertIn("Did you mean", r.content.decode())
        self.assertIn("Loretta AND Jose", r.content.decode())

        # On filters
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "case_name": "(Loretta OR (SEC) AND Jose",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertIn(
            "Did you forget to close one or more parentheses?",
            r.content.decode(),
        )
        self.assertNotIn("Did you mean", r.content.decode())

    def test_round_estimated_search_counts(self, court_cache_key_mock) -> None:
        """Confirm search counts above the threshold are properly rounded"""

        tests = [
            (13, 13),  # Below ELASTICSEARCH_CARDINALITY_PRECISION threshold
            (109, 109),
            (809, 809),
            (1_074, 1_074),
            (1_768, 1_768),
            (1_881, 1_800),  # Above ELASTICSEARCH_CARDINALITY_PRECISION * 0.94
            # threshold
            (
                11_740,
                11_000,
            ),
            (367_740, 360_000),
            (7_867_740, 7_800_000),
            (95_367_740, 95_000_000),
            (436_307_740, 430_000_000),
        ]
        for test in tests:
            with self.subTest(test=test, msg="Test estimated search counts."):
                self.assertEqual(simplify_estimated_count(test[0]), test[1])

    def test_avoid_wrapping_boosted_numbers_in_quotes(
        self, court_cache_key_mock
    ) -> None:
        """Confirm that numbers in boost queries are not wrapped in quotes
        that makes the query to fail.
        """
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Jose^3",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertNotIn("encountered an error", r.content.decode())

    def test_raise_forbidden_error_on_depth_pagination(
        self, court_cache_key_mock
    ) -> None:
        """Confirm that a 403 Forbidden error is raised on depth pagination."""
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "Lorem",
            "page": 101,
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertEqual(r.status_code, HTTPStatus.FORBIDDEN)

    def test_query_cleanup_function(self, court_cache_key_mock) -> None:
        # Send string of search_query to the function and expect it
        # to be encoded properly
        q_a = (
            (
                "12-9238 happy Gilmore",
                'docketNumber:"12-9238"~1 happy Gilmore',
            ),
            ("“ping tree” leads", '"ping tree" leads'),
            ('"this is” a “test"', '"this is" a "test"'),
            ("1chicken NUGGET", '"1chicken" NUGGET'),
            (
                "We can drive her home with 1headlight",
                'We can drive her home with "1headlight"',
            ),
            # Tildes are ignored even though they have numbers?
            ('"net neutrality"~2', '"net neutrality"~2'),
            # No changes to regular queries?
            ("Look Ma, no numbers!", "Look Ma, no numbers!"),
            # Docket numbers hyphenated into phrases?
            (
                "12cv9834 Monkey Goose",
                'docketNumber:"12-cv-9834"~1 Monkey Goose',
            ),
            # Valid dates ignored?
            (
                "2020-10-31T00:00:00Z Monkey Goose",
                "2020-10-31T00:00:00Z Monkey Goose",
            ),
            # Simple range query?
            ("[1 TO 4]", '["1" TO "4"]'),
            # Dates ignored in ranges?
            (
                "[* TO 2020-10-31T00:00:00Z] Monkey Goose",
                "[* TO 2020-10-31T00:00:00Z] Monkey Goose",
            ),
            ("id:10", "id:10"),
            ("id:[* TO 5] Monkey Goose", 'id:[* TO "5"] Monkey Goose'),
            (
                "(Tempura AND 12cv3392) OR sushi",
                '(Tempura AND docketNumber:"12-cv-3392"~1) OR sushi',
            ),
            # Phrase search with numbers (w/and w/o § mark)?
            ('"18 USC 242"', '"18 USC 242"'),
            ('"18 USC §242"', '"18 USC §242"'),
            ('"this is a test" asdf', '"this is a test" asdf'),
            ('asdf "this is a test" asdf', 'asdf "this is a test" asdf'),
            (
                '"this is a test" 22cv3332',
                '"this is a test" docketNumber:"22-cv-3332"~1',
            ),
            (
                '"this is a test" ~2',
                '"this is a test"~2',
            ),
            (
                '"this is a test" ~2 and "net neutrality" ~5 and 22cv3332',
                '"this is a test"~2 and "net neutrality"~5 and docketNumber:"22-cv-3332"~1',
            ),
            (
                "Strickland % Lorem % America",
                "Strickland NOT Lorem NOT America",
            ),
            (
                "Strickland% Lorem% America",
                "Strickland% Lorem% America",
            ),
            (
                "Strickland & Motion & Lorem",
                "Strickland AND Motion AND Lorem",
            ),
            (
                "!Strick !Mot",
                "Strick* Mot*",
            ),
            (
                "!111 !444",
                '!"111" !"444"',
            ),
            (
                "b*ra*e b*rav*",
                "b?ra?e b?rav*",
            ),
            (
                "Lorem docketNumber:1:21-bk-0021 test",
                'Lorem docketNumber:"1:21-bk-0021"~1 test',
            ),
            (
                "Lorem docketNumber:1:21-bk-0021 AND docketNumber:1:21-bk-0022",
                'Lorem docketNumber:"1:21-bk-0021"~1 AND docketNumber:"1:21-bk-0022"~1',
            ),
            (
                "Lorem docketNumber:1:21:0021 test",
                'Lorem docketNumber:"1:21:0021" test',
            ),
            (
                "docketNumber:(ASBCA No. 59126)",
                'docketNumber:(ASBCA No. "59126")',
            ),
            (
                'docketNumber:"1:21-bk-0021" test',
                'docketNumber:"1:21-bk-0021" test',
            ),
            (
                "docketNumber:1:21-bk-0021-ABC test",
                'docketNumber:"1:21-bk-0021-ABC"~1 test',
            ),
            (
                "12-9238 docketNumber:1:21-bk-0021",
                'docketNumber:"12-9238"~1 docketNumber:"1:21-bk-0021"~1',
            ),
            (
                'test case_name_full:"Lorem ipsum 2" test',
                'test case_name_full:"Lorem ipsum 2" test',
            ),
            (
                'docketNumber:"docket number 2"',
                'docketNumber:"docket number 2"',
            ),
        )
        for q, a in q_a:
            print("Does {q} --> {a} ? ".format(**{"q": q, "a": a}))
            self.assertEqual(cleanup_main_query(q), a)

    def test_built_in_search_connectors(self, court_cache_key_mock) -> None:
        """Verify that built in ES search connectors return the expected results."""

        tests = [
            {
                "label": "NOT query",
                "search_params": {
                    "q": "Strickland   NOT  Lorem   NOT   America",
                },
                "expected_count": 1,
                "expected_in_content": ["1:21-cv-1234"],
            },
            {
                "label": "AND connector test",
                "search_params": {
                    "q": "Strickland  AND  Motion  AND  Lorem",
                },
                "expected_count": 1,
                "expected_in_content": ["123456"],
            },
            {
                "label": "Zero or more chars wildcard *",
                "search_params": {
                    "q": "Comp*",
                },
                "expected_count": 2,
                "expected_in_content": ["36-2000", "38-1000"],
            },
            {
                "label": "Universal Character ?",
                "search_params": {
                    "q": "p??nt",
                },
                "expected_count": 2,
                "expected_in_content": ["36-2000", "38-1000"],
            },
            {
                "label": "Combined operators",
                "search_params": {
                    "q": "Strickland AND moti* AND ba?k NOT Lorem",
                },
                "expected_count": 1,
                "expected_in_content": ["34-2535"],
            },
        ]

        for test_case in tests:
            with self.subTest(label=test_case["label"]):
                response = self.client.get(
                    reverse("show_results"),
                    test_case["search_params"],
                )
                actual = self.get_article_count(response)
                self.assertEqual(
                    actual,
                    test_case["expected_count"],
                    msg=f"Failed on: {test_case['label']}",
                )
                decoded_content = response.content.decode()
                for expected_str in test_case["expected_in_content"]:
                    self.assertIn(
                        expected_str,
                        decoded_content,
                        msg=f"Failed on: {test_case['label']} missing {expected_str}",
                    )

    def test_support_search_connectors(self, court_cache_key_mock) -> None:
        """Verify that new supported custom search connectors yield the
        expected results.
        """

        tests = [
            {
                "label": "But not %",
                "search_params": {
                    "q": "Strickland % Lorem % America",
                },
                "expected_count": 1,
                "expected_in_content": ["1:21-cv-1234"],
            },
            {
                "label": "& connector test",
                "search_params": {
                    "q": "Strickland & Motion & Lorem",
                },
                "expected_count": 1,
                "expected_in_content": ["123456"],
            },
            {
                "label": "! Root expander suffix",
                "search_params": {
                    "q": "!Comp",
                },
                "expected_count": 2,
                "expected_in_content": ["36-2000", "38-1000"],
            },
            {
                "label": "Universal Character *",
                "search_params": {
                    "q": "p**nt",
                },
                "expected_count": 2,
                "expected_in_content": ["36-2000", "38-1000"],
            },
            {
                "label": "Combined operators",
                "search_params": {
                    "q": "Strickland & !moti & ba*k % Lorem",
                },
                "expected_count": 1,
                "expected_in_content": ["34-2535"],
            },
        ]

        for test_case in tests:
            with self.subTest(label=test_case["label"]):
                # Frontend
                response = self.client.get(
                    reverse("show_results"),
                    test_case["search_params"],
                )
                actual = self.get_article_count(response)
                self.assertEqual(
                    actual,
                    test_case["expected_count"],
                    msg=f"Failed on: {test_case['label']}",
                )
                decoded_content = response.content.decode()
                for expected_str in test_case["expected_in_content"]:
                    self.assertIn(
                        expected_str,
                        decoded_content,
                        msg=f"Failed on: {test_case['label']} missing {expected_str}",
                    )

                # API
                api_response = self.client.get(
                    reverse("search-list", kwargs={"version": "v4"}),
                    test_case["search_params"],
                )
                self.assertEqual(
                    len(api_response.data["results"]),
                    test_case["expected_count"],
                    msg=f"Failed on API: {test_case['label']}",
                )
                decoded_content = api_response.content.decode()
                for expected_str in test_case["expected_in_content"]:
                    self.assertIn(
                        expected_str,
                        decoded_content,
                        msg=f"Failed on Frontend: {test_case['label']} missing {expected_str}",
                    )

    def test_support_search_connectors_filters(
        self, court_cache_key_mock
    ) -> None:
        """Verify that new supported custom search connectors yield the
        expected results.
        """

        tests = [
            {
                "label": "But not %",
                "search_params": {
                    "case_name": "Strickland % Lorem % America",
                },
                "expected_count": 1,
                "expected_in_content": ["1:21-cv-1234"],
            },
            {
                "label": "& connector test",
                "search_params": {
                    "case_name": "Strickland & Lorem",
                },
                "expected_count": 1,
                "expected_in_content": ["123456"],
            },
            {
                "label": "! Root expander suffix",
                "search_params": {
                    "judge": "!Comp",
                },
                "expected_count": 2,
                "expected_in_content": ["36-2000", "38-1000"],
            },
            {
                "label": "Universal Character *",
                "search_params": {
                    "judge": "p**nt",
                },
                "expected_count": 2,
                "expected_in_content": ["36-2000", "38-1000"],
            },
            {
                "label": "Combined operators",
                "search_params": {
                    "case_name": "Calif*rnia & !Nev",
                },
                "expected_count": 1,
                "expected_in_content": ["38-1000"],
            },
        ]

        for test_case in tests:
            with self.subTest(label=test_case["label"]):
                # Frontend
                response = self.client.get(
                    reverse("show_results"),
                    test_case["search_params"],
                )
                actual = self.get_article_count(response)
                self.assertEqual(
                    actual,
                    test_case["expected_count"],
                    msg=f"Failed on: {test_case['label']}",
                )
                decoded_content = response.content.decode()
                for expected_str in test_case["expected_in_content"]:
                    self.assertIn(
                        expected_str,
                        decoded_content,
                        msg=f"Failed on Frontend: {test_case['label']} missing {expected_str}",
                    )

                # API
                api_response = self.client.get(
                    reverse("search-list", kwargs={"version": "v4"}),
                    test_case["search_params"],
                )
                self.assertEqual(
                    len(api_response.data["results"]),
                    test_case["expected_count"],
                    msg=f"Failed on API: {test_case['label']}",
                )
                decoded_content = api_response.content.decode()
                for expected_str in test_case["expected_in_content"]:
                    self.assertIn(
                        expected_str,
                        decoded_content,
                        msg=f"Failed on Frontend: {test_case['label']} missing {expected_str}",
                    )

    def test_disallowed_wildcard_pattern(self, court_cache_key_mock) -> None:
        """Verify that expensive wildcard queries thrown an error."""

        tests = [
            {
                "label": "Disallowed ! in short queries.",
                "search_params": {
                    "q": "!ap",
                },
            },
            {
                "label": "Disallowed * at the end in short queries.",
                "search_params": {
                    "q": "ap*",
                },
            },
            {
                "label": "Disallowed * at the beginning.",
                "search_params": {
                    "q": "*ing",
                },
            },
            {
                "label": "Disallowed ! in short queries - Filter.",
                "search_params": {
                    "case_name": "!ap",
                },
            },
            {
                "label": "Disallowed * at the end in short queries  - Filter.",
                "search_params": {
                    "judge": "ap*",
                },
            },
            {
                "label": "Disallowed * at the beginning  - Filter.",
                "search_params": {
                    "case_name": "*ing",
                },
            },
        ]

        for test_case in tests:
            with self.subTest(label=test_case["label"]):
                response = self.client.get(
                    reverse("show_results"),
                    test_case["search_params"],
                )
                decoded_content = response.content.decode()
                tree = html.fromstring(decoded_content)
                h2_error_element = tree.xpath('//h2[@class="alt"]')[0]
                h2_text_error = "".join(
                    h2_error_element.xpath(".//text()")
                ).strip()
                self.assertIn(
                    "The query contains a disallowed wildcard pattern.",
                    h2_text_error,
                    msg=f"Failed on: {test_case['label']}, no disallowed wildcard pattern error.",
                )

                # API V4
                api_response = self.client.get(
                    reverse("search-list", kwargs={"version": "v4"}),
                    test_case["search_params"],
                )
                self.assertEqual(api_response.status_code, 400)
                self.assertEqual(
                    api_response.data["detail"],
                    "The query contains a disallowed wildcard pattern.",
                    msg="Failed for V4",
                )

                # API V3
                api_response = self.client.get(
                    reverse("search-list", kwargs={"version": "v3"}),
                    test_case["search_params"],
                )
                self.assertEqual(api_response.status_code, 400)
                self.assertEqual(
                    api_response.data["detail"],
                    "The query contains a disallowed wildcard pattern.",
                    msg="Failed for V3",
                )


class SearchAPIV4CommonTest(ESIndexTestCase, TestCase):
    """Common tests for the Search API V4 endpoints."""

    async def test_es_general_bad_request_error_(self) -> None:
        """Can we properly raise the ElasticBadRequestError exception?"""

        # Bad syntax due to the / char in the query.
        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "This query contains long/short proximity token",
        }
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v4"}), params
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.data["detail"],
            "Elasticsearch Bad request error. Please review your query.",
        )

    async def test_es_bad_syntax_proximity_tokens(self) -> None:
        """Can we properly raise the BadProximityQuery exception?"""

        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "This query contains /s proximity token",
        }
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v4"}), params
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.data["detail"],
            "The query contains an unrecognized proximity token.",
        )

    async def test_es_unbalanced_quotes(self) -> None:
        """Can we properly raise the UnbalancedQuotesQuery exception?"""

        params = {"type": SEARCH_TYPES.RECAP, "q": 'Test query with "quotes'}
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v4"}), params
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.data["detail"], "The query contains unbalanced quotes."
        )

    async def test_handle_unbalanced_parentheses(self) -> None:
        """Can we properly raise the UnbalancedParenthesesQuery
        exception?
        """

        params = {
            "type": SEARCH_TYPES.RECAP,
            "q": "(Loretta OR (SEC) AND Jose",
        }
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v4"}), params
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.data["detail"], "The query contains unbalanced parentheses."
        )


class OpinionSearchFunctionalTest(AudioTestCase, BaseSeleniumTest):
    """
    Test some of the primary search functionality of CL: searching opinions.
    These tests should exercise all aspects of using the search box and SERP.
    """

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
        "functest_opinions.json",
    ]

    def setUp(self) -> None:
        self.pandora_profile = UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )
        super().setUp()

    def _perform_wildcard_search(self):
        searchbox = self.browser.find_element(By.ID, "id_q")
        searchbox.submit()
        result_count = self.browser.find_element(By.ID, "result-count")
        self.assertIn("Opinions", result_count.text)

    def test_query_cleanup_integration(self) -> None:
        # Dora goes to CL and performs a Search using a numbered citation
        # (e.g. "12-9238" or "3:18-cv-2383")
        self.browser.get(self.live_server_url)
        searchbox = self.browser.find_element(By.ID, "id_q")
        searchbox.clear()
        searchbox.send_keys("19-2205")
        searchbox.submit()
        # without the cleanup_main_query function, there are 4 results
        # with the query, there should be none
        results = self.browser.find_elements(By.CSS_SELECTOR, "#result-count")
        self.assertEqual(len(results), 0)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_toggle_to_oral_args_search_results(self) -> None:
        # Dora navigates to the global SERP from the homepage
        self.browser.get(self.live_server_url)
        self._perform_wildcard_search()
        self.extract_result_count_from_serp()

        # Dora sees she has Opinion results, but wants Oral Arguments
        self.assertTrue(self.extract_result_count_from_serp() > 0)
        label = self.browser.find_element(
            By.CSS_SELECTOR, 'label[for="id_type_0"]'
        )
        self.assertIn("selected", label.get_attribute("class"))
        self.assert_text_in_node("Date Filed", "body")
        self.assert_text_not_in_node("Date Argued", "body")

        # She clicks on Oral Arguments
        self.browser.find_element(By.ID, "navbar-oa").click()

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_search_and_facet_docket_numbers(self) -> None:
        # Dora goes to CL and performs an initial wildcard Search
        self.browser.get(self.live_server_url)
        self._perform_wildcard_search()
        initial_count = self.extract_result_count_from_serp()

        # Seeing a result that has a docket number displayed, she wants
        # to find all similar opinions with the same or similar docket
        # number
        search_results = self.browser.find_element(By.ID, "search-results")
        self.assertIn("Docket Number:", search_results.text)

        # She types part of the docket number into the docket number
        # filter on the left and hits enter
        text_box = self.browser.find_element(By.ID, "id_docket_number")
        text_box.send_keys("1337")
        text_box.submit()

        # The SERP refreshes and she sees resuls that
        # only contain fragments of the docker number she entered
        new_count = self.extract_result_count_from_serp()
        self.assertTrue(new_count < initial_count)

        search_results = self.browser.find_element(By.ID, "search-results")
        for result in search_results.find_elements(By.TAG_NAME, "article"):
            self.assertIn("1337", result.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_opinion_search_result_detail_page(self) -> None:
        # Dora navigates to CL and does a simple wild card search
        self.browser.get(self.live_server_url)
        self.browser.find_element(By.ID, "id_q").send_keys("voutila")
        self.browser.find_element(By.ID, "id_q").submit()

        # Seeing an Opinion immediately on the first page of results, she
        # wants more details so she clicks the title and drills into the result
        articles = self.browser.find_elements(By.TAG_NAME, "article")
        articles[0].find_elements(By.TAG_NAME, "a")[0].click()

        # She is brought to the detail page for the results
        self.assertNotIn("Search Results", self.browser.title)

        # and she can see lots of detail! This includes things like:
        # The name of the jurisdiction/court,
        # the status of the Opinion, any citations, the docket number,
        # the Judges, and a unique fingerpring ID
        meta_data = self.browser.find_elements(
            By.CSS_SELECTOR, ".case-details li strong"
        )
        headers = [
            "Citations:",
            "Docket Number:",
            "Nature of Suit:",
            "Posture:",
            "Full Case Name:",
        ]
        for header in headers:
            self.assertIn(header, [meta.text for meta in meta_data])

        # The complete body of the opinion is also displayed for her to
        # read on the page
        self.assertNotEqual(
            self.browser.find_element(By.ID, "opinion").text.strip(),
            "",
        )

        # Verify "Cited By" tab exists and it has a count on it
        cited_by_tab = self.browser.find_element(
            By.XPATH,
            '//ul[contains(@class, "nav-tabs")]//li//a[contains(., "Cited\u00a0By")]',
        )
        self.assertIsNotNone(cited_by_tab, "'Cited By' tab does not exist")
        cited_by_count = re.search(r"\((\d+)\)", cited_by_tab.text)
        self.assertIsNotNone(
            cited_by_count,
            '"Cited By" tab text must contain a number in parentheses (e.g., "(13)")',
        )
        cited_by_count = int(cited_by_count.group(1))
        self.assertGreaterEqual(
            cited_by_count, 1, f"Wrong Cited By count: {cited_by_count}"
        )

        # Go to cited by page and verify we loaded it correctly and then go back to main page
        cited_by_tab.click()
        section_title = self.browser.find_element(
            By.CSS_SELECTOR, ".opinion-section-title"
        )
        self.assertIn(
            "Cited By",
            section_title.text,
            f'Expected "Cited By" in section title, got: "{section_title.text}"',
        )
        cited_by_elements = self.browser.find_elements(
            By.CSS_SELECTOR, "div#cited-by article"
        )
        self.assertGreaterEqual(
            len(cited_by_elements),
            1,
            "Cited by expected at least 1 <article> element, found none",
        )
        self.browser.back()

        # Verify "Authorities" tab exists and it has a count on it
        authorities_tab = self.browser.find_element(
            By.XPATH,
            '//ul[contains(@class, "nav-tabs")]//li//a[contains(., "Authorities")]',
        )
        self.assertIsNotNone(
            authorities_tab, "'Authorities' tab does not exist"
        )
        authorities_count = re.search(r"\((\d+)\)", authorities_tab.text)
        self.assertIsNotNone(
            authorities_count,
            '"Authorities" tab text must contain a number in parentheses (e.g., "(13)")',
        )
        authorities_count = int(authorities_count.group(1))
        self.assertGreaterEqual(
            authorities_count,
            1,
            f"Wrong Authorities count: {authorities_count}",
        )

        # Go to authorities page and verify we loaded it correctly and then go back to main page
        authorities_tab.click()
        section_title = self.browser.find_element(
            By.CSS_SELECTOR, ".opinion-section-title"
        )
        self.assertIn(
            "Table of Authorities",
            section_title.text,
            f'Expected "Table of Authorities" in section title, got: "{section_title.text}"',
        )
        authorities_elements = self.browser.find_elements(
            By.CSS_SELECTOR, "div#authorities article"
        )
        self.assertGreaterEqual(
            len(authorities_elements),
            1,
            "Table of authorities expected at least 1 <article> element, found none",
        )
        self.browser.back()

        # Verify we returned to opinion main page
        self.assertNotEqual(
            self.browser.find_element(By.ID, "opinion").text.strip(),
            "",
        )

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_search_and_add_precedential_results(self) -> None:
        # Dora navigates to CL and just hits Search to just start with
        # a global result set
        self.browser.get(self.live_server_url)
        self._perform_wildcard_search()
        first_count = self.extract_result_count_from_serp()

        # She notices only Precedential results are being displayed
        prec = self.browser.find_element(By.ID, "id_stat_Published")
        non_prec = self.browser.find_element(By.ID, "id_stat_Unpublished")
        self.assertEqual(prec.get_attribute("checked"), "true")
        self.assertIsNone(non_prec.get_attribute("checked"))
        prec_count = self.browser.find_element(
            By.CSS_SELECTOR, 'label[for="id_stat_Published"]'
        )
        non_prec_count = self.browser.find_element(
            By.CSS_SELECTOR, 'label[for="id_stat_Unpublished"]'
        )
        self.assertNotIn("(0)", prec_count.text)
        self.assertNotIn("(0)", non_prec_count.text)

        # But she also notices the option to select and include
        # non_precedential results. She checks the box.
        non_prec.click()

        # Nothing happens yet.
        # TODO: this is hacky for now...just make sure result count is same
        self.assertEqual(first_count, self.extract_result_count_from_serp())

        # She goes ahead and clicks the Search button again to resubmit
        self.browser.find_element(By.ID, "search-button").click()

        # She didn't change the query, so the search box should still look
        # the same (which is blank)
        self.assertEqual(
            self.browser.find_element(By.ID, "id_q").get_attribute("value"), ""
        )

        # And now she notices her result set increases thanks to adding in
        # those other opinion types!
        second_count = self.extract_result_count_from_serp()
        self.assertTrue(second_count > first_count)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_basic_homepage_search_and_signin_and_signout(self) -> None:
        wait = WebDriverWait(self.browser, 1)

        # Dora navigates to the CL website.
        self.browser.get(self.live_server_url)

        # At a glance, Dora can see the Latest Opinions, Latest Oral Arguments,
        # the searchbox (obviously important), and a place to sign in
        page_text = get_with_wait(wait, (By.TAG_NAME, "body")).text
        self.assertIn("Latest Opinions", page_text)
        self.assertIn("Latest Oral Arguments", page_text)

        search_box = get_with_wait(wait, (By.ID, "id_q"))
        search_button = get_with_wait(wait, (By.ID, "search-button"))
        self.assertIn("Search", search_button.text)

        self.assertIn("Sign in / Register", page_text)

        # Dora remembers this Lissner guy and wonders if he's been involved
        # in any litigation. She types his name into the search box and hits
        # Enter
        search_box.send_keys("lissner")
        search_box.submit()

        # The browser brings her to a search engine result page with some
        # results. She notices her query is still in the searchbox and
        # has the ability to refine via facets
        result_count = get_with_wait(wait, (By.ID, "result-count"))

        self.assertIn("1 Opinion", result_count.text)
        search_box = get_with_wait(wait, (By.ID, "id_q"))
        self.assertEqual("lissner", search_box.get_attribute("value"))

        facet_sidebar = get_with_wait(wait, (By.ID, "extra-search-fields"))
        self.assertIn("Precedential Status", facet_sidebar.text)

        # She notes her URL For after signing in
        results_url = self.browser.current_url

        # Wanting to keep an eye on this Lissner guy, she decides to sign-in
        # and so she can create an alert
        sign_in = get_with_wait(wait, (By.LINK_TEXT, "Sign in / Register"))
        sign_in.click()

        # she providers her usename and password to sign in
        body_element = get_with_wait(wait, (By.TAG_NAME, "body"))
        page_text = body_element.text
        self.assertIn("Sign In", page_text)
        self.assertIn("Username", page_text)
        self.assertIn("Password", page_text)

        btn = get_with_wait(wait, (By.CSS_SELECTOR, 'button[type="submit"]'))
        self.assertEqual("Sign In", btn.text)

        get_with_wait(wait, (By.ID, "username")).send_keys("pandora")
        get_with_wait(wait, (By.ID, "password")).send_keys("password")
        btn.click()

        # After logging in, she goes to the homepage. From there, she goes back
        # to where she was, which still has "lissner" in the search box.
        self.browser.get(results_url)
        page_text = get_with_wait(wait, (By.TAG_NAME, "body")).text
        self.assertNotIn(
            "Please enter a correct username and password.", page_text
        )
        search_box = get_with_wait(wait, (By.ID, "id_q"))
        self.assertEqual("lissner", search_box.get_attribute("value"))

        # She now opens the modal for the form for creating an alert
        alert_bell = get_with_wait(
            wait, (By.CSS_SELECTOR, ".input-group-addon-blended i")
        )
        alert_bell.click()

        modal = wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-body"))
        )
        self.assertEqual("modal-body logged-in", modal.get_attribute("class"))

        page_text = get_with_wait(wait, (By.TAG_NAME, "body")).text
        self.assertIn("Create an Alert", page_text)
        self.assertIn("Give the alert a name", page_text)
        self.assertIn("How often should we notify you?", page_text)
        get_with_wait(wait, (By.ID, "id_name"))
        get_with_wait(wait, (By.ID, "id_rate"))
        btn = get_with_wait(wait, (By.ID, "alertSave"))
        self.assertEqual("Create Alert", btn.text)
        x_button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".modal-header .close")
            )
        )
        x_button.click()

        # But she decides to wait until another time. Instead she decides she
        # will log out. She notices a Profile link dropdown in the top of the
        # page, clicks it, and selects Sign out
        profile_dropdown = self.browser.find_elements(
            By.CSS_SELECTOR, "a.dropdown-toggle"
        )[0]
        self.assertEqual(profile_dropdown.text.strip(), "Profile")

        dropdown_menu = get_with_wait(
            wait, (By.CSS_SELECTOR, "ul.dropdown-menu")
        )
        self.assertIsNone(dropdown_menu.get_attribute("display"))
        profile_dropdown.click()

        sign_out = get_with_wait(
            wait, (By.XPATH, ".//button[contains(., 'Sign out')]")
        )
        sign_out.click()

        # She receives a sign out confirmation with links back to the homepage,
        # the block, and an option to sign back in.
        page_text = get_with_wait(wait, (By.TAG_NAME, "body")).text
        self.assertIn("You Have Successfully Signed Out", page_text)
        links = self.browser.find_elements(By.TAG_NAME, "a")
        self.assertIn("Go to the homepage", [link.text for link in links])
        self.assertIn("Read our blog", [link.text for link in links])

        bootstrap_btns = self.browser.find_elements(By.CSS_SELECTOR, "a.btn")
        self.assertIn("Sign Back In", [btn.text for btn in bootstrap_btns])

        # We are taking advantage of the queries done with authenticated and
        # anonymous user to see if SearchQuery collection is working
        lookup = {
            "get_params": "q=lissner",
            "user": None,
            "query_time_ms__gte": 0,
        }
        self.assertTrue(
            SearchQuery.objects.filter(**lookup).exists(),
            "a SearchQuery with get_params 'q=lissner' and anonymous user should have been created",
        )
        SearchQuery.objects.filter(user=None).delete()

        lookup["user"] = self.pandora_profile.user
        self.assertTrue(
            SearchQuery.objects.filter(**lookup).exists(),
            "a SearchQuery with get_params 'q=lissner' and 'pandora' user should have been created",
        )

        # Test if the SearchQuery get's deleted when the user is deleted
        self.pandora_profile.user.delete()
        lookup.pop("user")
        self.assertFalse(
            SearchQuery.objects.filter(**lookup).exists(),
            "SearchQuery should have been deleted when the user was deleted",
        )


class SaveSearchQueryTest(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        # Using plain text, fielded queries and manual filters

        self.base_searches = [
            # Recap
            r"type=r&q=trump&type=r&order_by=score%20desc&description=Notice",
            # Audio
            r"type=oa&q=company%20court_id:illappct&type=oa&order_by=score desc",
            # Opinions
            r"type=o&q=thomas&type=o&order_by=score%20desc&case_name=lorem",
            # People
            r"type=p&q=thomas&type=p&order_by=score%20desc&born_after=01/01/2080",
        ]

        self.searches = self.base_searches + [
            # Repeat the same query, for testing cache
            r"type=p&q=thomas&type=p&order_by=score%20desc&born_after=01/01/2080",
        ]

        super().setUp()
        self.source_error_message = (
            f"Saved wrong `engine` value, expected {SearchQuery.WEBSITE}"
        )

    @staticmethod
    def normalize_query(query, replace_space=False):
        """Normalize a query dictionary by sorting lists of values.
        Sometimes the search process alters the order of the query parameters,
        or duplicates them.
        """

        if replace_space:
            query = query.replace("%20", "+")
        parsed_query = parse_qs(query)
        return {k: sorted(v) for k, v in parsed_query.items()}

    @override_settings(ELASTICSEARCH_MICRO_CACHE_ENABLED=True)
    def test_search_query_saving(self) -> None:
        """Do we save queries on all public endpoints"""
        for query in self.searches:
            url = f"{reverse('show_results')}?{query}"
            self.client.get(url)
            # Compare parsed query strings;
            last_query = SearchQuery.objects.last()
            expected_query = self.normalize_query(query, replace_space=True)
            stored_query = self.normalize_query(last_query.get_params)
            self.assertEqual(
                expected_query,
                stored_query,
                f"Query was not saved properly. Expected {expected_query}, got {stored_query}",
            )
            self.assertEqual(
                last_query.engine,
                SearchQuery.ELASTICSEARCH,
                f"Saved wrong `engine` value, expected {SearchQuery.ELASTICSEARCH}",
            )
            self.assertEqual(
                last_query.source,
                SearchQuery.WEBSITE,
                self.source_error_message,
            )

        self.assertTrue(
            SearchQuery.objects.last().hit_cache,
            "Repeated query not marked as having hit cache",
        )

    def test_failed_es_search_queries(self) -> None:
        """Do we flag failed ElasticSearch queries properly?"""
        query = "type=r&q=contains/sproximity token"
        url = f"{reverse('show_results')}?{query}"
        self.client.get(url)
        last_query = SearchQuery.objects.last()
        self.assertTrue(last_query.failed, "SearchQuery.failed should be True")
        self.assertEqual(
            last_query.query_time_ms, None, "Query time should be None"
        )
        self.assertEqual(
            last_query.engine,
            SearchQuery.ELASTICSEARCH,
            f"Saved wrong `engine` value, expected {SearchQuery.ELASTICSEARCH}",
        )

    def test_search_api_v4_query_saving(self) -> None:
        """Do we save queries on all V4 Search endpoints"""
        for query in self.base_searches:
            url = f"{reverse("search-list", kwargs={"version": "v4"})}?{query}"
            self.client.get(url)
            # Compare parsed query strings;
            last_query = SearchQuery.objects.last()
            expected_query = self.normalize_query(query, replace_space=True)
            stored_query = self.normalize_query(last_query.get_params)
            self.assertEqual(
                expected_query,
                stored_query,
                f"Query was not saved properly. Expected {expected_query}, got {stored_query}",
            )
            self.assertEqual(
                last_query.engine,
                SearchQuery.ELASTICSEARCH,
                f"Saved wrong `engine` value, expected {SearchQuery.ELASTICSEARCH}",
            )
            self.assertEqual(
                last_query.source,
                SearchQuery.API,
                self.source_error_message,
            )

    def test_failed_es_search_v4_api_queries(self) -> None:
        """Do we flag failed v4 API queries properly?"""
        query = "type=r&q=contains/sproximity token"
        url = f"{reverse("search-list", kwargs={"version": "v4"})}?{query}"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 400)
        last_query = SearchQuery.objects.last()
        self.assertTrue(last_query.failed, "SearchQuery.failed should be True")
        self.assertEqual(
            last_query.query_time_ms, None, "Query time should be None"
        )
        self.assertEqual(
            last_query.engine,
            SearchQuery.ELASTICSEARCH,
            f"Saved wrong `engine` value, expected {SearchQuery.ELASTICSEARCH}",
        )

    def test_search_es_api_v3_query_saving(self) -> None:
        """Do we save queries on all V3 Search endpoints"""
        for query in self.base_searches:
            url = f"{reverse("search-list", kwargs={"version": "v3"})}?{query}"
            self.client.get(url)
            # Compare parsed query strings;
            last_query = SearchQuery.objects.last()
            expected_query = self.normalize_query(query, replace_space=True)
            stored_query = self.normalize_query(last_query.get_params)
            self.assertEqual(
                expected_query,
                stored_query,
                f"Query was not saved properly. Expected {expected_query}, got {stored_query}",
            )
            self.assertEqual(
                last_query.engine,
                SearchQuery.ELASTICSEARCH,
                f"Saved wrong `engine` value, expected {SearchQuery.ELASTICSEARCH}",
            )
            self.assertEqual(
                last_query.source,
                SearchQuery.API,
                self.source_error_message,
            )

    def test_failed_es_search_v3_api_queries(self) -> None:
        """Do we flag failed ES v3 API queries properly?"""
        query = "type=r&q=contains/sproximity token"
        url = f"{reverse("search-list", kwargs={"version": "v3"})}?{query}"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 500)
        last_query = SearchQuery.objects.last()
        self.assertTrue(last_query.failed, "SearchQuery.failed should be True")
        self.assertEqual(
            last_query.query_time_ms, None, "Query time should be None"
        )
        self.assertEqual(
            last_query.engine,
            SearchQuery.ELASTICSEARCH,
            f"Saved wrong `engine` value, expected {SearchQuery.ELASTICSEARCH}",
        )


class CaptionTest(TestCase):
    """Can we make good looking captions?"""

    async def test_simple_caption(self) -> None:
        c, _ = await Court.objects.aget_or_create(
            pk="ca1", defaults={"position": 1}
        )
        d = await Docket.objects.acreate(source=0, court=c)
        cluster = await OpinionCluster.objects.acreate(
            case_name="foo", docket=d, date_filed=date(1984, 1, 1)
        )
        await Citation.objects.acreate(
            cluster=cluster,
            type=Citation.FEDERAL,
            volume=22,
            reporter="F.2d",
            page="44",
        )
        self.assertEqual(
            "foo, 22 F.2d 44&nbsp;(1st&nbsp;Cir.&nbsp;1984)",
            await cluster.acaption(),
        )

    async def test_scotus_caption(self) -> None:
        c, _ = await Court.objects.aget_or_create(
            pk="scotus", defaults={"position": 2}
        )
        d = await Docket.objects.acreate(source=0, court=c)
        cluster = await OpinionCluster.objects.acreate(
            case_name="foo", docket=d, date_filed=date(1984, 1, 1)
        )
        await Citation.objects.acreate(
            cluster=cluster,
            type=Citation.FEDERAL,
            volume=22,
            reporter="U.S.",
            page="44",
        )
        self.assertEqual("foo, 22 U.S. 44", await cluster.acaption())

    async def test_neutral_cites(self) -> None:
        c, _ = await Court.objects.aget_or_create(
            pk="ca1", defaults={"position": 1}
        )
        d = await Docket.objects.acreate(source=0, court=c)
        cluster = await OpinionCluster.objects.acreate(
            case_name="foo", docket=d, date_filed=date(1984, 1, 1)
        )
        await Citation.objects.acreate(
            cluster=cluster,
            type=Citation.NEUTRAL,
            volume=22,
            reporter="IL",
            page="44",
        )
        self.assertEqual("foo, 22 IL 44", await cluster.acaption())

    def test_citation_sorting(self) -> None:
        # A list of citations ordered properly
        cs = [
            Citation(
                volume=22, reporter="IL", page="44", type=Citation.NEUTRAL
            ),
            Citation(
                volume=22, reporter="U.S.", page="44", type=Citation.FEDERAL
            ),
            Citation(
                volume=22, reporter="S. Ct.", page="33", type=Citation.FEDERAL
            ),
            Citation(
                volume=22,
                reporter="Alt.",
                page="44",
                type=Citation.STATE_REGIONAL,
            ),
        ]

        # Mess up the ordering of the list above.
        cs_shuffled = cs[:]
        last = cs_shuffled.pop()
        cs_shuffled.insert(0, last)
        self.assertNotEqual(cs, cs_shuffled)

        # Now sort the messed up list, and check if it worked.
        cs_sorted = sorted(cs_shuffled, key=sort_cites)
        self.assertEqual(cs, cs_sorted)


class DocketEntriesTimezone(TestCase):
    """Test docket entries with time, store date and time in the local court
    timezone and make datetime_filed aware to the local court timezone.
    """

    @classmethod
    def setUpTestData(cls):
        cls.cand = CourtFactory(id="cand", jurisdiction="FB")
        cls.nyed = CourtFactory(id="nyed", jurisdiction="FB")
        cls.d_cand = DocketFactory(
            source=Docket.RECAP,
            court=cls.cand,
            pacer_case_id="104490",
        )
        cls.d_nyed = DocketFactory(
            source=Docket.RECAP,
            court=cls.nyed,
            pacer_case_id="104491",
        )

        # No datetime
        cls.de_date_data = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime.date(2021, 10, 15),
                    document_number=1,
                )
            ],
        )

        cls.de_date_data_changes = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime.date(2021, 10, 16),
                    document_number=1,
                )
            ],
        )

        cls.de_no_date = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=None,
                    document_number=1,
                )
            ],
        )

        # DST entries in UTC
        cls.de_utc_data = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime.datetime(
                        2021, 10, 16, 2, 46, 51, tzinfo=tzutc()
                    ),
                    document_number=1,
                )
            ],
        )

        cls.de_utc_changes_time = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime.datetime(
                        2021, 10, 16, 2, 50, 11, tzinfo=tzutc()
                    ),
                    document_number=1,
                )
            ],
        )

        # DST entries in a different time offset
        cls.de_pdt_data = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime.datetime(
                        2021, 10, 16, 2, 46, 51, tzinfo=tzoffset(None, -25200)
                    ),
                    document_number=2,
                )
            ],
        )

        # Not DST entries in UTC
        cls.de_utc_data_not_dst = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime.datetime(
                        2023, 1, 16, 2, 46, 51, tzinfo=tzutc()
                    ),
                    document_number=1,
                )
            ],
        )

    def test_add_docket_entries_with_no_time(self):
        """Do time_filed field and datetime_filed property are None when
        ingesting docket entries with no time info?
        """

        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_date_data["docket_entries"]
        )
        de_cand_date = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        self.assertEqual(de_cand_date.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand_date.time_filed, None)
        self.assertEqual(de_cand_date.datetime_filed, None)

    def test_add_docket_entries_with_time(self):
        """Can we store docket entries date_filed in the local court timezone
        divided into date_filed and time_filed if we ingest
        docket entries with datetime?
        """

        # Add docket entries with UTC datetime for CAND
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_utc_data["docket_entries"]
        )

        # Add docket entries with a different time offset than UTC datetime
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_pdt_data["docket_entries"]
        )

        de_cand_utc = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        de_cand_pdt = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=2
        )
        # Compare both dates are stored in local court timezone PDT for CAND
        self.assertEqual(de_cand_utc.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand_utc.time_filed, datetime.time(19, 46, 51))

        self.assertEqual(de_cand_pdt.date_filed, datetime.date(2021, 10, 16))
        self.assertEqual(de_cand_pdt.time_filed, datetime.time(2, 46, 51))

        # Add docket entries with UTC datetime for NYED
        async_to_sync(add_docket_entries)(
            self.d_nyed, self.de_utc_data["docket_entries"]
        )

        # Add docket entries with a different time offset than UTC datetime
        async_to_sync(add_docket_entries)(
            self.d_nyed, self.de_pdt_data["docket_entries"]
        )

        de_nyed_utc = DocketEntry.objects.get(
            docket__court=self.nyed, entry_number=1
        )
        de_nyed_pdt = DocketEntry.objects.get(
            docket__court=self.nyed, entry_number=2
        )
        # Compare both dates are stored in local court timezone PDT for NYED
        self.assertEqual(de_nyed_utc.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_nyed_utc.time_filed, datetime.time(22, 46, 51))

        self.assertEqual(de_nyed_pdt.date_filed, datetime.date(2021, 10, 16))
        self.assertEqual(de_nyed_pdt.time_filed, datetime.time(5, 46, 51))

    def test_update_docket_entries_without_date_or_time_data(self):
        """Can we avoid updating docket entries date_filed and time_filed if
        we ingest docket entries with no date_filed?
        """

        # Add docket entries with UTC datetime for CAND
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_utc_data["docket_entries"]
        )

        de_cand = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        # Compare both dates are stored in local court timezone PDT for CAND
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

        # Add docket entries with null date_filed
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_no_date["docket_entries"]
        )
        de_cand.refresh_from_db()
        # Docket entry date_filed and time_filed are remain the same
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

    def test_update_docket_entries_with_no_time_data(self):
        """Does time_filed is set to None only when the new date_filed doesn't
        contain time data and the date differs from the previous one?
        """

        # Add docket entries with UTC datetime for CAND
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_utc_data["docket_entries"]
        )

        de_cand = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        # Compare both dates are stored in local court timezone PDT for CAND
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

        # Add docket entries without time data but same date
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_date_data["docket_entries"]
        )
        de_cand.refresh_from_db()
        # Avoid updating date-time if the date doesn't change
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

        # Add docket entries without time data but different date
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_date_data_changes["docket_entries"]
        )
        de_cand.refresh_from_db()
        # Docket entry date_filed is different from the previous one and,
        # time_filed should be null.
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 16))
        self.assertEqual(de_cand.time_filed, None)

    def test_update_docket_entries_with_time_data(self):
        """Does data_filed and time_filed are properly updated when ingesting
        docket entries with date and time data?
        """

        # Add docket entries with UTC datetime for CAND
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_utc_data["docket_entries"]
        )

        de_cand = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        # Compare both dates are stored in local court timezone PDT for CAND
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

        # Add docket entries with UTC datetime for CAND, time changes,
        # date remains the same
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_utc_changes_time["docket_entries"]
        )
        de_cand.refresh_from_db()
        # Time is properly updated.
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 50, 11))

        # Add docket entries with UTC datetime for CAND, date and time change.
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_utc_data_not_dst["docket_entries"]
        )
        de_cand.refresh_from_db()
        # Date and time are updated accordingly.
        self.assertEqual(de_cand.date_filed, datetime.date(2023, 1, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(18, 46, 51))

    def test_show_docket_entry_date_filed_according_court_timezone_dst(self):
        """Does the datetime_filed is shown to properly to users using the
        timezone template filter, considering DST time?
        """

        # Add docket entries for CAND US/Pacific filed in DST, in UTC and a
        # different time offset.
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_utc_data["docket_entries"]
        )
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_pdt_data["docket_entries"]
        )

        de_cand_utc = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        de_cand_pdt = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=2
        )

        court_timezone = pytz.timezone(
            COURT_TIMEZONES.get(self.d_cand.court_id, "US/Eastern")
        )
        # Compare date using local timezone, DST 7 hours of difference:
        target_date_aware = court_timezone.localize(
            datetime.datetime(2021, 10, 15, 19, 46, 51)
        )
        self.assertEqual(de_cand_utc.datetime_filed, target_date_aware)

        target_date_aware = court_timezone.localize(
            datetime.datetime(2021, 10, 16, 2, 46, 51)
        )
        self.assertEqual(
            de_cand_pdt.datetime_filed,
            target_date_aware,
        )

        # Add docket entries for NYED US/Eastern filed in DST, in UTC and a
        # different time offset.
        async_to_sync(add_docket_entries)(
            self.d_nyed, self.de_utc_data["docket_entries"]
        )
        async_to_sync(add_docket_entries)(
            self.d_nyed, self.de_pdt_data["docket_entries"]
        )

        de_nyed_utc = DocketEntry.objects.get(
            docket__court=self.nyed, entry_number=1
        )
        de_nyed_pdt = DocketEntry.objects.get(
            docket__court=self.nyed, entry_number=2
        )

        court_timezone = pytz.timezone(
            COURT_TIMEZONES.get(self.d_nyed.court_id, "US/Eastern")
        )
        # Compare date using local timezone, DST 4 hours of difference:
        target_date_aware = court_timezone.localize(
            datetime.datetime(2021, 10, 15, 22, 46, 51)
        )
        self.assertEqual(de_nyed_utc.datetime_filed, target_date_aware)

        target_date_aware = court_timezone.localize(
            datetime.datetime(2021, 10, 16, 5, 46, 51)
        )
        self.assertEqual(de_nyed_pdt.datetime_filed, target_date_aware)

    def test_show_docket_entry_date_filed_according_court_timezone_not_dst(
        self,
    ):
        """Does the datetime_filed is shown to properly to users using the
        timezone template filter, considering a not DST time?
        """

        # Add docket entries for CAND filed in not DST time. US/Pacific
        async_to_sync(add_docket_entries)(
            self.d_cand, self.de_utc_data_not_dst["docket_entries"]
        )
        de_cand_utc = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )

        court_timezone = pytz.timezone(
            COURT_TIMEZONES.get(self.d_cand.court_id, "US/Eastern")
        )
        # Compare date using local timezone, not DST 8 hours of difference:
        target_date_aware = court_timezone.localize(
            datetime.datetime(2023, 1, 15, 18, 46, 51),
        )
        self.assertEqual(de_cand_utc.datetime_filed, target_date_aware)

        # Add docket entries for NYED filed in not DST time. US/Eastern
        async_to_sync(add_docket_entries)(
            self.d_nyed, self.de_utc_data_not_dst["docket_entries"]
        )
        de_nyed_utc = DocketEntry.objects.get(
            docket__court=self.nyed, entry_number=1
        )

        court_timezone = pytz.timezone(
            COURT_TIMEZONES.get(self.d_nyed.court_id, "US/Eastern")
        )
        # Compare date using local timezone, not DST 5 hours of difference:
        target_date_aware = court_timezone.localize(
            datetime.datetime(2023, 1, 15, 21, 46, 51)
        )
        self.assertEqual(de_nyed_utc.datetime_filed, target_date_aware)


class ESIndexingTasksUtils(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.opinion = OpinionWithParentsFactory.create(
            cluster__precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
        )
        cls.person = PersonFactory.create(name_first="John American")
        cls.position = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=cls.court,
            date_start=datetime.date(2015, 12, 14),
            person=cls.person,
            how_selected="e_part",
            nomination_process="fed_senate",
        )
        cls.de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=cls.court,
                docket_number="12-09876",
                case_name="People v. Lorem",
                source=Docket.RECAP,
            ),
            entry_number=1,
        )
        cls.rd = RECAPDocumentFactory(
            docket_entry=cls.de,
            document_number="1",
            is_available=True,
        )

    @staticmethod
    def mock_pgh_created_at(mock_date) -> int:
        """Since it is not possible to use time_machine to mock the
        pgh_created_at field on instances created by triggers, this method
        assigns the mock_date to the most recently created event.
        """
        docket_events = DocketEvent.objects.all().order_by("pgh_created_at")
        latest_d_event = docket_events.last()
        latest_d_event.pgh_created_at = mock_date
        latest_d_event.save()

        return latest_d_event.pk

    def test_get_es_doc_id_and_parent_id(self) -> None:
        """Confirm that get_es_doc_id_and_parent_id returns the correct doc_id
        and parent_id for their use in ES indexing.
        """

        tests = [
            {
                "es_doc": PositionDocument,
                "instance": self.position,
                "expected_doc_id": f"po_{self.position.pk}",
                "expected_parent_id": self.position.person_id,
            },
            {
                "es_doc": ESRECAPDocument,
                "instance": self.rd,
                "expected_doc_id": f"rd_{self.rd.pk}",
                "expected_parent_id": self.de.docket_id,
            },
            {
                "es_doc": OpinionDocument,
                "instance": self.opinion,
                "expected_doc_id": f"o_{self.opinion.pk}",
                "expected_parent_id": self.opinion.cluster_id,
            },
            {
                "es_doc": DocketDocument,
                "instance": self.de.docket,
                "expected_doc_id": self.de.docket.pk,
                "expected_parent_id": None,
            },
        ]
        for test in tests:
            doc_id, parent_id = get_es_doc_id_and_parent_id(
                test["es_doc"],  # type: ignore
                test["instance"],  # type: ignore
            )
            self.assertEqual(doc_id, test["expected_doc_id"])
            self.assertEqual(parent_id, test["expected_parent_id"])

    def test_get_unique_oldest_date_range_rows(self) -> None:
        """Can we retrieve the unique oldest rows from history tables within a
        specified date range?
        """

        docket_2 = DocketFactory(
            court=self.court,
            docket_number="21-55555",
            case_name="Enterprises, Inc v. Lorem",
            source=Docket.RECAP,
        )
        docket_1 = self.de.docket
        expected_event_ids = set()
        # Events created outside (before) the date_range.
        mock_date = now().replace(year=2024, month=1, day=15, hour=1)
        # docket_1 updates.
        docket_1.docket_number = "12-00000-v1"
        docket_1.case_name = "The People v. Lorem v1"
        docket_1.save()
        self.mock_pgh_created_at(mock_date)

        # docket_2 updates.
        docket_2.docket_number = "21-00000-v1"
        docket_2.case_name = "Enterprises, Inc v. The People v1"
        docket_2.save()
        self.mock_pgh_created_at(mock_date)

        # Events created within the date_range.
        mock_date = now().replace(year=2024, month=1, day=16, hour=1)
        # docket_1 updates.
        docket_1.docket_number = "12-00000-v2"
        docket_1.case_name = "The People v. Lorem v2"
        docket_1.save()
        # Oldest event within the data_range is expected.
        expected_id = self.mock_pgh_created_at(mock_date)
        expected_event_ids.add(expected_id)

        mock_date = now().replace(year=2024, month=1, day=16, hour=2)
        docket_1.docket_number = "12-00000-v3"
        docket_1.save()
        self.mock_pgh_created_at(mock_date)

        mock_date = now().replace(year=2024, month=1, day=18, hour=1)
        # docket_2 updates.
        docket_2.docket_number = "21-00000-v2"
        docket_2.save()
        # Oldest event within the data_range is expected.
        expected_id = self.mock_pgh_created_at(mock_date)
        expected_event_ids.add(expected_id)

        mock_date = now().replace(year=2024, month=1, day=19, hour=1)
        docket_2.case_name = "Enterprises, Inc v. The People v3"
        docket_2.save()
        self.mock_pgh_created_at(mock_date)

        # Events created outside (after) the date_range
        mock_date = now().replace(year=2024, month=1, day=20, hour=0)
        # docket_1 updates.
        docket_1.docket_number = "12-00000-v-latest"
        docket_1.case_name = "The People v. Lorem v-latest"
        docket_1.save()
        self.mock_pgh_created_at(mock_date)

        # docket_1 updates.
        docket_2.docket_number = "21-00000-v-lates"
        docket_2.case_name = "Enterprises, Inc v. The People v-latest"
        docket_2.save()
        self.mock_pgh_created_at(mock_date)

        # date_range dates.
        date_start = now().replace(year=2024, month=1, day=16, hour=0)
        date_end = now().replace(year=2024, month=1, day=19, hour=1)
        unique_events = get_unique_oldest_history_rows(
            date_start, date_end, 0, EventTable.DOCKET
        )
        # Confirm the expected events are returned.
        unique_event_ids = set(unique_events.values_list("pgh_id", flat=True))
        self.assertEqual(unique_event_ids, expected_event_ids)


@mock.patch(
    "cl.search.management.commands.sweep_indexer.compose_indexer_redis_key",
    return_value="es_sweep_indexer:log_test",
)
class SweepIndexerCommandTest(
    CourtTestCase, PeopleTestCase, ESIndexTestCase, TestCase
):
    """sweep_indexer command tests for Elasticsearch"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=cls.court,
                date_filed=datetime.date(2015, 8, 16),
                docket_number="1:21-bk-1234",
                nature_of_suit="440",
                source=Docket.RECAP,
            ),
            entry_number=1,
            date_filed=datetime.date(2015, 8, 19),
        )
        cls.rd = RECAPDocumentFactory(
            docket_entry=cls.de,
            document_number="1",
        )
        cls.rd_att = RECAPDocumentFactory(
            docket_entry=cls.de,
            document_number="1",
            attachment_number=2,
            document_type=RECAPDocument.ATTACHMENT,
        )
        cls.de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=cls.court,
                date_filed=datetime.date(2016, 8, 16),
                date_argued=datetime.date(2012, 6, 23),
                source=Docket.RECAP_AND_IDB,
            ),
            entry_number=None,
            date_filed=datetime.date(2014, 7, 19),
        )
        cls.rd_2 = RECAPDocumentFactory(
            docket_entry=cls.de_1,
            document_number="",
        )

        # Audio Factories
        cls.audio_1 = AudioFactory(
            docket_id=cls.de.docket_id,
            duration=420,
            local_path_original_file="test/audio/ander_v._leo.mp3",
            local_path_mp3="test/audio/2.mp3",
            source="C",
            blocked=False,
            sha1="a49ada00977449",
            processing_complete=True,
        )
        cls.audio_2 = AudioFactory(
            docket_id=cls.de_1.docket_id,
            duration=837,
            local_path_original_file="mp3/2014/06/09/ander_v._leo.mp3",
            local_path_mp3="test/audio/2.mp3",
            source="C",
            sha1="a49ada0097744956",
            processing_complete=True,
        )
        # This audio shouldn't be indexed since is not processed.
        cls.audio_3 = AudioFactory(
            docket_id=cls.de_1.docket_id,
            processing_complete=False,
        )

        # Opinion Factories
        cls.opinion_cluster_1 = OpinionClusterFactory.create(
            source="C",
            precedential_status="Errata",
            docket=cls.de.docket,
        )
        cls.opinion_1 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_2,
            cluster=cls.opinion_cluster_1,
            type="020lead",
        )
        cls.opinion_2 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_2,
            cluster=cls.opinion_cluster_1,
            type="010combined",
        )

        cls.opinion_cluster_2 = OpinionClusterFactory.create(
            source="C",
            precedential_status="Published",
            docket=cls.de_1.docket,
        )
        cls.opinion_3 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_3,
            cluster=cls.opinion_cluster_2,
            type="010combined",
        )

        # No RECAP Docket.
        DocketFactory(
            court=cls.court,
            date_filed=datetime.date(2019, 8, 16),
            docket_number="21-bk-2341",
            nature_of_suit="440",
            source=Docket.HARVARD,
        )

    def tearDown(self) -> None:
        self.delete_index(
            [
                "search.OpinionCluster",
                "search.Docket",
                "audio.Audio",
                "people_db.Person",
            ]
        )
        self.create_index(
            [
                "search.OpinionCluster",
                "search.Docket",
                "audio.Audio",
                "people_db.Person",
            ]
        )

    def test_sweep_indexer_all(self, mock_logging_prefix):
        """Confirm the sweep_indexer command works properly indexing 'all' the
        documents serially.
        """

        s = DocketDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)

        s = AudioDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)

        s = PersonDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)

        s = OpinionClusterDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)

        # Call sweep_indexer command.
        with mock.patch(
            "cl.search.management.commands.sweep_indexer.logger"
        ) as mock_logger:
            call_command(
                "sweep_indexer",
                testing_mode=True,
            )
            expected_dict = {
                "audio.Audio": 2,
                "people_db.Person": 2,
                "search.OpinionCluster": 2,
                "search.Opinion": 3,
                "search.Docket": 2,
                "search.RECAPDocument": 3,
            }
            # All the instances of each type should be indexed.
            mock_logger.info.assert_called_with(
                f"\rDocuments Indexed: {expected_dict}"
            )

        # Confirm Dockets are indexed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2, msg="Wrong number of Dockets returned.")

        # Confirm RECAPDocuments are indexed.
        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de.docket.pk)
        self.assertEqual(
            s.count(), 2, msg="Wrong number of RECAPDocuments returned."
        )
        # Confirm routing_ids are properly set.
        response = s.execute()
        self.assertEqual(int(response[0].meta.routing), self.de.docket.pk)
        self.assertEqual(int(response[1].meta.routing), self.de.docket.pk)

        # Confirm RECAPDocuments are indexed.
        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de_1.docket.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of RECAPDocuments returned."
        )
        # Confirm routing_ids are properly set.
        response = s.execute()
        self.assertEqual(int(response[0].meta.routing), self.de_1.docket.pk)

        # Confirm Audios are indexed.
        s = AudioDocument.search().query("match_all")
        self.assertEqual(s.count(), 2)

        # Confirm Persons are indexed
        s = PersonDocument.search()
        s = s.query(Q("match", person_child="person"))
        self.assertEqual(s.count(), 2, msg="Wrong number of judges returned.")

        # Confirm Positions are indexed.
        s = PersonDocument.search()
        s = s.query("parent_id", type="position", id=self.person_2.pk)
        self.assertEqual(s.count(), 2)

        s = PersonDocument.search()
        s = s.query("parent_id", type="position", id=self.person_3.pk)
        self.assertEqual(s.count(), 1)

        # Confirm OpinionCluster are indexed
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion_cluster"))
        self.assertEqual(
            s.count(), 2, msg="Wrong number of Clusters returned."
        )

        # Confirm Opinions are indexed.
        s = OpinionClusterDocument.search()
        s = s.query("parent_id", type="opinion", id=self.opinion_cluster_1.pk)
        self.assertEqual(
            s.count(), 2, msg="Wrong number of Opinions returned."
        )
        # Confirm routing_ids are properly set.
        response = s.execute()
        self.assertEqual(
            int(response[0].meta.routing), self.opinion_cluster_1.pk
        )
        self.assertEqual(
            int(response[1].meta.routing), self.opinion_cluster_1.pk
        )

        s = OpinionClusterDocument.search()
        s = s.query("parent_id", type="opinion", id=self.opinion_cluster_2.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of Opinions returned."
        )
        # Confirm routing_ids are properly set.
        response = s.execute()
        self.assertEqual(
            int(response[0].meta.routing), self.opinion_cluster_2.pk
        )

    @override_settings(ELASTICSEARCH_SWEEP_INDEXER_ACTION="missing")
    def test_sweep_indexer_missing(self, mock_logging_prefix):
        """Confirm the sweep_indexer command works properly indexing 'missing'
        the documents serially.
        """

        # Call sweep_indexer command to indexing everything.
        call_command(
            "sweep_indexer",
            testing_mode=True,
        )

        # Remove one instance of each type from their index.
        DocketDocument.get(id=self.de_1.docket.pk).delete(
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
        )
        DocketDocument.get(id=ES_CHILD_ID(self.rd.pk).RECAP).delete(
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
        )
        AudioDocument.get(id=self.audio_1.pk).delete(
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
        )
        PersonDocument.get(id=self.person_2.pk).delete(
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
        )
        PersonDocument.get(id=ES_CHILD_ID(self.position_2.pk).POSITION).delete(
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
        )
        OpinionClusterDocument.get(id=self.opinion_cluster_1.pk).delete(
            refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
        )
        OpinionClusterDocument.get(
            id=ES_CHILD_ID(self.opinion_3.pk).OPINION
        ).delete(refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH)

        with mock.patch(
            "cl.search.management.commands.sweep_indexer.logger"
        ) as mock_logger:
            call_command(
                "sweep_indexer",
                testing_mode=True,
            )
            expected_dict = {
                "audio.Audio": 1,
                "people_db.Person": 1,
                "search.OpinionCluster": 1,
                "search.Opinion": 1,
                "search.Docket": 1,
                "search.RECAPDocument": 1,
            }
            # Only missing instances of each type should be indexed.
            mock_logger.info.assert_called_with(
                f"\rDocuments Indexed: {expected_dict}"
            )

        # Confirm Dockets are indexed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2, msg="Wrong number of Dockets returned.")
        # Confirm RECAPDocuments are indexed.
        s = ESRECAPDocument.search()
        s = s.query(Q("match", docket_child="recap_document"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of RECAPDocuments returned."
        )
        # Confirm Audios are indexed.
        s = AudioDocument.search().query("match_all")
        self.assertEqual(s.count(), 2)
        # Confirm Persons are indexed
        s = PersonDocument.search()
        s = s.query(Q("match", person_child="person"))
        self.assertEqual(s.count(), 2, msg="Wrong number of judges returned.")
        # Confirm Positions are indexed.
        s = PositionDocument.search()
        s = s.query(Q("match", person_child="position"))
        self.assertEqual(s.count(), 3)
        # Confirm OpinionCluster are indexed
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion_cluster"))
        self.assertEqual(
            s.count(), 2, msg="Wrong number of Clusters returned."
        )
        # Confirm Opinions are indexed.
        s = OpinionDocument.search()
        s = s.query(Q("match", cluster_child="opinion"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of Opinions returned."
        )

    def test_restart_from_last_document_logged(self, mock_logging_prefix):
        """Confirm the sweep_indexer command can resume from where it left
        off after a failure or interruption.
        """

        # Log last status to simulate a resume from "search.Docket"
        log_indexer_last_status(
            "search.Docket",
            self.de.docket.pk,
            0,
        )

        with mock.patch(
            "cl.search.management.commands.sweep_indexer.logger"
        ) as mock_logger:
            call_command(
                "sweep_indexer",
                testing_mode=True,
            )
            expected_dict = {
                "audio.Audio": 0,
                "people_db.Person": 0,
                "search.OpinionCluster": 0,
                "search.Opinion": 0,
                "search.Docket": 2,
                "search.RECAPDocument": 3,
            }
            # Only Docket and RECAPDocument should be indexed.
            mock_logger.info.assert_called_with(
                f"\rDocuments Indexed: {expected_dict}"
            )

        # Confirm Dockets are indexed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2, msg="Wrong number of Dockets returned.")
        # Confirm RECAPDocuments are indexed.
        s = ESRECAPDocument.search()
        s = s.query(Q("match", docket_child="recap_document"))
        self.assertEqual(
            s.count(), 3, msg="Wrong number of RECAPDocuments returned."
        )

        # Confirm no Audios were indexed.
        s = AudioDocument.search().query("match_all")
        self.assertEqual(s.count(), 0)
        # Confirm that neither Person nor Positions were indexed.
        s = PersonDocument.search().query("match_all")
        self.assertEqual(s.count(), 0, msg="Wrong number of judges returned.")
        # Confirm that neither OpinionCluster nor Opinions were indexed.
        s = OpinionClusterDocument.search().query("match_all")
        self.assertEqual(
            s.count(), 0, msg="Wrong number of Clusters returned."
        )


@mock.patch(
    "cl.search.management.commands.sweep_indexer.compose_indexer_redis_key",
    return_value="es_sweep_indexer:log_remove",
)
class RemoveContentFromESCommandTest(ESIndexTestCase, TestCase):
    """cl_remove_content_from_es command tests for Elasticsearch"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.court = CourtFactory(id="canb", jurisdiction="FB")

        cls.recap_docket = DocketFactory(
            court=cls.court,
            date_filed=datetime.date(2015, 8, 16),
            docket_number="1:21-bk-1234",
            nature_of_suit="440",
            source=Docket.RECAP,
        )
        cls.non_recap_docket = DocketFactory(
            court=cls.court,
            date_filed=datetime.date(2019, 8, 16),
            docket_number="21-bk-2341",
            nature_of_suit="440",
            source=Docket.HARVARD,
        )
        cls.non_recap_docket_2 = DocketFactory(
            court=cls.court,
            date_filed=datetime.date(2010, 8, 16),
            docket_number="21-bk-2632",
            nature_of_suit="440",
            source=Docket.HARVARD,
        )
        r = get_redis_interface("CACHE")
        keys_remove = r.keys(compose_redis_key_remove_content())
        if keys_remove:
            r.delete(*keys_remove)

    def tearDown(self) -> None:
        self.delete_index(["search.Docket", "search.OpinionCluster"])
        self.create_index(["search.Docket", "search.OpinionCluster"])

    def test_remove_non_recap_dockets(self, mock_logging_prefix):
        """Confirm the cl_remove_content_from_es command works
        properly removing non-recap dockets from ES.
        """

        # Index all the dockets regardless of their source.
        index_dockets_in_bulk.delay(
            [
                self.recap_docket.pk,
                self.non_recap_docket.pk,
                self.non_recap_docket_2.pk,
            ],
            testing_mode=True,
        )

        # Confirm Dockets are indexed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 3, msg="Wrong number of Dockets returned.")

        # Call sweep_indexer command.
        with mock.patch(
            "cl.search.management.commands.cl_remove_content_from_es.logger"
        ) as mock_logger:
            call_command(
                "cl_remove_content_from_es",
                action="non-recap-dockets",
            )
            mock_logger.info.assert_called_with(
                "Successfully removed 2 non-recap dockets."
            )

        # Confirm non-recap Dockets are removed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 1, msg="Wrong number of Dockets returned.")
        self.assertTrue(DocketDocument.exists(self.recap_docket.pk))

    def test_restart_from_last_document_logged(self, mock_logging_prefix):
        """Confirm the cl_remove_content_from_es is able to resume
        from the last logged docket.
        """

        # Index all the dockets regardless of their source.
        index_dockets_in_bulk.delay(
            [
                self.recap_docket.pk,
                self.non_recap_docket.pk,
                self.non_recap_docket_2.pk,
            ],
            testing_mode=True,
        )

        # Confirm Dockets are indexed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 3, msg="Wrong number of Dockets returned.")

        log_last_document_indexed(
            self.non_recap_docket_2.pk, compose_redis_key_remove_content()
        )
        # Call sweep_indexer command.
        with mock.patch(
            "cl.search.management.commands.cl_remove_content_from_es.logger"
        ) as mock_logger:
            call_command(
                "cl_remove_content_from_es",
                action="non-recap-dockets",
                auto_resume=True,
            )
            mock_logger.info.assert_called_with(
                "Successfully removed 1 non-recap dockets."
            )

        # Confirm the last non-recap Docket is removed.
        s = DocketDocument.search()
        s = s.query(Q("match", docket_child="docket"))
        self.assertEqual(s.count(), 2, msg="Wrong number of Dockets returned.")
        self.assertFalse(DocketDocument.exists(self.non_recap_docket_2.pk))

    def test_remove_opinions_by_timestamp(self, mock_logging_prefix):
        """Confirm the cl_remove_content_from_es command works
        properly removing opinions by a timestamp range query.
        """

        # Opinion Factories
        opinion_cluster_1 = OpinionClusterFactory.create(
            source="C",
            precedential_status="Errata",
            docket=self.recap_docket,
        )
        opinion_1 = OpinionFactory.create(
            extracted_by_ocr=False,
            cluster=opinion_cluster_1,
            type="020lead",
        )

        opinion_cluster_2 = OpinionClusterFactory.create(
            source="C",
            precedential_status="Published",
            docket=self.non_recap_docket,
        )
        opinion_2 = OpinionFactory.create(
            extracted_by_ocr=False,
            cluster=opinion_cluster_2,
            type="010combined",
        )

        five_days_ago = now() - datetime.timedelta(days=5)
        with time_machine.travel(five_days_ago, tick=False):
            # Index all the opinion documents with a timestamp from 5 days ago.
            call_command(
                "cl_index_parent_and_child_docs",
                search_type=SEARCH_TYPES.OPINION,
                pk_offset=0,
                testing_mode=True,
            )

        # Confirm OpinionClusters are indexed
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion_cluster"))
        self.assertEqual(
            s.count(), 2, msg="Wrong number of Clusters returned."
        )
        # Confirm Opinions are indexed.
        s = OpinionDocument.search()
        s = s.query(Q("match", cluster_child="opinion"))
        self.assertEqual(
            s.count(), 2, msg="Wrong number of Opinions returned."
        )

        three_days_ago = now() - datetime.timedelta(days=3)
        with time_machine.travel(three_days_ago, tick=False):
            # Run the sweep indexer to update the timestamp in opinion_2
            log_indexer_last_status(
                "search.Opinion",
                opinion_2.pk,
                0,
            )
            call_command(
                "sweep_indexer",
                testing_mode=True,
            )

        # The timestamp in opinion_2 is updated to 2 days ago.
        opinion_2_doc = OpinionClusterDocument.get(
            ES_CHILD_ID(opinion_2.pk).OPINION
        )
        self.assertEqual(opinion_2_doc.timestamp.date(), three_days_ago.date())

        # Call cl_remove_content_from_es command.
        with mock.patch(
            "cl.search.management.commands.cl_remove_content_from_es.logger"
        ) as mock_logger:
            call_command(
                "cl_remove_content_from_es",
                action="opinions-removal",
                start_date=three_days_ago.date(),
                end_date=now().date(),
                testing_mode=True,
            )
            self.assertIn(
                "Removal task successfully scheduled. Task ID:",
                mock_logger.info.call_args[0][0],
            )

        # Confirm OpinionCluster remains indexed.
        s = OpinionClusterDocument.search()
        s = s.query(Q("match", cluster_child="opinion_cluster"))
        self.assertEqual(
            s.count(), 2, msg="Wrong number of Clusters returned."
        )
        # Confirm only opinion_2 was removed.
        s = OpinionDocument.search()
        s = s.query(Q("match", cluster_child="opinion"))
        self.assertEqual(
            s.count(), 1, msg="Wrong number of Opinions returned."
        )
        self.assertFalse(
            OpinionClusterDocument.exists(ES_CHILD_ID(opinion_2.pk).OPINION)
        )


class OpinionQuerySetWithBestTextTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        court = CourtFactory(
            id="canb",
            jurisdiction="FB",
        )
        cls.opinion_cluster_1 = OpinionClusterFactory(
            docket=DocketFactory(
                court=court,
                docket_number="1:21-cv-1234",
                source=Docket.HARVARD,
            ),
            date_filed=datetime.date(2020, 8, 15),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        cls.opinion_html_with_citations = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            plain_text="Plain text fallback 1",
            html_with_citations="HTML with citations content",
            html_columbia="Other version",
            html_lawbox="Other version",
            xml_harvard="Other version",
            html_anon_2020="Other version",
            html="Other version",
        )
        cls.opinion_html_columbia = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            plain_text="Plain text fallback 2",
            html_with_citations="",
            html_columbia="HTML columbia content",
            html_lawbox="Other version",
            xml_harvard="",
            html_anon_2020="Other version",
            html="Other version",
        )
        cls.opinion_html_lawbox = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            plain_text="Plain text fallback 3",
            html_with_citations="",
            html_columbia="",
            html_lawbox="HTML lawbox content",
            xml_harvard="",
            html_anon_2020="Other version",
            html="Other version",
        )
        cls.opinion_xml_harvard = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            plain_text="Plain text fallback 4",
            html_with_citations="",
            html_columbia="Other version",
            html_lawbox="Other version",
            xml_harvard="XML harvard content",
            html_anon_2020="Other version",
            html="Other version",
        )
        cls.opinion_html_anon_2020 = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            plain_text="Plain text fallback 5",
            html_with_citations="",
            html_columbia="",
            html_lawbox="",
            xml_harvard="",
            html_anon_2020="HTML anon 2020 content",
            html="Other version",
        )
        cls.opinion_html = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            plain_text="Plain text fallback 6",
            html_with_citations="",
            html_columbia="",
            html_lawbox="",
            xml_harvard="",
            html_anon_2020="",
            html="HTML content",
        )
        cls.opinion_plain_text = OpinionFactory(
            cluster=cls.opinion_cluster_1,
            plain_text="Plain text fallback",
            html_with_citations="",
            html_columbia="",
            html_lawbox="",
            xml_harvard="",
            html_anon_2020="",
            html="",
        )

    def test_with_best_text_annotation(self):
        """Test that with_best_text annotates the Opinion queryset with the
        correct  best_text and best_text_source values based on the
        prioritization of OPINION_TEXT_SOURCE_FIELDS.
        """
        qs = Opinion.objects.all().with_best_text()

        o_html_citations = qs.get(pk=self.opinion_html_with_citations.pk)
        o_html_columbia = qs.get(pk=self.opinion_html_columbia.pk)
        o_html_lawbox = qs.get(pk=self.opinion_html_lawbox.pk)
        o_xml_harvard = qs.get(pk=self.opinion_xml_harvard.pk)
        o_html_anon = qs.get(pk=self.opinion_html_anon_2020.pk)
        o_html = qs.get(pk=self.opinion_html.pk)
        o_plain_text = qs.get(pk=self.opinion_plain_text.pk)

        self.assertEqual(
            o_html_citations.best_text, "HTML with citations content"
        )
        self.assertEqual(
            o_html_citations.best_text_source, "html_with_citations"
        )

        self.assertEqual(o_html_columbia.best_text, "HTML columbia content")
        self.assertEqual(o_html_columbia.best_text_source, "html_columbia")

        self.assertEqual(o_html_lawbox.best_text, "HTML lawbox content")
        self.assertEqual(o_html_lawbox.best_text_source, "html_lawbox")

        self.assertEqual(o_xml_harvard.best_text, "XML harvard content")
        self.assertEqual(o_xml_harvard.best_text_source, "xml_harvard")

        self.assertEqual(o_html_anon.best_text, "HTML anon 2020 content")
        self.assertEqual(o_html_anon.best_text_source, "html_anon_2020")

        self.assertEqual(o_html.best_text, "HTML content")
        self.assertEqual(o_html.best_text_source, "html")

        self.assertEqual(o_plain_text.best_text, "Plain text fallback")
        self.assertEqual(o_plain_text.best_text_source, "plain_text")
