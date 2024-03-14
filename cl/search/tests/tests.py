import datetime
import io
import os
from datetime import date
from pathlib import Path
from unittest import mock

import pytz
from asgiref.sync import async_to_sync
from dateutil.tz import tzoffset, tzutc
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from elasticsearch_dsl import Q
from factory import RelatedFactory
from lxml import html
from rest_framework.status import HTTP_200_OK
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from timeout_decorator import timeout_decorator

from cl.audio.factories import AudioFactory
from cl.lib.search_utils import make_fq
from cl.lib.storage import clobbering_get_name
from cl.lib.test_helpers import (
    AudioTestCase,
    CourtTestCase,
    EmptySolrTestCase,
    IndexedSolrTestCase,
    PeopleTestCase,
    SolrTestCase,
)
from cl.lib.utils import (
    cleanup_main_query,
    get_child_court_ids_for_parents,
    modify_court_id_queries,
)
from cl.people_db.factories import PersonFactory, PositionFactory
from cl.recap.constants import COURT_TIMEZONES
from cl.recap.factories import DocketEntriesDataFactory, DocketEntryDataFactory
from cl.recap.mergers import add_docket_entries
from cl.scrapers.factories import PACERFreeDocumentLogFactory
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
from cl.search.management.commands.cl_calculate_pagerank import Command
from cl.search.management.commands.cl_index_parent_and_child_docs import (
    get_unique_oldest_history_rows,
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
    sort_cites,
)
from cl.search.tasks import (
    add_docket_to_solr_by_rds,
    get_es_doc_id_and_parent_id,
)
from cl.search.types import EventTable
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.tests.utils import get_with_wait
from cl.users.factories import UserProfileWithParentsFactory


class UpdateIndexCommandTest(SolrTestCase):
    args = [
        "--type",
        "search.Opinion",
        "--noinput",
    ]

    def _get_result_count(self, results):
        return results.result.numFound

    def test_updating_all_opinions(self) -> None:
        """If we have items in the DB, can we add/delete them to/from Solr?

        This tests is rather long because we need to test adding and deleting,
        and it's hard to setup/dismantle the indexes before/after every test.
        """

        # First, we add everything to Solr.
        args = list(self.args)  # Make a copy of the list.
        args.extend(
            [
                "--solr-url",
                f"{settings.SOLR_HOST}/solr/{self.core_name_opinion}",
                "--update",
                "--everything",
                "--do-commit",
            ]
        )
        call_command("cl_update_index", *args)
        results = self.si_opinion.query("*").execute()
        actual_count = self._get_result_count(results)
        self.assertEqual(
            actual_count,
            self.expected_num_results_opinion,
            msg="Did not get expected number of results.\n"
            "\tGot:\t%s\n\tExpected:\t %s"
            % (
                actual_count,
                self.expected_num_results_opinion,
            ),
        )

        # Check a simple citation query
        results = self.si_opinion.query(cites=self.opinion_3.pk).execute()
        actual_count = self._get_result_count(results)
        expected_citation_count = 2
        self.assertEqual(
            actual_count,
            expected_citation_count,
            msg="Did not get the expected number of citation counts.\n"
            "\tGot:\t %s\n\tExpected:\t%s"
            % (actual_count, expected_citation_count),
        )

        # Next, we delete everything from Solr
        args = list(self.args)  # Make a copy of the list.
        args.extend(
            [
                "--solr-url",
                f"{settings.SOLR_HOST}/solr/{self.core_name_opinion}",
                "--delete",
                "--everything",
                "--do-commit",
            ]
        )
        call_command("cl_update_index", *args)
        results = self.si_opinion.query("*").execute()
        actual_count = self._get_result_count(results)
        expected_citation_count = 0
        self.assertEqual(
            actual_count,
            expected_citation_count,
            msg="Did not get the expected number of counts in empty index.\n"
            "\tGot:\t %s\n\tExpected:\t%s"
            % (actual_count, expected_citation_count),
        )

        # Add things back, but do it by ID
        args = list(self.args)  # Make a copy of the list.
        args.extend(
            [
                "--solr-url",
                f"{settings.SOLR_HOST}/solr/{self.core_name_opinion}",
                "--update",
                "--items",
                f"{self.opinion_1.pk}",
                f"{self.opinion_2.pk}",
                f"{self.opinion_3.pk}",
                "--do-commit",
            ]
        )
        call_command("cl_update_index", *args)
        results = self.si_opinion.query("*").execute()
        actual_count = self._get_result_count(results)
        expected_citation_count = 3
        self.assertEqual(
            actual_count,
            expected_citation_count,
            msg="Did not get the expected number of citation counts.\n"
            "\tGot:\t %s\n\tExpected:\t%s"
            % (actual_count, expected_citation_count),
        )


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
            self.o.save(index=False)
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


