import datetime
import io
import operator
import os
from datetime import date
from functools import reduce
from pathlib import Path
from unittest import mock

import pytz
from dateutil.tz import tzoffset, tzutc
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.test import RequestFactory, override_settings
from django.test.utils import captured_stderr
from django.urls import reverse
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Q, connections
from factory import RelatedFactory
from lxml import etree, html
from rest_framework.status import HTTP_200_OK
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from timeout_decorator import timeout_decorator

from cl.alerts.models import Alert
from cl.alerts.send_alerts import percolate_document
from cl.audio.factories import AudioFactory
from cl.audio.models import Audio
from cl.lib.elasticsearch_utils import (
    build_daterange_query,
    build_es_filters,
    build_es_main_query,
    build_fulltext_query,
    build_sort_results,
    build_term_query,
    group_search_results,
)
from cl.lib.search_utils import cleanup_main_query, make_fq
from cl.lib.storage import clobbering_get_name
from cl.lib.test_helpers import (
    AudioESTestCase,
    AudioTestCase,
    CourtTestCase,
    EmptySolrTestCase,
    ESTestCaseMixin,
    IndexedSolrTestCase,
    SolrTestCase,
)
from cl.people_db.factories import (
    EducationFactory,
    PersonFactory,
    PoliticalAffiliationFactory,
    PositionFactory,
    SchoolFactory,
)
from cl.recap.constants import COURT_TIMEZONES
from cl.recap.factories import DocketEntriesDataFactory, DocketEntryDataFactory
from cl.recap.mergers import add_docket_entries
from cl.scrapers.factories import PACERFreeDocumentLogFactory
from cl.search.documents import (
    PEOPLE_DOCS_TYPE_ID,
    AudioDocument,
    AudioPercolator,
    ParentheticalGroupDocument,
    PersonBaseDocument,
)
from cl.search.factories import (
    CitationWithParentsFactory,
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionsCitedWithParentsFactory,
    OpinionWithChildrenFactory,
    OpinionWithParentsFactory,
    ParentheticalFactory,
    ParentheticalGroupFactory,
    RECAPDocumentFactory,
)
from cl.search.feeds import JurisdictionFeed
from cl.search.management.commands.cl_calculate_pagerank import Command
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Citation,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    RECAPDocument,
    sort_cites,
)
from cl.search.tasks import add_docket_to_solr_by_rds
from cl.search.views import do_search
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import TestCase
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
        except ValueError as e:
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

    def test_a_intersection_query(self) -> None:
        """Does AND queries work"""
        r = self.client.get(reverse("show_results"), {"q": "Howard AND Honda"})
        self.assertIn("Howard", r.content.decode())
        self.assertIn("Honda", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    def test_a_union_query(self) -> None:
        """Does OR queries work"""
        r = self.client.get(
            reverse("show_results"), {"q": "Howard OR Lissner"}
        )
        self.assertIn("Howard", r.content.decode())
        self.assertIn("Lissner", r.content.decode())
        self.assertIn("2 Opinions", r.content.decode())

    def test_query_negation(self) -> None:
        """Does negation query work"""
        r = self.client.get(reverse("show_results"), {"q": "Howard"})
        self.assertIn("Howard", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        r = self.client.get(reverse("show_results"), {"q": "Howard NOT Honda"})
        self.assertIn("had no results", r.content.decode())

        r = self.client.get(reverse("show_results"), {"q": "Howard !Honda"})
        self.assertIn("had no results", r.content.decode())

        r = self.client.get(reverse("show_results"), {"q": "Howard -Honda"})
        self.assertIn("had no results", r.content.decode())

    def test_query_phrase(self) -> None:
        """Can we query by phrase"""
        r = self.client.get(
            reverse("show_results"), {"q": '"Harvey Howard v. Antonin Honda"'}
        )
        self.assertIn("Harvey Howard", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        r = self.client.get(
            reverse("show_results"), {"q": '"Antonin Honda v. Harvey Howard"'}
        )
        self.assertIn("had no results", r.content.decode())

    def test_query_grouped_and_sub_queries(self) -> None:
        """Does grouped and sub queries work"""
        r = self.client.get(
            reverse("show_results"), {"q": "(Lissner OR Honda) AND Howard"}
        )
        self.assertIn("Howard", r.content.decode())
        self.assertIn("Honda", r.content.decode())
        self.assertIn("Lissner", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    def test_query_fielded(self) -> None:
        """Does fielded queries work"""
        r = self.client.get(
            reverse("show_results"), {"q": "status:precedential"}
        )
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("2 Opinions", r.content.decode())

    def test_a_wildcard_query(self) -> None:
        """Does a wildcard query work"""
        r = self.client.get(reverse("show_results"), {"q": "Ho*"})
        self.assertIn("Howard", r.content.decode())
        self.assertIn("Honda", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        r = self.client.get(reverse("show_results"), {"q": "?owa*"})
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    def test_a_fuzzy_query(self) -> None:
        """Does a fuzzy query work"""
        r = self.client.get(reverse("show_results"), {"q": "ond~"})
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("2 Opinions", r.content.decode())

    def test_proximity_query(self) -> None:
        """Does a proximity query work"""
        r = self.client.get(
            reverse("show_results"), {"q": "'Testing Court'~3"}
        )
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    def test_range_query(self) -> None:
        """Does a range query work"""
        r = self.client.get(
            reverse("show_results"), {"q": "citation:([22 TO 33])"}
        )
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("2 Opinions", r.content.decode())

    def test_date_query(self) -> None:
        """Does a date query work"""
        r = self.client.get(
            reverse("show_results"),
            {"q": "dateFiled:[2015-01-01T00:00:00Z TO 2015-12-31T00:00:00Z]"},
        )
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

        r = self.client.get(
            reverse("show_results"),
            {"q": "dateFiled:[1895-01-01T00:00:00Z TO 2015-12-31T00:00:00Z]"},
        )
        self.assertIn("docket number 2", r.content.decode())
        self.assertIn("docket number 3", r.content.decode())
        self.assertIn("2 Opinions", r.content.decode())

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

    def test_phrase_plus_conjunction_search(self) -> None:
        """Confirm phrase + conjunction search works properly"""

        add_docket_to_solr_by_rds([self.rd.pk], force_commit=True)
        add_docket_to_solr_by_rds([self.rd_1.pk], force_commit=True)
        params = {
            "q": "",
            "description": '"leave to file" AND amicus',
            "type": SEARCH_TYPES.RECAP,
        }
        r = self.client.get(
            reverse("show_results"),
            params,
        )
        self.assertIn("2 Cases", r.content.decode())
        self.assertIn("SUBPOENAS SERVED ON", r.content.decode())

        params["description"] = '"leave to file" amicus'
        r = self.client.get(
            reverse("show_results"),
            params,
        )
        self.assertIn("2 Cases", r.content.decode())
        self.assertIn("SUBPOENAS SERVED ON", r.content.decode())

        params["description"] = '"leave to file" AND "amicus"'
        r = self.client.get(
            reverse("show_results"),
            params,
        )
        self.assertIn("2 Cases", r.content.decode())
        self.assertIn("SUBPOENAS SERVED ON", r.content.decode())

        params[
            "description"
        ] = '"leave to file" AND "amicus" "Curiae september"'
        r = self.client.get(
            reverse("show_results"),
            params,
        )
        self.assertIn("1 Case", r.content.decode())
        self.assertIn("SUBPOENAS SERVED OFF", r.content.decode())


class SearchTest(IndexedSolrTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
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
        super().setUpTestData()

    @staticmethod
    def get_article_count(r):
        """Get the article count in a query response"""
        return len(html.fromstring(r.content.decode()).xpath("//article"))

    def test_a_simple_text_query(self) -> None:
        """Does typing into the main query box work?"""
        r = self.client.get(reverse("show_results"), {"q": "supreme"})
        self.assertIn("Honda", r.content.decode())
        self.assertIn("1 Opinion", r.content.decode())

    def test_a_case_name_query(self) -> None:
        """Does querying by case name work?"""
        r = self.client.get(
            reverse("show_results"), {"q": "*", "case_name": "honda"}
        )
        self.assertIn("Honda", r.content.decode())

    def test_a_query_with_white_space_only(self) -> None:
        """Does everything work when whitespace is in various fields?"""
        r = self.client.get(
            reverse("show_results"), {"q": " ", "judge": " ", "case_name": " "}
        )
        self.assertIn("Honda", r.content.decode())
        self.assertNotIn("an error", r.content.decode())

    def test_a_query_with_a_date(self) -> None:
        """Does querying by date work?"""
        response = self.client.get(
            reverse("show_results"),
            {"q": "*", "filed_after": "1895-06", "filed_before": "1896-01"},
        )
        text = response.content.decode()
        print(text)
        self.assertIn("Honda", response.content.decode())

    def test_faceted_queries(self) -> None:
        """Does querying in a given court return the document? Does querying
        the wrong facets exclude it?
        """
        r = self.client.get(
            reverse("show_results"), {"q": "*", "court_test": "on"}
        )
        self.assertIn("Honda", r.content.decode())
        r = self.client.get(
            reverse("show_results"), {"q": "*", "stat_Errata": "on"}
        )
        self.assertNotIn("Honda", r.content.decode())
        self.assertIn("Debbas", r.content.decode())

    def test_a_docket_number_query(self) -> None:
        """Can we query by docket number?"""
        r = self.client.get(
            reverse("show_results"), {"q": "*", "docket_number": "2"}
        )
        self.assertIn(
            "Honda", r.content.decode(), "Result not found by docket number!"
        )

    def test_a_west_citation_query(self) -> None:
        """Can we query by citation number?"""
        get_dicts = [{"q": "*", "citation": "33"}, {"q": "citation:33"}]
        for get_dict in get_dicts:
            r = self.client.get(reverse("show_results"), get_dict)
            self.assertIn("Honda", r.content.decode())

    def test_a_neutral_citation_query(self) -> None:
        """Can we query by neutral citation numbers?"""
        r = self.client.get(
            reverse("show_results"), {"q": "*", "neutral_cite": "22"}
        )
        self.assertIn("Honda", r.content.decode())

    def test_a_query_with_a_old_date(self) -> None:
        """Do we have any recurrent issues with old dates and strftime (issue
        220)?"""
        r = self.client.get(
            reverse("show_results"), {"q": "*", "filed_after": "1890"}
        )
        self.assertEqual(200, r.status_code)

    def test_a_judge_query(self) -> None:
        """Can we query by judge name?"""
        r = self.client.get(
            reverse("show_results"), {"q": "*", "judge": "david"}
        )
        self.assertIn("Honda", r.content.decode())
        r = self.client.get(reverse("show_results"), {"q": "judge:david"})
        self.assertIn("Honda", r.content.decode())

    def test_a_nature_of_suit_query(self) -> None:
        """Can we query by nature of suit?"""
        r = self.client.get(
            reverse("show_results"), {"q": 'suitNature:"copyright"'}
        )
        self.assertIn("Honda", r.content.decode())

    def test_citation_filtering(self) -> None:
        """Can we find Documents by citation filtering?"""
        r = self.client.get(
            reverse("show_results"), {"q": "*", "cited_lt": 7, "cited_gt": 5}
        )
        self.assertIn(
            "Honda",
            r.content.decode(),
            msg="Did not get case back when filtering by citation count.",
        )
        r = self.client.get("/", {"q": "*", "cited_lt": 100, "cited_gt": 80})
        self.assertIn(
            "had no results",
            r.content.decode(),
            msg="Got case back when filtering by crazy citation count.",
        )

    def test_citation_ordering(self) -> None:
        """Can the results be re-ordered by citation count?"""
        r = self.client.get(
            reverse("show_results"), {"q": "*", "order_by": "citeCount desc"}
        )
        most_cited_name = "case name cluster 3"
        less_cited_name = "Howard v. Honda"
        self.assertTrue(
            r.content.decode().index(most_cited_name)
            < r.content.decode().index(less_cited_name),
            msg="'%s' should come BEFORE '%s' when ordered by descending "
            "citeCount." % (most_cited_name, less_cited_name),
        )

        r = self.client.get("/", {"q": "*", "order_by": "citeCount asc"})
        self.assertTrue(
            r.content.decode().index(most_cited_name)
            > r.content.decode().index(less_cited_name),
            msg="'%s' should come AFTER '%s' when ordered by ascending "
            "citeCount." % (most_cited_name, less_cited_name),
        )

    def test_random_ordering(self) -> None:
        """Can the results be ordered randomly?

        This test is difficult since we can't check that things actually get
        ordered randomly, but we can at least make sure the query succeeds.
        """
        r = self.client.get(
            reverse("show_results"), {"q": "*", "order_by": "random_123 desc"}
        )
        self.assertNotIn("an error", r.content.decode())

    def test_homepage(self) -> None:
        """Is the homepage loaded when no GET parameters are provided?"""
        response = self.client.get(reverse("show_results"))
        self.assertIn(
            'id="homepage"',
            response.content.decode(),
            msg="Did not find the #homepage id when attempting to "
            "load the homepage",
        )

    def test_fail_gracefully(self) -> None:
        """Do we fail gracefully when an invalid search is created?"""
        response = self.client.get(
            reverse("show_results"), {"neutral_cite": "-"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "an error",
            response.content.decode(),
            msg="Invalid search did not result in an error.",
        )

    def test_issue_635_leading_zeros(self) -> None:
        """Do queries with leading zeros work equal to ones without?"""
        r = self.client.get(
            reverse("show_results"),
            {"docket_number": "005", "stat_Errata": "on"},
        )
        expected = 1
        self.assertEqual(expected, self.get_article_count(r))
        r = self.client.get(
            reverse("show_results"),
            {"docket_number": "5", "stat_Errata": "on"},
        )
        self.assertEqual(expected, self.get_article_count(r))

    def test_issue_1193_docket_numbers_as_phrase(self) -> None:
        """Are docket numbers searched as a phrase?"""
        # Search for the full docket number. Does it work?
        r = self.client.get(
            reverse("show_results"),
            {"docket_number": "docket number 1 005", "stat_Errata": "on"},
        )
        expected = 1
        got = self.get_article_count(r)
        self.assertEqual(
            expected,
            got,
            "Didn't get the expected result count of '%s' for docket "
            "phrase search. Got '%s' instead." % (expected, got),
        )

        # Twist up the docket numbers. Do we get no results?
        r = self.client.get(
            reverse("show_results"),
            {"docket_number": "docket 005 number", "stat_Errata": "on"},
        )
        expected = 0
        self.assertEqual(
            expected,
            self.get_article_count(r),
            "Got results for badly ordered docket number.",
        )

    def test_issue_727_doc_att_numbers(self) -> None:
        """Can we send integers to the document number and attachment number
        fields?
        """
        r = self.client.get(
            reverse("show_results"),
            {"type": SEARCH_TYPES.RECAP, "document_number": "1"},
        )
        self.assertEqual(r.status_code, HTTP_200_OK)
        r = self.client.get(
            reverse("show_results"),
            {"type": SEARCH_TYPES.RECAP, "attachment_number": "1"},
        )
        self.assertEqual(r.status_code, HTTP_200_OK)

    def test_issue_1296_abnormal_citation_type_queries(self) -> None:
        """Does search work OK when there are supra, id, or non-opinion
        citations in the query?
        """
        params = (
            {"type": SEARCH_TYPES.OPINION, "q": "42 U.S.C. § ·1383a(a)(3)(A)"},
            {"type": SEARCH_TYPES.OPINION, "q": "supra, at 22"},
        )
        for param in params:
            r = self.client.get(reverse("show_results"), param)
            self.assertEqual(
                r.status_code,
                HTTP_200_OK,
                msg=f"Didn't get good status code with params: {param}",
            )

    def test_rendering_unicode_o_text(self) -> None:
        """Does unicode HTML unicode is properly rendered in search results?"""
        r = self.client.get(
            reverse("show_results"), {"q": "*", "case_name": "Washington"}
        )
        self.assertIn("Code, §", r.content.decode())

    def test_docket_number_proximity_query(self) -> None:
        """Test docket_number proximity query, so that docket numbers like
        1:21-cv-1234 can be matched by queries like: 21-1234
        """

        # Query 21-1234, return results for 1:21-bk-1234
        search_params = {"type": SEARCH_TYPES.OPINION, "q": "21-1234"}
        r = self.client.get(reverse("show_results"), search_params)
        actual = self.get_article_count(r)
        self.assertEqual(actual, 1)
        self.assertIn("Washington", r.content.decode())

        # Query 1:21-cv-1234
        search_params["q"] = "1:21-cv-1234"
        r = self.client.get(reverse("show_results"), search_params)
        actual = self.get_article_count(r)
        self.assertEqual(actual, 1)
        self.assertIn("Washington", r.content.decode())

        # docket_number box filter: 21-1234, return results for 1:21-bk-1234
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "docket_number": f"21-1234",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Washington", r.content.decode())

    def test_docket_number_suffixes_query(self) -> None:
        """Test docket_number with suffixes can be found."""

        # Indexed: 1:21-cv-1234 -> Search: 1:21-cv-1234-ABC
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": f"1:21-cv-1234-ABC",
        }
        r = self.client.get(reverse("show_results"), search_params)
        actual = self.get_article_count(r)
        self.assertEqual(actual, 1)
        self.assertIn("Washington", r.content.decode())

        # Other kind of formats can still be searched -> 123456
        search_params = {
            "type": SEARCH_TYPES.OPINION,
            "q": "123456",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Lorem", r.content.decode())


@override_settings(
    # MLT results should not be cached
    RELATED_USE_CACHE=False,
    # Default MLT settings limit the search space to minimize run time.
    # These limitations are not needed on the small document collections during
    # testing.
    RELATED_MLT_MINTF=0,
    RELATED_MLT_MAXQT=9999,
    RELATED_MLT_MINWL=0,
)
class RelatedSearchTest(IndexedSolrTestCase):
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

        # disable all status filters (otherwise results do not match detail page)
        params.update(
            {f"stat_{v}": "on" for s, v in PRECEDENTIAL_STATUS.NAMES}
        )

        r = self.client.get(reverse("show_results"), params)
        self.assertEqual(r.status_code, HTTP_200_OK)

        self.assertEqual(
            expected_article_count, SearchTest.get_article_count(r)
        )
        self.assertTrue(
            r.content.decode().index("/opinion/%i/" % expected_first_pk)
            < r.content.decode().index("/opinion/%i/" % expected_second_pk),
            msg="'Howard v. Honda' should come AFTER 'case name cluster 3'.",
        )

    def test_more_like_this_opinion_detail_detail(self) -> None:
        """MoreLikeThis query on opinion detail page with status filter"""
        seed_pk = self.opinion_cluster_3.pk  # case name cluster 3
        expected_first_pk = self.opinion_2.pk  # Howard v. Honda

        # Login as staff user (related items are by default disabled for guests)
        self.assertTrue(
            self.client.login(username="admin", password="password")
        )

        r = self.client.get("/opinion/%i/asdf/" % seed_pk)
        self.assertEqual(r.status_code, 200)

        # Test if related opinion exist
        self.assertGreater(
            r.content.decode().index(
                "'clickRelated_mlt_seed%i', %i," % (seed_pk, expected_first_pk)
            ),
            0,
            msg="Related opinion not found.",
        )
        self.client.logout()

    @override_settings(RELATED_FILTER_BY_STATUS=None)
    def test_more_like_this_opinion_detail_no_filter(self) -> None:
        """MoreLikeThis query on opinion detail page (without filter)"""
        seed_pk = self.opinion_cluster_1.pk  # Paul Debbas v. Franklin
        expected_first_pk = self.opinion_2.pk  # Howard v. Honda
        expected_second_pk = self.opinion_3.pk  # case name cluster 3

        # Login as staff user (related items are by default disabled for guests)
        self.assertTrue(
            self.client.login(username="admin", password="password")
        )

        r = self.client.get("/opinion/%i/asdf/" % seed_pk)
        self.assertEqual(r.status_code, 200)

        # Test for click tracking order
        self.assertTrue(
            r.content.decode().index(
                "'clickRelated_mlt_seed%i', %i," % (seed_pk, expected_first_pk)
            )
            < r.content.decode().index(
                "'clickRelated_mlt_seed%i', %i,"
                % (seed_pk, expected_second_pk)
            ),
            msg="Related opinions are in wrong order.",
        )
        self.client.logout()


class GroupedSearchTest(EmptySolrTestCase):
    fixtures = ["opinions-issue-550.json"]

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
        self.factory = RequestFactory()

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


class JudgeSearchTest(IndexedSolrTestCase):
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
            r.content.decode().index("Susan")
            < r.content.decode().index("Olivia"),
            msg="'Susan' should come BEFORE 'Olivia'.",
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

        # Combine fields in advanced search.
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


class FeedTest(IndexedSolrTestCase):
    def test_jurisdiction_feed(self) -> None:
        """Can we simply load the jurisdiction feed?"""
        response = self.client.get(
            reverse("jurisdiction_feed", kwargs={"court": "test"})
        )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for jurisdiction feed",
        )
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ("//a:feed/a:entry", 5),
            ("//a:feed/a:entry/a:title", 5),
        )
        for test, expected_count in node_tests:
            actual_count = len(
                xml_tree.xpath(
                    test, namespaces={"a": "http://www.w3.org/2005/Atom"}
                )
            )
            self.assertEqual(
                actual_count,
                expected_count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (expected_count, test, actual_count),
            )


@override_settings(
    MEDIA_ROOT=os.path.join(settings.INSTALL_ROOT, "cl/assets/media/test/")
)
class JurisdictionFeedTest(TestCase):
    def setUp(self) -> None:
        self.good_item = {
            "title": "Opinion Title",
            "court": "SCOTUS",
            "absolute_url": "http://absolute_url",
            "caseName": "Case Name",
            "status": "Precedential",
            "dateFiled": date(2015, 12, 25),
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
        super(JurisdictionFeedTest, self).setUp()

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

        court = Court.objects.get(pk="test")
        request = HttpRequest()
        request.user = AnonymousUser()
        request.path = "/feed"
        try:
            feed = FakeFeed().get_feed(court, request)
            xml = feed.writeString("utf-8")
            self.assertIn(
                'feed xml:lang="en-us" xmlns="http://www.w3.org/2005/Atom',
                xml,
            )
        except Exception as e:
            self.fail(f"Could not call get_feed(): {e}")


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
        super().setUp()

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
        prec = self.browser.find_element(By.ID, "id_stat_Precedential")
        non_prec = self.browser.find_element(By.ID, "id_stat_Non-Precedential")
        self.assertEqual(prec.get_attribute("checked"), "true")
        self.assertIsNone(non_prec.get_attribute("checked"))
        prec_count = self.browser.find_element(
            By.CSS_SELECTOR, 'label[for="id_stat_Precedential"]'
        )
        non_prec_count = self.browser.find_element(
            By.CSS_SELECTOR, 'label[for="id_stat_Non-Precedential"]'
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

        sign_out = get_with_wait(wait, (By.LINK_TEXT, "Sign out"))
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

    def test_simple_caption(self) -> None:
        c, _ = Court.objects.get_or_create(pk="ca1", defaults={"position": 1})
        d = Docket.objects.create(source=0, court=c)
        cluster = OpinionCluster.objects.create(
            case_name="foo", docket=d, date_filed=date(1984, 1, 1)
        )
        Citation.objects.create(
            cluster=cluster,
            type=Citation.FEDERAL,
            volume=22,
            reporter="F.2d",
            page="44",
        )
        self.assertEqual(
            "foo, 22 F.2d 44&nbsp;(1st&nbsp;Cir.&nbsp;1984)", cluster.caption
        )

    def test_scotus_caption(self) -> None:
        c, _ = Court.objects.get_or_create(
            pk="scotus", defaults={"position": 2}
        )
        d = Docket.objects.create(source=0, court=c)
        cluster = OpinionCluster.objects.create(
            case_name="foo", docket=d, date_filed=date(1984, 1, 1)
        )
        Citation.objects.create(
            cluster=cluster,
            type=Citation.FEDERAL,
            volume=22,
            reporter="U.S.",
            page="44",
        )
        self.assertEqual("foo, 22 U.S. 44", cluster.caption)

    def test_neutral_cites(self) -> None:
        c, _ = Court.objects.get_or_create(pk="ca1", defaults={"position": 1})
        d = Docket.objects.create(source=0, court=c)
        cluster = OpinionCluster.objects.create(
            case_name="foo", docket=d, date_filed=date(1984, 1, 1)
        )
        Citation.objects.create(
            cluster=cluster,
            type=Citation.NEUTRAL,
            volume=22,
            reporter="IL",
            page="44",
        )
        self.assertEqual("foo, 22 IL 44", cluster.caption)

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


def is_es_online(connection_alias="default"):
    """Validate that ES instance is online
    :param connection_alias: Name of connection to use
    :return: True or False
    """
    with captured_stderr():
        es = connections.get_connection(connection_alias)
        return es.ping()


class ElasticSearchTest(TestCase):
    fixtures = ["test_court.json"]

    # Mock ElasticSearch search and responses are difficult due to its implementation,
    # that's why we skip testing if Elasticsearch instance is offline, this can be
    # fixed by implementing the service in Github actions or using external library to
    # Mock elasticsearch like: ElasticMock

    @classmethod
    def rebuild_index(self):
        """
        Create and populate the Elasticsearch index and mapping
        """

        # -f rebuilds index without prompt for confirmation
        call_command("search_index", "--rebuild", "-f")

    @classmethod
    def setUpTestData(cls):
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

        cls.rebuild_index()

    # Notes:
    # "term" Returns documents that contain an exact term in a provided field.
    # "match" Returns documents that match a provided text, number, date or boolean
    # value. The provided text is analyzed before matching.

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
        """Test filter and then ordering by descending
        dateFiled"""
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

        q1 = build_fulltext_query(["representative_text"], "responsibility")
        s = ParentheticalGroupDocument.search().filter(q1)
        self.assertEqual(s.count(), 1)

    def test_build_terms_query(self) -> None:
        """Test build es terms query"""
        filters = []
        q = build_term_query(
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
        cd = {
            "filed_after": "",
            "filed_before": "",
            "q": "",
            "type": SEARCH_TYPES.PARENTHETICAL,
        }

        filters = build_es_filters(cd)

        if not filters:
            # Return all results
            s = ParentheticalGroupDocument.search().query("match_all")
            self.assertEqual(s.count(), 4)

    def test_docker_number_filter(self) -> None:
        """Test filter by docker_number"""
        filters = []

        filters.append(Q("term", docketNumber="1:98-cr-35856"))

        s = ParentheticalGroupDocument.search().filter(
            reduce(operator.iand, filters)
        )
        self.assertEqual(s.count(), 1)

    def test_build_sort(self) -> None:
        """Test we can build sort dict and sort ES query"""
        cd = {"order_by": "dateFiled desc", "type": SEARCH_TYPES.PARENTHETICAL}
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

        cd = {"order_by": "dateFiled asc", "type": SEARCH_TYPES.PARENTHETICAL}
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

        cd = {"order_by": "score desc", "type": SEARCH_TYPES.PARENTHETICAL}
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

        cd = {"type": SEARCH_TYPES.PARENTHETICAL, "q": ""}
        q1 = build_fulltext_query(["representative_text"], "Necessary")
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
        self.assertEqual(type(results[0].dateArgued), datetime.datetime)
        self.assertEqual(type(results[0].dateFiled), datetime.datetime)
        self.assertEqual(type(results[0].dateReargued), datetime.datetime)
        self.assertEqual(
            type(results[0].dateReargumentDenied), datetime.datetime
        )
        self.assertEqual(type(results[0].docket_id), int)
        self.assertEqual(type(results[0].docketNumber), str)
        self.assertEqual(type(results[0].joined_by_ids[0]), int)
        self.assertEqual(type(results[0].judge), str)
        self.assertEqual(type(results[0].lexisCite), str)
        self.assertEqual(type(results[0].neutralCite), str)
        self.assertEqual(type(results[0].panel_ids[0]), int)
        self.assertEqual(type(results[0].scdb_id), str)
        self.assertEqual(type(results[0].status), str)
        self.assertEqual(type(results[0].suitNature), str)

    def test_pa_search_form_search_and_filtering(self) -> None:
        """Test Parenthetical search directly from the form."""
        r = self.client.get(
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

        r = self.client.get(
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
        r = self.client.get(
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
        r = self.client.get(
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

        add_docket_entries(self.d_cand, self.de_date_data["docket_entries"])
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
        add_docket_entries(self.d_cand, self.de_utc_data["docket_entries"])

        # Add docket entries with a different time offset than UTC datetime
        add_docket_entries(self.d_cand, self.de_pdt_data["docket_entries"])

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
        add_docket_entries(self.d_nyed, self.de_utc_data["docket_entries"])

        # Add docket entries with a different time offset than UTC datetime
        add_docket_entries(self.d_nyed, self.de_pdt_data["docket_entries"])

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
        add_docket_entries(self.d_cand, self.de_utc_data["docket_entries"])

        de_cand = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        # Compare both dates are stored in local court timezone PDT for CAND
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

        # Add docket entries with null date_filed
        add_docket_entries(self.d_cand, self.de_no_date["docket_entries"])
        de_cand.refresh_from_db()
        # Docket entry date_filed and time_filed are remain the same
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

    def test_update_docket_entries_with_no_time_data(self):
        """Does time_filed is set to None only when the new date_filed doesn't
        contain time data and the date differs from the previous one?
        """

        # Add docket entries with UTC datetime for CAND
        add_docket_entries(self.d_cand, self.de_utc_data["docket_entries"])

        de_cand = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        # Compare both dates are stored in local court timezone PDT for CAND
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

        # Add docket entries without time data but same date
        add_docket_entries(self.d_cand, self.de_date_data["docket_entries"])
        de_cand.refresh_from_db()
        # Avoid updating date-time if the date doesn't change
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

        # Add docket entries without time data but different date
        add_docket_entries(
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
        add_docket_entries(self.d_cand, self.de_utc_data["docket_entries"])

        de_cand = DocketEntry.objects.get(
            docket__court=self.cand, entry_number=1
        )
        # Compare both dates are stored in local court timezone PDT for CAND
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 46, 51))

        # Add docket entries with UTC datetime for CAND, time changes,
        # date remains the same
        add_docket_entries(
            self.d_cand, self.de_utc_changes_time["docket_entries"]
        )
        de_cand.refresh_from_db()
        # Time is properly updated.
        self.assertEqual(de_cand.date_filed, datetime.date(2021, 10, 15))
        self.assertEqual(de_cand.time_filed, datetime.time(19, 50, 11))

        # Add docket entries with UTC datetime for CAND, date and time change.
        add_docket_entries(
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
        add_docket_entries(self.d_cand, self.de_utc_data["docket_entries"])
        add_docket_entries(self.d_cand, self.de_pdt_data["docket_entries"])

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
        add_docket_entries(self.d_nyed, self.de_utc_data["docket_entries"])
        add_docket_entries(self.d_nyed, self.de_pdt_data["docket_entries"])

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
        add_docket_entries(
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
        add_docket_entries(
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


class OASearchTestElasticSearch(ESTestCaseMixin, AudioESTestCase, TestCase):
    """Oral argument search tests for Elasticsearch"""

    @classmethod
    def rebuild_index(self):
        """
        Create and populate the Elasticsearch index and mapping
        """

        # -f rebuilds index without prompt for confirmation
        call_command("search_index", "--rebuild", "-f")

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rebuild_index()

    @classmethod
    def tearDownClass(cls):
        Audio.objects.all().delete()
        super().tearDownClass()

    @staticmethod
    def get_article_count(r):
        """Get the article count in a query response"""
        return len(html.fromstring(r.content.decode()).xpath("//article"))

    @staticmethod
    def get_results_count(r):
        """Get the result count in a API query response"""
        return len(r.data["results"])

    @staticmethod
    def confirm_query_matched(response, query_id) -> bool:
        """Confirm if a percolator query matched."""

        matched = False
        for hit in response:
            if hit.meta.id == query_id:
                matched = True
        return matched

    @staticmethod
    def save_percolator_query(cd):
        search_query = AudioDocument.search()
        query, total_query_results, top_hits_limit = build_es_main_query(
            search_query, cd
        )
        query_dict = query.to_dict()["query"]
        percolator_query = AudioPercolator(
            percolator_query=query_dict, rate=Alert.REAL_TIME
        )
        percolator_query.save()

        return percolator_query.meta.id

    @staticmethod
    def prepare_document(document):
        audio_doc = AudioDocument()
        return audio_doc.prepare(document)

    def test_oa_results_basic(self) -> None:
        # Frontend
        r = self.client.get(
            reverse("show_results"), {"type": SEARCH_TYPES.ORAL_ARGUMENT}
        )
        self.assertIn("Jose", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            {"type": SEARCH_TYPES.ORAL_ARGUMENT},
        )
        self.assertIn("Jose", r.content.decode())

    def test_oa_results_date_argued_ordering(self) -> None:
        # Order by dateArgued desc
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "dateArgued desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertTrue(
            r.content.decode().index("SEC") < r.content.decode().index("Jose"),
            msg="'SEC' should come BEFORE 'Jose' when order_by desc.",
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        self.assertTrue(
            r.content.decode().index("SEC") < r.content.decode().index("Jose"),
            msg="'SEC' should come BEFORE 'Jose' when order_by desc.",
        )

        # Order by dateArgued asc
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "dateArgued asc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertTrue(
            r.content.decode().index("Jose") < r.content.decode().index("SEC"),
            msg="'Jose' should come AFTER 'SEC' when order_by asc.",
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        self.assertTrue(
            r.content.decode().index("Jose") < r.content.decode().index("SEC"),
            msg="'Jose' should come AFTER 'SEC' when order_by asc.",
        )

    def test_oa_results_relevance_ordering(self) -> None:
        # Relevance order, single word match.
        search_params = {
            "q": "Loretta",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Jose")
            < r.content.decode().index("Hong Liu"),
            msg="'Jose' should come BEFORE 'Hong Liu' when order_by relevance.",
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Jose")
            < r.content.decode().index("Hong Liu"),
            msg="'Jose' should come BEFORE 'Hong Liu' when order_by relevance.",
        )

    def test_oa_results_search_match_phrase(self) -> None:
        # Search by phrase that only matches one result.
        search_params = {
            "q": "Hong Liu Lorem",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        expected = 1
        self.assertEqual(actual, expected)

    def test_oa_results_search_in_text(self) -> None:
        # Text query search by docket number
        search_params = {
            "q": f"{self.audio_3.docket.docket_number}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Lorem")
            < r.content.decode().index("Yang"),
            msg="'Lorem' should come BEFORE 'Yang' when order_by relevance.",
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Lorem")
            < r.content.decode().index("Yang"),
            msg="'Lorem' should come BEFORE 'Yang' when order_by relevance.",
        )

        # Text query combine case name and docket name.
        search_params = {
            "q": f"Lorem {self.audio_3.docket.docket_number}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)

        # Text query search by Judge in text.
        search_params = {
            "q": "John Smith",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)

        # Text query search by Court in text.
        search_params = {
            "q": f"{self.audio_3.docket.court.pk}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)

        # Text query search by sha1 in text.
        search_params = {
            "q": self.audio_1.sha1,
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)

    def test_oa_results_highlights(self) -> None:
        # Case name highlights
        r = self.client.get(
            reverse("show_results"),
            {
                "q": "Hong Liu Yang",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "order_by": "score desc",
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Hong</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Hong</mark>"), 2)

        # Docket number highlights
        r = self.client.get(
            reverse("show_results"),
            {
                "q": f"{self.audio_2.docket.docket_number}",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "order_by": "score desc",
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>19", r.content.decode())

        # Judge highlights
        r = self.client.get(
            reverse("show_results"),
            {
                "q": "John Smith",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "order_by": "score desc",
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>John</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>John</mark>"), 2)

        # Court citation string highlights
        r = self.client.get(
            reverse("show_results"),
            {
                "q": "Freedom of Inform Wikileaks (Bankr. C.D. Cal. 2013)",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "order_by": "score desc",
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Bankr.</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Bankr.</mark>"), 2)

    def test_oa_case_name_filtering(self) -> None:
        """Filter by case_name"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "case_name": "jose",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

    def test_oa_docket_number_filtering(self) -> None:
        """Filter by docket number"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": f"{self.audio_1.docket.docket_number}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "docket number. Expected %s, but got %s." % (expected, actual),
        )
        self.assertIn("SEC", r.content.decode())

        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "docket number. Expected %s, but got %s." % (expected, actual),
        )
        self.assertIn("SEC", r.content.decode())

    def test_oa_jurisdiction_filtering(self) -> None:
        """Filter by court"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "court": f"{self.audio_3.docket.court.pk}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "jurisdiction. Expected %s, but got %s." % (expected, actual),
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "jurisdiction. Expected %s, but got %s." % (expected, actual),
        )

    def test_oa_date_argued_filtering(self) -> None:
        """Filter by date_argued"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "argued_after": "2015-08-16",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertNotIn(
            "an error",
            r.content.decode(),
            msg="Got an error when doing a Date Argued filter.",
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "argued_after. Expected %s, but got %s." % (actual, expected),
        )
        self.assertIn(
            "SEC v. Frank J. Information, WikiLeaks",
            r.content.decode(),
            msg="Did not get the expected oral argument.",
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "argued_after. Expected %s, but got %s." % (actual, expected),
        )
        self.assertIn(
            "SEC v. Frank J. Information, WikiLeaks",
            r.content.decode(),
            msg="Did not get the expected oral argument.",
        )

    def test_oa_combine_search_and_filtering(self) -> None:
        """Test combine text query and filtering"""
        # Text query
        search_params = {
            "q": "Loretta",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

        # Text query filtered by case_name
        search_params = {
            "q": "Loretta",
            "case_name": "Hong Liu",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

        # Text query filtered by case_name and judge
        search_params = {
            "q": "Loretta",
            "case_name": "Hong Liu",
            "judge": "John Smith",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

    def test_oa_advanced_search_not_query(self) -> None:
        """Test advanced search queries"""
        # NOT query
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Loretta NOT (Hong Liu)",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose A.", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Jose A.", r.content.decode())

    def test_oa_advanced_search_and_query(self) -> None:
        # AND query
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Loretta AND judge:John Smith",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem v. Lynch", r.content.decode())
        self.assertIn("John Smith", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem v. Lynch", r.content.decode())
        self.assertIn("John Smith", r.content.decode())

    def test_oa_advanced_search_or_and_query(self) -> None:
        # Grouped "OR" query and "AND" query
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "(Loretta OR SEC) AND Jose",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

    def test_oa_advanced_search_by_field(self) -> None:
        # Query by docket_id advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"docket_id:{self.audio_1.docket.pk}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank", r.content.decode())

        # Query by id advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"id:{self.audio_4.pk}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem", r.content.decode())

        # Query by court_id advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"court_id:{self.audio_3.docket.court_id}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Yang v. Lynch-Loretta E", r.content.decode())
        self.assertIn("Hong Liu Lorem v. Lynch-Loretta E.", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Yang v. Lynch-Loretta E", r.content.decode())
        self.assertIn("Hong Liu Lorem v. Lynch-Loretta E.", r.content.decode())

        # Query by panel_ids advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"panel_ids:{self.author.pk}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem v. Lynch-Loretta E.", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem v. Lynch-Loretta E.", r.content.decode())

        # Query by dateArgued advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "dateArgued:[2015-08-15T00:00:00Z TO 2015-08-17T00:00:00Z]",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Jose", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Jose", r.content.decode())

        # Query by pacer_case_id advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"pacer_case_id:{self.audio_5.docket.pacer_case_id}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())

    def test_oa_advanced_search_by_field_and_keyword(self) -> None:
        # Query by advanced field and refine by keyword.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"docket_id:{self.audio_3.docket.pk} Lorem",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Lorem", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Lorem", r.content.decode())

    def test_oa_random_ordering(self) -> None:
        """Can the Oral Arguments results be ordered randomly?

        This test is difficult since we can't check that things actually get
        ordered randomly, but we can at least make sure the query succeeds.
        """
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Hong Liu",
            "order_by": "random_123 desc",
        }
        # Frontend
        r = self.client.get(reverse("show_results"), search_params)
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertNotIn("an error", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)

    def test_last_oral_arguments_home_page(self) -> None:
        """Test last oral arguments in home page"""
        cache.delete("homepage-data-oa-es")
        r = self.client.get(
            reverse("show_results"),
        )
        self.assertIn("Latest Oral Arguments", r.content.decode())
        self.assertIn(
            "SEC v. Frank J. Information, WikiLeaks", r.content.decode()
        )
        self.assertIn(
            "Jose A. Dominguez v. Loretta E. Lynch", r.content.decode()
        )
        self.assertIn("Hong Liu Yang v. Lynch-Loretta E.", r.content.decode())
        self.assertIn("Hong Liu Lorem v. Lynch-Loretta E.", r.content.decode())

    def test_oa_advanced_search_combine_fields(self) -> None:
        # Query by two advanced fields, caseName and docketNumber
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"caseName:Loretta AND docketNumber:({self.audio_2.docket.docket_number})",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

    def test_oa_search_by_no_exact_docket_number(self) -> None:
        # Query a not exact docket number: 19-5734 -> 19 5734
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f'docketNumber:"19 5734"',
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

        # Avoid error parsing the docket number: 19-5734 -> 19:5734.
        search_params["q"] = "docketNumber:19:5734"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

    def test_oa_results_relevance_ordering_elastic(self) -> None:
        # Relevance order, two words match.
        search_params = {
            "q": "Lynch Loretta",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang")
            < r.content.decode().index("Jose"),
            msg="'Hong Liu Lorem' should come BEFORE 'Hong Liu Yang' and 'Jose' when order_by relevance.",
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang")
            < r.content.decode().index("Jose"),
            msg="'Hong Liu Lorem' should come BEFORE 'Hong Liu Yang' and 'Jose' when order_by relevance.",
        )

        # Relevance order, two words match, reverse order.
        search_params = {
            "q": "Loretta Lynch",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Jose")
            < r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang"),
            msg="'Jose' should come BEFORE 'Hong Liu Lorem' and 'Hong Liu Yang' when order_by relevance.",
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Jose")
            < r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang"),
            msg="'Jose' should come BEFORE 'Hong Liu Lorem' and 'Hong Liu Yang' when order_by relevance.",
        )

        # Relevance order, hyphenated compound word.
        search_params = {
            "q": "Lynch-Loretta E.",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang")
            < r.content.decode().index("Jose"),
            msg="'Hong Liu Lorem' should come BEFORE 'Hong Liu Yang' and 'Jose' when order_by relevance.",
        )
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang")
            < r.content.decode().index("Jose"),
            msg="'Hong Liu Lorem' should come BEFORE 'Hong Liu Yang' and 'Jose' when order_by relevance.",
        )

    def test_oa_results_api_fields_es(self) -> None:
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Hong Liu Lorem v. Lynch-Loretta E.",
        }

        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        expected = 1
        self.assertEqual(actual, expected)

        keys_to_check = [
            "absolute_url",
            "caseName",
            "court",
            "court_citation_string",
            "court_exact",
            "court_id",
            "dateArgued",
            "dateReargued",
            "dateReargumentDenied",
            "docketNumber",
            "docket_id",
            "download_url",
            "duration",
            "file_size_mp3",
            "id",
            "judge",
            "local_path",
            "pacer_case_id",
            "panel_ids",
            "snippet",
            "source",
            "sha1",
            "timestamp",
        ]
        keys_count = len(r.data["results"][0])
        self.assertEqual(keys_count, 23)
        for key in keys_to_check:
            self.assertTrue(
                key in r.data["results"][0],
                msg=f"Key {key} not found in the result object.",
            )

    def test_oa_results_api_pagination(self) -> None:
        created_audios = []
        for i in range(20):
            audio = AudioFactory.create(
                docket_id=self.audio_3.docket.pk,
            )
            created_audios.append(audio)
        AudioDocument._index.refresh()
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 20
        self.assertEqual(actual, expected)
        self.assertIn("24", r.content.decode())
        self.assertIn("1 of 2", r.content.decode())

        # Test next page.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "page": 2,
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 5
        self.assertEqual(actual, expected)
        self.assertIn("25", r.content.decode())
        self.assertIn("2 of 2", r.content.decode())

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        expected = 20
        self.assertEqual(actual, expected)
        self.assertEqual(25, r.data["count"])
        self.assertIn("page=2", r.data["next"])

        # Test next page.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "page": 2,
        }
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        expected = 5
        self.assertEqual(actual, expected)
        self.assertEqual(25, r.data["count"])
        self.assertEqual(None, r.data["next"])

        # Remove Audio objects to avoid affecting other tests.
        for created_audio in created_audios:
            created_audio.delete()
        AudioDocument._index.refresh()

    def test_oa_synonym_search(self) -> None:
        # Query using a synonym
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"Freedom of Info",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())

        # Top abbreviations in legal documents
        # Single term posttraumatic
        search_params["q"] = "posttraumatic stress disorder"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>ptsd</mark>", r.content.decode())

        # Split terms post traumatic
        search_params["q"] = "post traumatic stress disorder"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>ptsd</mark>", r.content.decode())

        # Search acronym "apa"
        search_params["q"] = "apa"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("<mark>apa</mark>", r.content.decode())
        self.assertIn("<mark>Administrative</mark>", r.content.decode())
        self.assertIn("<mark>procedures</mark>", r.content.decode())
        self.assertIn("<mark>act</mark>", r.content.decode())

        # Search by "Administrative procedures act"
        search_params["q"] = "Administrative procedures act"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("<mark>apa</mark>", r.content.decode())
        self.assertIn("<mark>Administrative</mark>", r.content.decode())
        self.assertIn("<mark>procedures</mark>", r.content.decode())
        self.assertIn("<mark>act</mark>", r.content.decode())

        # Search by "Administrative" shouldn't return results for "apa" but for
        # "Administrative" and "Administrative procedures act".
        search_params["q"] = "Administrative"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Yang", r.content.decode())
        self.assertIn("procedures act", r.content.decode())

        # Single word one-way synonyms.
        # mag => mag,magazine,magistrate
        search_params["q"] = "mag"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertIn("<mark>mag</mark>", r.content.decode())
        self.assertIn("<mark>magazine</mark>", r.content.decode())
        self.assertIn("<mark>magistrate</mark>", r.content.decode())

        # Searching "magazine" only returns results containing "magazine"
        search_params["q"] = "magazine"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>magazine</mark>", r.content.decode())

    def test_oa_stopwords_search(self) -> None:
        # Query using a stopword, indexed content doesn't contain the stop word
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"judge:Wallace and Friedland",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"judge:Wallace to Friedland",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())

        # Special stopwords are not found.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"xx-xxxx",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 0
        self.assertEqual(actual, expected)

    def test_phrase_queries_with_stop_words(self) -> None:
        # Do phrase queries with stop words return results properly?
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f'caseName:"Freedom of Inform"',
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())

    def test_character_case_queries(self) -> None:
        # Do character case queries works properly?
        # Queries like WikiLeaks and wikileaks or GraphQL and GraphqL, should
        # return the same results in both cases.
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "WikiLeaks",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Freedom", r.content.decode())

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "wikileaks",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Freedom", r.content.decode())

    def test_emojis_searchable(self) -> None:
        # Are emojis are searchable?
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "⚖️",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wallace", r.content.decode())
        # Is the emoji highlighted?
        self.assertIn("<mark>⚖️</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>⚖️</mark>"), 2)

        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wallace", r.content.decode())

    def test_docket_number_proximity_query(self) -> None:
        """Test docket_number proximity query, so that docket numbers like
        1:21-cv-1234-ABC can be matched by queries like: 21-1234
        """

        # Query 1234-21, no results should be returned due to phrased search.
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "1234-21",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 0
        self.assertEqual(actual, expected)
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)

        # Query 21-1234, return results for 1:21-bk-1234 and 1:21-cv-1234-ABC
        # Frontend
        search_params["q"] = "21-1234"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())
        self.assertIn("SEC", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())
        self.assertIn("SEC", r.content.decode())

        # Query 1:21-cv-1234
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "1:21-cv-1234",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())

        # Query 1:21-cv-1234-ABC
        # Frontend
        search_params["q"] = "1:21-cv-1234-ABC"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())

        # Query 1:21-bk-1234
        # Frontend
        search_params["q"] = "1:21-bk-1234"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())

        # docket_number filter: 21-1234, return results for 1:21-bk-1234
        # and 1:21-cv-1234-ABC
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": f"21-1234",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Freedom", r.content.decode())
        self.assertIn("SEC", r.content.decode())

        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())
        self.assertIn("SEC", r.content.decode())

    def test_docket_number_suffixes_query(self) -> None:
        """Test docket_number with suffixes can be found."""

        # Indexed: 1:21-bk-1234 -> Search: 1:21-bk-1234-ABC
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "1:21-bk-1234-ABC",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        # API
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}), search_params
        )
        actual = self.get_results_count(r)
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())

        # Other kind of formats can still be searched -> ASBCA No. 59126
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "ASBCA No. 59126",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu", r.content.decode())

    def test_stemming_disable_search(self) -> None:
        """Test docket_number with suffixes can be found."""

        # Normal search with stemming 'Information', results for:
        # Hong Liu Yang (Joseph Information Deposition)
        # SEC v. Frank J. Information... (Mary Deposit)
        # Freedom of Inform... (Wallace to Friedland ⚖️ Deposit)
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Information deposition",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank J.", r.content.decode())
        self.assertIn("Freedom of", r.content.decode())
        self.assertIn("Hong Liu Yang", r.content.decode())

        # Exact search '"Information" deposition', results for:
        # Hong Liu Yang (Joseph Information Deposition)
        # SEC v. Frank J. Information... (Mary Deposit)
        # Frontend
        search_params["q"] = '"Information" deposition'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank J.", r.content.decode())
        self.assertIn("Hong Liu Yang", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Information</mark>"), 4
        )
        self.assertEqual(r.content.decode().count("<mark>Deposit</mark>"), 2)
        self.assertEqual(
            r.content.decode().count("<mark>Deposition</mark>"), 2
        )

        # Exact search '"Information" "deposit"', results for:
        # SEC v. Frank J. Information... (Mary Deposit)
        # Frontend
        search_params["q"] = '"Information" "deposit"'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank J.", r.content.decode())

        # Exact search '"Inform" "deposit"', results for:
        # Freedom of Inform... (Wallace to Friedland ⚖️ Deposit)
        # Frontend
        search_params["q"] = '"Inform" "deposit"'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom of", r.content.decode())
        self.assertIn("<mark>Inform</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Inform</mark>"), 2)
        self.assertEqual(r.content.decode().count("<mark>Deposit</mark>"), 2)

        # API
        # Does quote_field_suffix works on API too?
        search_params["q"] = '"Inform" "deposit"'
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v3"}),
            search_params,
        )
        actual = self.get_results_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom of", r.content.decode())

    def test_keep_in_sync_related_OA_objects(self) -> None:
        """Test Audio documents are updated when related objects change."""
        with transaction.atomic():
            docket_5 = DocketFactory.create(
                docket_number="1:22-bk-12345",
                court_id=self.court_1.pk,
                date_argued=datetime.date(2015, 8, 16),
            )
            audio_6 = AudioFactory.create(
                case_name="Lorem Ipsum Dolor vs. USA",
                docket_id=docket_5.pk,
            )
            audio_7 = AudioFactory.create(
                case_name="Lorem Ipsum Dolor vs. IRS",
                docket_id=docket_5.pk,
            )
            AudioDocument._index.refresh()
            cd = {
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "q": "Lorem Ipsum Dolor vs. United States",
                "order_by": "score desc",
            }
            search_query = AudioDocument.search()
            s, total_query_results, top_hits_limit = build_es_main_query(
                search_query, cd
            )
            self.assertEqual(s.count(), 1)
            results = s.execute()
            self.assertEqual(results[0].caseName, "Lorem Ipsum Dolor vs. USA")
            self.assertEqual(results[0].docketNumber, "1:22-bk-12345")
            self.assertEqual(results[0].panel_ids, [])

            # Update docket number.
            docket_5.docket_number = "23-98765"
            docket_5.save()
            AudioDocument._index.refresh()
            # Confirm docket number is updated in the index.
            s, total_query_results, top_hits_limit = build_es_main_query(
                search_query, cd
            )
            self.assertEqual(s.count(), 1)
            results = s.execute()
            self.assertEqual(results[0].caseName, "Lorem Ipsum Dolor vs. USA")
            self.assertEqual(results[0].docketNumber, "23-98765")

            # Trigger a ManyToMany insert.
            audio_7.refresh_from_db()
            audio_7.panel.add(self.author)
            AudioDocument._index.refresh()
            # Confirm ManyToMany field is updated in the index.
            cd["q"] = "Lorem Ipsum Dolor vs. IRS"
            s, total_query_results, top_hits_limit = build_es_main_query(
                search_query, cd
            )
            self.assertEqual(s.count(), 1)
            results = s.execute()
            self.assertEqual(results[0].caseName, "Lorem Ipsum Dolor vs. IRS")
            self.assertEqual(results[0].panel_ids, [self.author.pk])

            # Delete parent docket.
            docket_5.delete()
            AudioDocument._index.refresh()
            # Confirm that docket-related audio objects are removed from the
            # index.
            cd["q"] = "Lorem Ipsum Dolor"
            s, total_query_results, top_hits_limit = build_es_main_query(
                search_query, cd
            )
            self.assertEqual(s.count(), 0)

    def test_exact_and_synonyms_query(self) -> None:
        """Test exact and synonyms in the same query."""

        # Search for 'learn road' should return results for 'learn of rd' and
        # 'learning rd'.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"learn road",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Learn</mark>", r.content.decode())
        self.assertIn("<mark>Learning</mark>", r.content.decode())
        self.assertIn("<mark>rd</mark>", r.content.decode())

        # Search for '"learning" road' should return only a result for
        # 'Learning rd'
        search_params["q"] = f'"learning" road'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Learning</mark>", r.content.decode())
        self.assertIn("rd", r.content.decode())

        # A phrase search for '"learn road"' should execute an exact and phrase
        # search simultaneously. It shouldn't return any results,
        # given that the indexed string is 'Learn of rd'.
        search_params["q"] = f'"learn road"'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 0
        self.assertEqual(actual, expected)

    def test_percolator(self) -> None:
        """Test if a variety of documents triggers a percolator query."""

        created_queries_ids = []
        # Add queries to percolator.
        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Loretta",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        AudioPercolator._index.refresh()
        response = percolate_document(str(self.audio_2.pk), "oral_arguments")
        expected_queries = 1
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "case_name": "jose",
            "q": "",
            "order_by": "score desc",
        }

        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        AudioPercolator._index.refresh()
        response = percolate_document(str(self.audio_2.pk), "oral_arguments")
        expected_queries = 2
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": f"1:21-bk-1234",
            "q": "",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        AudioPercolator._index.refresh()
        response = percolate_document(str(self.audio_1.pk), "oral_arguments")
        expected_queries = 1
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": f"1:21-cv-1234-ABC",
            "court": f"cabc",
            "q": "",
            "order_by": "score desc",
        }

        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        AudioPercolator._index.refresh()
        response = percolate_document(str(self.audio_5.pk), "oral_arguments")
        expected_queries = 1
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": f"1:21-bk-1234",
            "court": f"cabc",
            "argued_after": datetime.date(2015, 8, 16),
            "q": "",
            "order_by": "score desc",
        }

        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        AudioPercolator._index.refresh()
        response = percolate_document(str(self.audio_1.pk), "oral_arguments")
        expected_queries = 2
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": f"19-5734",
            "court": f"cabc",
            "argued_after": datetime.date(2015, 8, 15),
            "q": "Loretta NOT (Hong Liu)",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        AudioPercolator._index.refresh()
        response = percolate_document(str(self.audio_2.pk), "oral_arguments")
        expected_queries = 3
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "court": f"nyed",
            "argued_after": datetime.date(2015, 8, 14),
            "q": f"caseName:Loretta AND docketNumber:(ASBCA No. 59126)",
            "order_by": "score desc",
        }

        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        AudioPercolator._index.refresh()
        response = percolate_document(str(self.audio_4.pk), "oral_arguments")
        expected_queries = 2
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        # Remove queries from percolator
        connections.create_connection(
            hosts=[
                f"{settings.ELASTICSEARCH_DSL_HOST}:{settings.ELASTICSEARCH_DSL_PORT}"
            ],
            timeout=50,
        )
        es = Elasticsearch(
            f"{settings.ELASTICSEARCH_DSL_HOST}:{settings.ELASTICSEARCH_DSL_PORT}"
        )
        for query_id in created_queries_ids:
            es.delete(index="oral_arguments_percolator", id=query_id)