class IndexingTest(EmptySolrTestCase):
    """Are things indexed properly?"""

    fixtures = ["test_court.json"]

    def test_issue_729_url_coalescing(self) -> None:
        """Are URL's coalesced properly?"""
        # Save a docket to the backend using coalescing

        test_dir = (
            Path(settings.INSTALL_ROOT)
            / "cl"
            / "assets"
            / "media"
            / "test"
            / "search"
        )
        self.att_filename = "fake_document.html"
        fake_path = os.path.join(test_dir, self.att_filename)

        d = Docket.objects.create(
            source=Docket.RECAP,
            docket_number="asdf",
            pacer_case_id="asdf",
            court_id="test",
        )
        de = DocketEntry.objects.create(docket=d, entry_number=1)
        rd1 = RECAPDocument.objects.create(
            docket_entry=de,
            document_type=RECAPDocument.PACER_DOCUMENT,
            document_number="1",
            pacer_doc_id="1",
            filepath_local=fake_path,
        )
        rd2 = RECAPDocument.objects.create(
            docket_entry=de,
            document_type=RECAPDocument.ATTACHMENT,
            document_number="1",
            attachment_number=1,
            pacer_doc_id="2",
            filepath_local=fake_path,
        )
        # Do the absolute URLs differ when pulled from the DB?
        self.assertNotEqual(rd1.get_absolute_url(), rd2.get_absolute_url())

        add_docket_to_solr_by_rds([rd1.pk, rd2.pk], force_commit=True)

        # Do the absolute URLs differ when pulled from Solr?
        r1 = self.si_recap.get(rd1.pk)
        r2 = self.si_recap.get(rd2.pk)
        self.assertNotEqual(
            r1.result.docs[0]["absolute_url"],
            r2.result.docs[0]["absolute_url"],
        )
        Docket.objects.all().delete()
        DocketEntry.objects.all().delete()
        RECAPDocument.objects.all().delete()


class AdvancedTest(IndexedSolrTestCase):
    """
    Advanced query techniques
    """

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=cls.court, case_name="SUBPOENAS SERVED ON"
            ),
            description="MOTION for Leave to File Amicus Curiae august",
        )
        cls.rd = RECAPDocumentFactory(
            docket_entry=cls.de, description="Leave to File"
        )

        cls.de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=cls.court, case_name="SUBPOENAS SERVED OFF"
            ),
            description="MOTION for Leave to File Amicus Curiae september",
        )
        cls.rd_1 = RECAPDocumentFactory(
            docket_entry=cls.de_1, description="Leave to File"
        )
        super().setUpTestData()

    def test_make_fq(self) -> None:
        """Test make_fq method, checks query formatted is correctly performed."""
        args = (
            {
                "q": "",
                "description": '"leave to file" AND amicus',
            },
            "description",
            "description",
        )
        fq = make_fq(*args)
        self.assertEqual(fq, 'description:("leave to file" AND amicus)')

        args[0]["description"] = '"leave to file" curie'
        fq = make_fq(*args)
        self.assertEqual(fq, 'description:("leave to file" AND curie)')

        args[0]["description"] = '"leave to file" AND "amicus curie"'
        fq = make_fq(*args)
        self.assertEqual(
            fq, 'description:("leave to file" AND "amicus curie")'
        )

        args[0][
            "description"
        ] = '"leave to file" AND "amicus curie" "by august"'
        fq = make_fq(*args)
        self.assertEqual(
            fq,
            'description:("leave to file" AND "amicus curie" AND "by august")',
        )

        args[0][
            "description"
        ] = '"leave to file" AND "amicus curie" OR "by august"'
        fq = make_fq(*args)
        self.assertEqual(
            fq,
            'description:("leave to file" AND "amicus curie" OR "by august")',
        )
        args[0][
            "description"
        ] = '"leave to file" NOT "amicus curie" OR "by august"'
        fq = make_fq(*args)
        self.assertEqual(
            fq,
            'description:("leave to file" NOT "amicus curie" OR "by august")',
        )

        args[0]["description"] = '"leave to file amicus curie"'
        fq = make_fq(*args)
        self.assertEqual(fq, 'description:("leave to file amicus curie")')

        args[0]["description"] = "leave to file AND amicus curie"
        fq = make_fq(*args)
        self.assertEqual(
            fq, "description:(leave AND to AND file AND amicus AND curie)"
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
                html_columbia="<p>Code, &#167; 1-815</p>",
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Lorem.",
            docket=DocketFactory(court=cls.court, docket_number="123456"),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="America vs Bank",
            docket=DocketFactory(
                court=cls.child_court_1, docket_number="34-2535"
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )
        OpinionClusterFactoryWithChildrenAndParents(
            case_name="Johnson v. National",
            docket=DocketFactory(
                court=cls.child_court_2_2, docket_number="36-2000"
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
        )

        OpinionClusterFactoryWithChildrenAndParents(
            case_name="California v. Nevada",
            docket=DocketFactory(
                court=cls.child_gand_2, docket_number="38-1000"
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
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

    def test_get_child_court_ids_for_parents(self) -> None:
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

    def test_modify_court_id_queries(self) -> None:
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

    async def test_filter_parent_child_courts(self) -> None:
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

    async def test_advanced_search_parent_child_courts(self) -> None:
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

    async def test_es_bad_syntax_proximity_tokens(self) -> None:
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

    async def test_es_unbalanced_quotes(self) -> None:
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

    def test_handle_unbalanced_parentheses(self) -> None:
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


class PagerankTest(TestCase):
    fixtures = ["test_objects_search.json", "judge_judy.json"]

    @classmethod
    def setUpTestData(cls) -> None:
        PACERFreeDocumentLogFactory.create()

    def test_pagerank_calculation(self) -> None:
        """Create a few items and fake citation relation among them, then
        run the pagerank algorithm. Check whether this simple case can get the
        correct result.
        """
        # calculate pagerank of these 3 document
        comm = Command()
        self.verbosity = 1
        pr_results = comm.do_pagerank()

        # Verify that whether the answer is correct, based on calculations in
        # Gephi
        answers = {
            1: 0.369323534954,
            2: 0.204581549974,
            3: 0.378475867453,
        }
        for key, value in answers.items():
            self.assertTrue(
                abs(pr_results[key] - value) < 0.0001,
                msg="The answer for item %s was %s when it should have been "
                "%s" % (key, pr_results[key], answers[key]),
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
        UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )
        self.rebuild_index("search.OpinionCluster")
        super().setUp()
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
        )

    def _perform_wildcard_search(self):
        searchbox = self.browser.find_element(By.ID, "id_q")
        searchbox.submit()
        result_count = self.browser.find_element(By.ID, "result-count")
        self.assertIn("Opinions", result_count.text)

    def test_query_cleanup_function(self) -> None:
        # Send string of search_query to the function and expect it
        # to be encoded properly
        q_a = (
            (
                "12-9238 happy Gilmore",
                'docketNumber:"12-9238"~1 happy Gilmore',
            ),
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
        )
        for q, a in q_a:
            print("Does {q} --> {a} ? ".format(**{"q": q, "a": a}))
            self.assertEqual(cleanup_main_query(q), a)

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
        # Dora navitages to CL and does a simple wild card search
        self.browser.get(self.live_server_url)
        self.browser.find_element(By.ID, "id_q").send_keys("voutila")
        self.browser.find_element(By.ID, "id_q").submit()

        # Seeing an Opinion immediately on the first page of results, she
        # wants more details so she clicks the title and drills into the result
        articles = self.browser.find_elements(By.TAG_NAME, "article")
        articles[0].find_elements(By.TAG_NAME, "a")[0].click()

        # She is brought to the detail page for the results
        self.assertNotIn("Search Results", self.browser.title)
        article_text = self.browser.find_element(By.TAG_NAME, "article").text

        # and she can see lots of detail! This includes things like:
        # The name of the jurisdiction/court,
        # the status of the Opinion, any citations, the docket number,
        # the Judges, and a unique fingerpring ID
        meta_data = self.browser.find_elements(
            By.CSS_SELECTOR, ".meta-data-header"
        )
        headers = [
            "Filed:",
            "Precedential Status:",
            "Citations:",
            "Docket Number:",
            "Author:",
            "Nature of suit:",
        ]
        for header in headers:
            self.assertIn(header, [meta.text for meta in meta_data])

        # The complete body of the opinion is also displayed for her to
        # read on the page
        self.assertNotEqual(
            self.browser.find_element(By.ID, "opinion-content").text.strip(),
            "",
        )

        # She wants to dig a big deeper into the influence of this Opinion,
        # so she's able to see links to the first five citations on the left
        # and a link to the full list
        cited_by = self.browser.find_element(By.ID, "cited-by")
        self.assertIn(
            "Cited By", cited_by.find_element(By.TAG_NAME, "h3").text
        )
        citations = cited_by.find_elements(By.TAG_NAME, "li")
        self.assertTrue(0 < len(citations) < 6)

        # She clicks the "Full List of Citations" link and is brought to
        # a SERP page with all the citations, generated by a query
        full_list = cited_by.find_element(By.LINK_TEXT, "View Citing Opinions")
        full_list.click()

        # She notices this submits a new query targeting anything citing the
        # original opinion she was viewing. She notices she's back on the SERP
        self.assertIn("Search Results for", self.browser.title)
        query = self.browser.find_element(By.ID, "id_q").get_attribute("value")
        self.assertIn("cites:", query)

        # She wants to go back to the Opinion page, so she clicks back in her
        # browser, expecting to return to the Opinion details
        self.browser.back()
        self.assertNotIn("Search Results", self.browser.title)
        self.assertEqual(
            self.browser.find_element(By.TAG_NAME, "article").text,
            article_text,
        )

        # She now wants to see details on the list of Opinions cited within
        # this particular opinion. She notices an abbreviated list on the left,
        # and can click into a Full Table of Authorities. (She does so.)
        authorities = self.browser.find_element(By.ID, "authorities")
        self.assertIn(
            "Authorities", authorities.find_element(By.TAG_NAME, "h3").text
        )
        authority_links = authorities.find_elements(By.TAG_NAME, "li")
        self.assertTrue(0 < len(authority_links) < 6)
        self.click_link_for_new_page("View All Authorities")
        self.assertIn("Table of Authorities", self.browser.title)

        # Like before, she's just curious of the list and clicks Back to
        # Document.
        self.click_link_for_new_page("Back to Opinion")

        # And she's back at the Opinion in question and pretty happy about that
        self.assertNotIn("Table of Authorities", self.browser.title)
        self.assertEqual(
            self.browser.find_element(By.TAG_NAME, "article").text,
            article_text,
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

    def test_sweep_indexer_all(self):
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

        s = DocketDocument.search()
        s = s.query("parent_id", type="recap_document", id=self.de_1.docket.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of RECAPDocuments returned."
        )

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

        s = OpinionClusterDocument.search()
        s = s.query("parent_id", type="opinion", id=self.opinion_cluster_2.pk)
        self.assertEqual(
            s.count(), 1, msg="Wrong number of Opinions returned."
        )

    @override_settings(ELASTICSEARCH_SWEEP_INDEXER_ACTION="missing")
    def test_sweep_indexer_missing(self):
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

    def test_restart_from_last_document_logged(self):
        """Confirm the sweep_indexer command can resume from where it left
        off after a failure or interruption.
        """

        # Log last status to simulate a resume from "search.Docket"
        log_indexer_last_status(
            "search.Docket",
            self.de_1.docket.pk,
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
                "search.Docket": 1,
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