class PeopleSearchTestElasticSearch(CourtTestCase, ESTestCaseMixin, TestCase):
    """People search tests for Elasticsearch"""

    @classmethod
    def rebuild_index(self):
        """
        Create and populate the Elasticsearch index and mapping
        """
        # -f rebuilds index without prompt for confirmation
        call_command(
            "search_index", "--rebuild", "-f", "--models", "audio.Audio"
        )

    @classmethod
    def create_index(self):
        """
        Create and populate the Elasticsearch index and mapping
        """
        # -f rebuilds index without prompt for confirmation
        call_command(
            "search_index", "--create", "-f", "--models", "people_db.Person"
        )

    @classmethod
    def delete_index(self):
        """
        Create and populate the Elasticsearch index and mapping
        """
        # -f rebuilds index without prompt for confirmation
        call_command(
            "search_index", "--delete", "-f", "--models", "people_db.Person"
        )

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rebuild_index()
        cls.delete_index()
        cls.create_index()
        cls.person = PersonFactory.create(name_first="John Deer")
        cls.pos_1 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(2015, 12, 14),
            organization_name="Pants, Inc.",
            job_title="Corporate Lawyer",
            position_type=None,
            person=cls.person,
        )
        cls.pos_2 = PositionFactory.create(
            court=cls.court_1,
            person=cls.person,
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(1993, 1, 20),
            date_retirement=datetime.date(2001, 1, 20),
            termination_reason="retire_mand",
            position_type="c-jud",
            how_selected="e_part",
            nomination_process="fed_senate",
        )
        PoliticalAffiliationFactory.create(person=cls.person)
        school = SchoolFactory.create(name="Harvard University")
        cls.education = EducationFactory.create(
            person=cls.person,
            school=school,
            degree_level="ma",
            degree_year="1990",
        )

    def test_index_parent_and_child_objects(self) -> None:
        """Confirm Parent object and child objects are properly indexed."""

        # Judge is indexed.
        self.assertTrue(PersonBaseDocument.exists(id=self.person.pk))

        # Position 1 is indexed.
        self.assertTrue(
            PersonBaseDocument.exists(
                id=PEOPLE_DOCS_TYPE_ID(self.pos_1.pk).POSITION
            )
        )

        # Position 2 is indexed.
        self.assertTrue(
            PersonBaseDocument.exists(
                id=PEOPLE_DOCS_TYPE_ID(self.pos_2.pk).POSITION
            )
        )

        # Education is indexed.
        self.assertTrue(
            PersonBaseDocument.exists(
                id=PEOPLE_DOCS_TYPE_ID(self.education.pk).EDUCATION
            )
        )
