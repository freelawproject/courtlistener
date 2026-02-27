import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch

import httpx
import responses
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.files.base import ContentFile
from django.test import SimpleTestCase
from django.utils.timezone import now
from juriscraper.AbstractSite import logger
from juriscraper.lib.exceptions import UnexpectedContentTypeError
from responses import matchers

from cl.alerts.factories import AlertFactory
from cl.alerts.models import Alert
from cl.api.factories import WebhookFactory
from cl.api.models import WebhookEvent, WebhookEventType
from cl.audio.factories import AudioWithParentsFactory
from cl.audio.models import Audio
from cl.citations.models import UnmatchedCitation
from cl.lib.juriscraper_utils import get_module_by_court_id
from cl.lib.microservice_utils import microservice
from cl.lib.test_helpers import generate_docket_target_sources
from cl.people_db.factories import PersonFactory
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.exceptions import (
    ConsecutiveDuplicatesError,
    SingleDuplicateError,
)
from cl.scrapers.management.commands import (
    cl_back_scrape_citations,
    cl_scrape_opinions,
    cl_scrape_oral_arguments,
    delete_duplicates,
    update_from_text,
)
from cl.scrapers.management.commands.merge_opinion_versions import (
    merge_judge_names,
    merge_versions_by_download_url,
)
from cl.scrapers.models import UrlHash
from cl.scrapers.tasks import (
    extract_opinion_content,
    find_and_merge_versions,
    process_audio_file,
    process_scotus_captcha_transcription,
    subscribe_to_scotus_updates,
)
from cl.scrapers.test_assets import test_opinion_scraper, test_oral_arg_scraper
from cl.scrapers.utils import (
    case_names_are_too_different,
    check_duplicate_ingestion,
    get_existing_docket,
    get_extension,
    update_or_create_docket,
)
from cl.search.documents import (
    ES_CHILD_ID,
    DocketDocument,
    OpinionClusterDocument,
    OpinionDocument,
)
from cl.search.factories import (
    CitationWithParentsFactory,
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionClusterWithParentsFactory,
    OpinionFactory,
    OpinionsCitedWithParentsFactory,
    ParentheticalFactory,
)
from cl.search.models import (
    SEARCH_TYPES,
    SOURCES,
    Citation,
    ClusterRedirection,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    OriginatingCourtInformation,
    Parenthetical,
)
from cl.settings import MEDIA_ROOT
from cl.tests.cases import (
    ESIndexTestCase,
    TestCase,
    TransactionTestCase,
)
from cl.tests.fixtures import ONE_SECOND_MP3_BYTES, SMALL_WAV_BYTES
from cl.users.factories import UserProfileWithParentsFactory


class ScraperIngestionTest(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="test", jurisdiction="F")
        cls.user_profile = UserProfileWithParentsFactory()
        cls.webhook_enabled = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        with cls.captureOnCommitCallbacks(execute=True):
            cls.search_alert_oa = AlertFactory(
                user=cls.user_profile.user,
                rate=Alert.DAILY,
                name="Test Alert OA",
                query="type=oa",
                alert_type=SEARCH_TYPES.ORAL_ARGUMENT,
            )
        cls.existing_oci_id = 111111
        cls.oci = OriginatingCourtInformation.objects.create(
            docket_number="09-1111", id=cls.existing_oci_id
        )

    def test_extension(self):
        r = async_to_sync(microservice)(
            service="buffer-extension",
            params={"mime": True},
        )
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    def test_ingest_opinions_from_scraper(self) -> None:
        """Can we successfully ingest opinions at a high level?"""
        d_1 = DocketFactory(
            case_name="Tarrant Regional Water District v. Herrmann",
            docket_number="11-889",
            court=self.court,
            source=Docket.RECAP,
            pacer_case_id=None,
            originating_court_information=self.oci,
        )

        d_2 = DocketFactory(
            case_name="State of Indiana v. Charles Barker",
            docket_number="49S00-0308-DP-392",
            court=self.court,
            source=Docket.IDB,
            pacer_case_id=None,
        )

        d_3 = DocketFactory(
            case_name="Intl Fidlty Ins Co v. Ideal Elec Sec Co",
            docket_number="96-7169",
            court=self.court,
            source=Docket.RECAP_AND_IDB,
            pacer_case_id="12345",
        )

        site = test_opinion_scraper.Site()
        site.method = "LOCAL"
        parsed_site = async_to_sync(site.parse)()
        cl_scrape_opinions.Command().scrape_court(
            parsed_site, full_crawl=True, ocr_available=False
        )

        opinions = Opinion.objects.all()
        count = opinions.count()
        self.assertTrue(
            opinions.count() == 6,
            f"Should have 6 test opinions, not {count}",
        )

        dockets = Docket.objects.all()
        self.assertTrue(
            dockets.count() == 6,
            f"Should have 6 test dockets, not {dockets.count()}",
        )

        d_1.refresh_from_db()
        d_2.refresh_from_db()
        d_3.refresh_from_db()
        self.assertEqual(d_1.source, Docket.RECAP_AND_SCRAPER)
        self.assertEqual(d_2.source, Docket.SCRAPER_AND_IDB)
        self.assertEqual(d_3.source, Docket.RECAP_AND_SCRAPER_AND_IDB)

        self.assertEqual(
            d_1.case_name, "Tarrant Regional Water District v. Herrmann"
        )
        self.assertEqual(d_2.case_name, "State of Indiana v. Charles Barker")
        self.assertEqual(
            d_3.case_name, "Intl Fidlty Ins Co v. Ideal Elec Sec Co"
        )

        oci = Docket.objects.get(
            case_name="In Re Motion for Consent to Disclosure of Court Records"
        ).originating_court_information
        self.assertEqual(
            oci.docket_number, "09-2222", "New OCI.docket_number was not saved"
        )
        self.assertEqual(
            oci.assigned_to_str,
            "another jalal",
            "New OCI.assigned_to_str was not saved",
        )

        self.assertEqual(
            d_1.originating_court_information.docket_number,
            "09-1111",
            "Existing OCI.docket_number number changed",
        )
        self.assertEqual(
            d_1.originating_court_information.assigned_to_str,
            "another david",
            "Existing OCI.assigned_to_str was not updated",
        )
        self.assertEqual(
            d_1.originating_court_information.id,
            self.existing_oci_id,
            "Existing OCI id should not change",
        )

    def test_opinion_dockets_source_assigment(self) -> None:
        """Test that the opinion dockets source gets properly assigned."""
        docket = DocketFactory.create(
            case_name="Lorem Ipsum",
            docket_number="11-8890",
            court=self.court,
            source=Docket.RECAP,
            pacer_case_id="01111",
        )
        non_columbia_sources_tests = generate_docket_target_sources(
            Docket.NON_COLUMBIA_SOURCES(), Docket.COLUMBIA
        )
        non_harvard_sources_tests = generate_docket_target_sources(
            Docket.NON_HARVARD_SOURCES(), Docket.HARVARD
        )
        non_scraper_sources_tests = generate_docket_target_sources(
            Docket.NON_SCRAPER_SOURCES(), Docket.SCRAPER
        )

        source_assigment_tests = [
            (
                non_columbia_sources_tests,
                Docket.NON_COLUMBIA_SOURCES(),
                Docket.COLUMBIA,
            ),
            (
                non_harvard_sources_tests,
                Docket.NON_HARVARD_SOURCES(),
                Docket.HARVARD,
            ),
            (
                non_scraper_sources_tests,
                Docket.NON_SCRAPER_SOURCES(),
                Docket.SCRAPER,
            ),
        ]

        for (
            expected_sources,
            non_sources,
            source_to_assign,
        ) in source_assigment_tests:
            with self.subTest(
                f"Testing {source_to_assign} source assigment.",
                expected_sources=expected_sources,
                non_sources=non_sources,
                source_to_assign=source_to_assign,
            ):
                self.assertEqual(
                    len(expected_sources),
                    len(non_sources),
                    msg="Was a new non-recap source added?",
                )
                for source, expected_source in expected_sources.items():
                    with self.subTest(
                        f"Testing source {source} assigment.",
                        source=source,
                        expected_source=expected_source,
                    ):
                        Docket.objects.filter(pk=docket.pk).update(
                            source=getattr(Docket, source)
                        )
                        docket.refresh_from_db()
                        docket.add_opinions_source(source_to_assign)
                        docket.save()
                        docket.refresh_from_db()
                        self.assertEqual(
                            docket.source,
                            getattr(Docket, expected_source),
                            msg="The source does not match.",
                        )

    def test_ingest_oral_arguments(self) -> None:
        """Can we successfully ingest oral arguments at a high level?"""

        d_1 = DocketFactory(
            case_name="Jeremy v. Julian",
            docket_number="23-232388",
            court=self.court,
            source=Docket.RECAP,
            pacer_case_id=None,
        )

        site = test_oral_arg_scraper.Site()
        site.method = "LOCAL"
        parsed_site = async_to_sync(site.parse)()

        with self.captureOnCommitCallbacks(execute=True):
            with mock.patch(
                "cl.lib.celery_utils.get_task_wait"
            ) as patched_wait:
                patched_wait.return_value = 0
                cl_scrape_oral_arguments.Command().scrape_court(
                    parsed_site, full_crawl=True
                )

        # There should now be two items in the database.
        audio_files = Audio.objects.all()
        self.assertEqual(2, audio_files.count())

        dockets = Docket.objects.all()
        self.assertTrue(
            dockets.count() == 2,
            f"Should have 2 dockets, not {dockets.count()}",
        )
        d_1.refresh_from_db()
        self.assertEqual(d_1.source, Docket.RECAP_AND_SCRAPER)

        # Confirm that OA Search Alerts are properly triggered after an OA is
        # scraped and its MP3 file is processed.
        # Two webhook events should be sent, both of them to user_profile user
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(
            len(webhook_events), 2, msg="Wrong number of webhook events."
        )

        cases_names = ["Jeremy v. Julian", "Ander v. Leo"]
        for webhook_sent in webhook_events:
            self.assertEqual(
                webhook_sent.webhook.user,
                self.user_profile.user,
            )
            content = webhook_sent.content
            # Check if the webhook event payload is correct.
            self.assertEqual(
                content["webhook"]["event_type"],
                WebhookEventType.SEARCH_ALERT,
            )
            self.assertIn(
                content["payload"]["results"][0]["caseName"], cases_names
            )
            self.assertIsNotNone(content["payload"]["results"][0]["duration"])
            self.assertIsNotNone(
                content["payload"]["results"][0]["local_path"]
            )

    async def test_parsing_xml_opinion_site_to_site_object(self) -> None:
        """Does a basic parse of a site reveal the right number of items?"""
        site = await test_opinion_scraper.Site().parse()
        self.assertEqual(len(site.case_names), 6)

    async def test_parsing_xml_oral_arg_site_to_site_object(self) -> None:
        """Does a basic parse of an oral arg site work?"""
        site = await test_oral_arg_scraper.Site().parse()
        self.assertEqual(len(site.case_names), 2)

    @patch(
        "cl.scrapers.management.commands.cl_scrape_opinions.Command.get_opinions_content"
    )
    def test_scrape_multiple_opinions_per_cluster(
        self, patched_get_opinions_content
    ):
        """Test if we can ingest multiple opinions per opinion cluster"""
        # Define two opinions for the same cluster
        op1 = {
            "download_urls": "https://example.com/op1.pdf",
            "types": Opinion.LEAD,
        }
        op2 = {
            "download_urls": "https://example.com/op2.pdf",
            "types": Opinion.DISSENT,
        }
        returned_cluster = {
            "docket_numbers": "123-456",
            "case_names": "Multiple Opinion Case",
            "case_dates": date(2023, 1, 1),
            "precedential_statuses": "Published",
            "date_filed_is_approximate": False,
            "blocked_statuses": False,
            "sub_opinions": [op1, op2],
        }
        patched_get_opinions_content.return_value = [
            (op1, b"111", "111"),
            (op2, b"222", "222"),
        ]

        mock_site = MagicMock()
        mock_site.__iter__.return_value = [returned_cluster]
        mock_site.court_id = "test"
        mock_site.url = "111"
        mock_site.hash = "234"

        cl_scrape_opinions.Command().scrape_court(mock_site)

        # a single cluster with 2 sub opinions was created
        clusters = OpinionCluster.objects.filter(
            docket__docket_number="123-456"
        )
        self.assertEqual(clusters.count(), 1)
        cluster = clusters.first()

        opinions = Opinion.objects.filter(cluster=cluster)
        self.assertEqual(opinions.count(), 2)


class IngestionTest(TestCase):
    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
    ]

    def setUp(self) -> None:
        files = Opinion.objects.all()
        for opinion in files:
            opinion.file_with_date = datetime.today()
            with open(Path(MEDIA_ROOT, opinion.local_path.name), "rb") as f:
                content = f.read()
            opinion.local_path.save(
                opinion.local_path.name, ContentFile(content)
            )

    def test_doc_content_extraction(self) -> None:
        """Can we ingest a doc file?"""
        doc_opinion = Opinion.objects.get(pk=1)
        extract_opinion_content(doc_opinion.pk, ocr_available=False)
        doc_opinion.refresh_from_db()
        self.assertIn("indiana", doc_opinion.plain_text.lower())

    def test_image_based_pdf(self) -> None:
        """Can we ingest an image based pdf file?"""
        image_opinion = Opinion.objects.get(pk=2)
        extract_opinion_content(image_opinion.pk, ocr_available=True)
        image_opinion.refresh_from_db()
        self.assertIn("intelligence", image_opinion.plain_text.lower())

    def test_text_based_pdf(self) -> None:
        """Can we ingest a text based pdf file?"""
        txt_opinion = Opinion.objects.get(pk=3)
        extract_opinion_content(txt_opinion.pk, ocr_available=False)
        txt_opinion.refresh_from_db()
        self.assertIn("tarrant", txt_opinion.plain_text.lower())

    def test_html_content_extraction(self) -> None:
        """Can we ingest an html file?"""
        html_opinion = Opinion.objects.get(pk=4)
        extract_opinion_content(html_opinion.pk, ocr_available=False)
        html_opinion.refresh_from_db()
        self.assertIn("reagan", html_opinion.html.lower())

    def test_wpd_content_extraction(self) -> None:
        """Can we ingest a wpd file?"""
        wpd_opinion = Opinion.objects.get(pk=5)
        extract_opinion_content(wpd_opinion.pk, ocr_available=False)
        wpd_opinion.refresh_from_db()
        self.assertIn("greene", wpd_opinion.html.lower())

    def test_txt_content_extraction(self) -> None:
        """Can we ingest a txt file?"""
        txt_opinion = Opinion.objects.get(pk=6)
        extract_opinion_content(txt_opinion.pk, ocr_available=False)
        txt_opinion.refresh_from_db()
        self.assertIn("ideal", txt_opinion.plain_text.lower())

    def test_duplicate_ingestion_warnings(self) -> None:
        """Can we detect duplicate ingestion"""
        with mock.patch.object(logger, "error") as error_mock:
            check_duplicate_ingestion("pdf/2025/06/05/state_v._walsh_1.pdf")
            error_mock.assert_not_called()
            check_duplicate_ingestion(
                "html/2025/04/25/zelka_h.v.a.c._maintenance_solutions_inc._v._g.m._crisalli__assoc._inc._12.html"
            )
            error_mock.assert_called()


class ExtensionIdentificationTest(SimpleTestCase):
    def setUp(self) -> None:
        self.path = os.path.join(settings.MEDIA_ROOT, "test", "search")

    def test_wpd_extension(self) -> None:
        with open(os.path.join(self.path, "opinion_wpd.wpd"), "rb") as f:
            data = f.read()
        self.assertEqual(get_extension(data), ".wpd")

    def test_pdf_extension(self) -> None:
        with open(
            os.path.join(self.path, "opinion_pdf_text_based.pdf"), "rb"
        ) as f:
            data = f.read()
        self.assertEqual(get_extension(data), ".pdf")

    def test_doc_extension(self) -> None:
        with open(os.path.join(self.path, "opinion_doc.doc"), "rb") as f:
            data = f.read()
        self.assertEqual(get_extension(data), ".doc")

    def test_html_extension(self) -> None:
        with open(os.path.join(self.path, "opinion_html.html"), "rb") as f:
            data = f.read()
        self.assertEqual(get_extension(data), ".html")

        with open(os.path.join(self.path, "not_wpd.html"), "rb") as f:
            data = f.read()
        self.assertEqual(get_extension(data), ".html")


class DupcheckerTest(TestCase):
    fixtures = ["test_court.json"]

    def setUp(self) -> None:
        self.court = Court.objects.get(pk="test")
        self.dup_checkers = [
            DupChecker(self.court, full_crawl=True),
            DupChecker(self.court, full_crawl=False),
        ]

    def test_abort_when_new_court_website(self) -> None:
        """Tests what happens when a new website is discovered."""
        site = test_opinion_scraper.Site()
        site.hash = "this is a dummy hash code string"

        for dup_checker in self.dup_checkers:
            abort = dup_checker.abort_by_url_hash(site.url, site.hash)
            if dup_checker.full_crawl:
                self.assertFalse(
                    abort, "DupChecker says to abort during a full crawl."
                )
            else:
                self.assertFalse(
                    abort,
                    "DupChecker says to abort on a court that's never been "
                    "crawled before.",
                )

            # The checking function creates url2Hashes, that we must delete as
            # part of cleanup.
            dup_checker.url_hash.delete()

    def test_abort_on_unchanged_court_website(self) -> None:
        """Similar to the above, but we create a UrlHash object before
        checking if it exists."""
        site = test_opinion_scraper.Site()
        site.hash = "this is a dummy hash code string"
        for dup_checker in self.dup_checkers:
            UrlHash(id=site.url, sha1=site.hash).save()
            abort = dup_checker.abort_by_url_hash(site.url, site.hash)
            if dup_checker.full_crawl:
                self.assertFalse(
                    abort, "DupChecker says to abort during a full crawl."
                )
            else:
                self.assertTrue(
                    abort,
                    "DupChecker says not to abort on a court that's been "
                    "crawled before with the same hash",
                )

            dup_checker.url_hash.delete()

    def test_abort_on_changed_court_website(self) -> None:
        """Similar to the above, but we create a UrlHash with a different
        hash before checking if it exists.
        """
        site = test_opinion_scraper.Site()
        site.hash = "this is a dummy hash code string"
        for dup_checker in self.dup_checkers:
            UrlHash(pk=site.url, sha1=site.hash).save()
            abort = dup_checker.abort_by_url_hash(
                site.url, "this is a *different* hash!"
            )
            if dup_checker.full_crawl:
                self.assertFalse(
                    abort, "DupChecker says to abort during a full crawl."
                )
            else:
                self.assertFalse(
                    abort,
                    "DupChecker says to abort on a court where the hash has "
                    "changed.",
                )

            dup_checker.url_hash.delete()

    def test_press_on_with_an_empty_database(self) -> None:
        site = test_opinion_scraper.Site()
        site.hash = "this is a dummy hash code string"
        for dup_checker in self.dup_checkers:
            try:
                dup_checker.press_on(
                    Opinion,
                    now(),
                    now() - timedelta(days=1),
                    lookup_value="content",
                    lookup_by="sha1",
                )
            except (SingleDuplicateError, ConsecutiveDuplicatesError):
                if dup_checker.full_crawl:
                    failure = "DupChecker says to abort during a full crawl. This should never happen."
                else:
                    count = Opinion.objects.all().count()
                    failure = f"DupChecker says to abort on dups when the database has {count} Documents."
                self.fail(failure)


class DupcheckerPressOnTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.court = Court.objects.get(pk="test")

        self.dc_full_crawl = DupChecker(self.court, True, 2)
        self.dc_not_full_crawl = DupChecker(self.court, False, 2)
        self.dup_checkers = [self.dc_full_crawl, self.dc_not_full_crawl]
        self.dup_hash = "1" * 40
        self.press_on_args = [Opinion, now(), now(), self.dup_hash]

        docket = DocketFactory()
        cluster = OpinionClusterFactory(docket=docket)
        opinion = OpinionFactory(sha1=self.dup_hash, cluster=cluster)

    def test_press_on_no_dup(self) -> None:
        """Does the DupChecker raises no error when seeing a new hash?"""
        self.dc_full_crawl.press_on(*self.press_on_args[:-1], "not a dup")
        self.dc_not_full_crawl.press_on(*self.press_on_args[:-1], "not a dup")

    def test_press_on_with_a_dup_found(self) -> None:
        """Do we raise the appropiate exceptions when a dup is found?"""
        # First duplicate
        try:
            self.dc_full_crawl.press_on(*self.press_on_args)
            self.fail("Should raise SingleDuplicateError")
        except ConsecutiveDuplicatesError:
            self.fail("Full crawl raised a loop breaking exception")
        except SingleDuplicateError:
            pass  # we expect this to happen

        # Second duplicate, dup threshold = 2
        try:
            self.dc_full_crawl.press_on(*self.press_on_args)
            self.fail("Should raise SingleDuplicateError")
        except ConsecutiveDuplicatesError:
            self.fail("Full crawl raised a loop breaking exception")
        except SingleDuplicateError:
            pass

        # First duplicate
        try:
            self.dc_not_full_crawl.press_on(*self.press_on_args)
            self.fail("Should raise SingleDuplicateError")
        except SingleDuplicateError:
            pass
        except ConsecutiveDuplicatesError:
            self.fail(
                "Dup threshold is 1, should not raise ConsecutiveDuplicatesError"
            )

        # Second duplicate, dup threshold = 2
        try:
            self.dc_not_full_crawl.press_on(*self.press_on_args)
            self.fail("Should raise ConsecutiveDuplicatesError")
        except SingleDuplicateError:
            self.fail("Should raise ConsecutiveDuplicatesError")
        except ConsecutiveDuplicatesError:
            pass  # expected behavior

    def test_press_on_with_dup_found_and_older_date(self) -> None:
        """Do we raise the appropiate exception when a duplicate is found
        and we account for case dates?
        """
        self.dc_not_full_crawl.reset()
        self.dc_full_crawl.reset()

        # duplicated case occurs prior to the current one
        args = [*self.press_on_args]
        args[2] = now() - timedelta(days=1)

        try:
            self.dc_full_crawl.press_on(*args)
            self.fail("Expected SingleDuplicateError")
        except SingleDuplicateError:
            pass
        except ConsecutiveDuplicatesError:
            self.fail(
                "This a full crawl, ConsecutiveDuplicatesError should not be raised"
            )

        try:
            self.dc_not_full_crawl.press_on(*args)
            self.fail("Expected loop breaking ConsecutiveDuplicatesError")
        except SingleDuplicateError:
            self.fail("Expected loop breaking ConsecutiveDuplicatesError")
        except ConsecutiveDuplicatesError:
            pass


class AudioFileTaskTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        docket = DocketFactory.create(
            date_argued=datetime(year=2022, month=5, day=4),
        )
        cls.audio1 = AudioWithParentsFactory.create(
            docket=docket,
            local_path_mp3__data=ONE_SECOND_MP3_BYTES,
            local_path_original_file__data=ONE_SECOND_MP3_BYTES,
        )
        cls.audio2 = AudioWithParentsFactory.create(
            docket=docket,
            local_path_mp3__data=SMALL_WAV_BYTES,
            local_path_original_file__data=SMALL_WAV_BYTES,
        )

    def test_process_audio_file(self) -> None:
        af = Audio.objects.get(pk=self.audio1.id)
        expected_duration = 1.0
        with mock.patch("cl.lib.celery_utils.get_task_wait") as patched_wait:
            patched_wait.return_value = 0
            process_audio_file(pk=self.audio1.id)

        af.refresh_from_db()
        measured_duration: float = af.duration  # type: ignore
        # Use almost equal because measuring MP3's is wonky.
        self.assertAlmostEqual(
            measured_duration,
            expected_duration,
            delta=5,
            msg=f"We should end up with the proper duration of about {expected_duration}. "
            f"Instead we got {measured_duration}.",
        )

    def test_audio_conversion(self) -> None:
        """Can we convert wav to audio and update the metadata"""
        audio_obj = Audio.objects.get(pk=self.audio2.id)
        audio_data = {
            "court_full_name": audio_obj.docket.court.full_name,
            "court_short_name": audio_obj.docket.court.short_name,
            "court_pk": audio_obj.docket.court.pk,
            "court_url": audio_obj.docket.court.url,
            "docket_number": audio_obj.docket.docket_number,
            "date_argued": audio_obj.docket.date_argued.strftime("%Y-%m-%d"),
            "date_argued_year": audio_obj.docket.date_argued.year,
            "case_name": audio_obj.case_name,
            "case_name_full": audio_obj.case_name_full,
            "case_name_short": audio_obj.case_name_short,
            "download_url": audio_obj.download_url,
        }
        audio_response = async_to_sync(microservice)(
            service="convert-audio",
            item=audio_obj,
            params=audio_data,
        )

        self.assertEqual(
            audio_response.status_code,
            HTTPStatus.OK,
            msg="Unsuccessful audio conversion",
        )


class ScraperContentTypeTest(TestCase):
    def setUp(self):
        # Common mock setup for all tests
        self.mock_response = mock.AsyncMock(httpx.Response)
        self.mock_response.content = b"not empty"
        self.mock_response.headers = {"Content-Type": "application/pdf"}
        self.site = test_opinion_scraper.Site()
        self.site.method = "GET"
        self.logger = logger

    @mock.patch("httpx.AsyncClient.get")
    async def test_unexpected_content_type(self, mock_get):
        """Test when content type doesn't match scraper expectation."""
        mock_get.return_value = self.mock_response
        self.site.expected_content_types = ["text/html"]
        with self.assertRaises(UnexpectedContentTypeError):
            await self.site.download_content("/dummy/url/")

    @mock.patch("httpx.AsyncClient.get")
    async def test_correct_content_type(self, mock_get):
        """Test when content type matches scraper expectation."""
        mock_get.return_value = self.mock_response
        self.site.expected_content_types = ["application/pdf"]

        with mock.patch.object(self.logger, "error") as error_mock:
            _ = await self.site.download_content("/dummy/url/")

            self.mock_response.headers = {
                "Content-Type": "application/pdf;charset=utf-8"
            }
            mock_get.return_value = self.mock_response
            _ = await self.site.download_content("/dummy/url/")
            error_mock.assert_not_called()

    @mock.patch("httpx.AsyncClient.get")
    async def test_no_content_type(self, mock_get):
        """Test for no content type expected (ie. Montana)"""
        mock_get.return_value = self.mock_response
        self.site.expected_content_types = None

        with mock.patch.object(self.logger, "error") as error_mock:
            _ = await self.site.download_content("/dummy/url/")
            error_mock.assert_not_called()


class ScrapeCitationsTest(TestCase):
    """This class only tests the update of existing clusters
    Since the ingestion of new clusters and their citations call
    super().scrape_court(), it should be tested in the superclass
    """

    def setUp(self):
        keys = [
            "download_urls",
            "case_names",
            "citations",
            "parallel_citations",
        ]
        self.mock_site = mock.MagicMock()
        self.mock_site.__iter__.return_value = [
            # update
            dict(zip(keys, ["", "something", "482 Md. 342", ""])),
            # exact duplicate
            dict(zip(keys, ["", "something", "", "482 Md. 342"])),
            # reporter duplicate
            dict(zip(keys, ["", "something", "485 Md. 111", ""])),
            # no citation, ignore
            dict(zip(keys, ["", "something", "", ""])),
        ]
        self.mock_site.court_id = "juriscraper.md"
        self.hash = "1234" * 10
        self.hashes = [self.hash, self.hash, self.hash, "111"]

        court = CourtFactory(id="md")
        docket = DocketFactory(
            case_name="Attorney Grievance v. Taniform",
            docket_number="40ag/21",
            court_id="md",
            source=Docket.SCRAPER,
            pacer_case_id=None,
        )
        self.cluster = OpinionClusterFactory(docket=docket)
        opinion = OpinionFactory(sha1=self.hash, cluster=self.cluster)

    def test_citation_scraper(self):
        """Test if citation scraper creates a citation or ignores duplicates"""
        cmd = "cl.scrapers.management.commands.cl_back_scrape_citations"
        with (
            mock.patch(f"{cmd}.sha1", side_effect=self.hashes),
            mock.patch.object(
                self.mock_site,
                "download_content",
                new=mock.AsyncMock(return_value="placeholder"),
            ),
        ):
            cl_back_scrape_citations.Command().scrape_court(self.mock_site)

        citations = Citation.objects.filter(cluster=self.cluster).count()
        self.assertEqual(citations, 1, "Exactly 1 citation was expected")


class ScraperDocketMatchingTest(TestCase):
    """Docket matching behaves differently depending on court jurisdiction
    - Federal courts use `docket_number_core`
    - State courts do not
    - There are also special cases such as ohioctapp

    Also, test if we can detect when a docket match has a
    case_name to different than the incoming case_name
    """

    def setUp(self):
        self.ariz = CourtFactory(id="ariz")
        DocketFactory(
            docket_number="1 CA-CR 23-0297",
            court=self.ariz,
            source=Docket.SCRAPER,
            pacer_case_id=None,
        )
        # To test query for multi docket dockets without
        # a semicolon
        DocketFactory(
            docket_number="23-1374 23-1880",
            court=self.ariz,
            source=Docket.SCRAPER,
            pacer_case_id=None,
        )

        # Need to disambiguate using `appeal_from_str`
        self.ohioctapp = CourtFactory(id="ohioctapp")
        self.ohioctapp_dn = "22CA15"
        DocketFactory(
            docket_number=self.ohioctapp_dn,
            appeal_from_str="Pickaway County",
            case_name="Dietrich v. Dietrich",
            court=self.ohioctapp,
            source=Docket.SCRAPER,
            pacer_case_id=None,
        )
        DocketFactory(
            docket_number=self.ohioctapp_dn,
            appeal_from_str="Athens County",
            case_name="State v. Myers",
            court=self.ohioctapp,
            source=Docket.SCRAPER,
            pacer_case_id=None,
        )

        self.ca2 = CourtFactory(id="ca2", jurisdiction=Court.FEDERAL_APPELLATE)
        self.ca2_docket = DocketFactory(
            court=self.ca2,
            docket_number="10-1039-pr",
            case_name="Garbutt v. Conway",
            docket_number_core="10001039",
        )

    def test_get_existing_docket(self):
        """Can we get an existing docket if it exists,
        or None if it doesn't?

        Can we handle special cases like ohioctapp and
        multi-docket docket numbers without semicolons?
        """
        # Return Docket
        docket = get_existing_docket(self.ariz.id, "1 CA-CR 23-0297")
        self.assertEqual(docket.docket_number, "1 CA-CR 23-0297")

        docket = get_existing_docket(
            self.ohioctapp.id, self.ohioctapp_dn, "Athens County"
        )
        self.assertEqual(
            docket.appeal_from_str,
            "Athens County",
            "Incorrect docket match for ohioctapp",
        )

        # Test for OR query with or without semicolons
        docket = get_existing_docket(self.ariz.id, "23-1374; 23-1880")
        self.assertEqual(
            get_existing_docket(self.ariz.id, "23-1374 23-1880").id,
            docket.id,
            "should match the same docket",
        )

        # Return None
        docket = get_existing_docket(self.ariz.id, "1 CA-CV 23-0297-FC")
        self.assertIsNone(docket, "Expected None")

        docket = get_existing_docket(
            self.ohioctapp.id, self.ohioctapp_dn, "Gallia County"
        )
        self.assertIsNone(docket, "Expected None, ohioctapp special case")

    def test_different_case_names_detection(self):
        """Can we detect case names that are too different?"""
        similar_names = [
            ("Miller v. Doe", "Miller v. Nelson"),
            (
                "IN RE: KIRKLAND LAKE GOLD LTD. SECURITIES LITIGATION",
                "In Re: Kirkland Lake Gold",
            ),
            # Docket 14734478
            (
                "State ex rel. AWMS Water Solutions, L.L.C. v. Zehringer",
                "State ex rel. AWMS Water Solutions, L.L.C. v. Mertz",
            ),
            # Docket 61614696
            (
                "Fortis Advisors LLC v. Johnson & Johnson, Ethicon, Inc., Alex Gorsky, Ashley McEvoy, Peter Shen and Susan Morano",
                "Fortis Advisors LLC v. Johnson & Johnson",
            ),
        ]
        different_names = [
            # Docket 68390253, ohioctapp error
            ("M.A.N.S.O. Holding, L.L.C. v. Marquette", "State v. Sweeney"),
            # Docket 68295573, az error
            ("Van Camp v. Van Camp", "State v. Snyder"),
        ]
        for first, second in similar_names:
            self.assertFalse(
                case_names_are_too_different(first, second),
                "Case names should not be marked as too different",
            )

        for first, second in different_names:
            self.assertTrue(
                case_names_are_too_different(first, second),
                "Case names should be marked as too different",
            )

    def test_federal_jurisdictions(self):
        """These courts should follow the flow that uses
        cl.recap.mergers.find_docket_object and relies on
        Docket.docket_number_core
        """
        docket = update_or_create_docket(
            "Garbutt v Conway", "", self.ca2, "10-1039", Docket.SCRAPER, False
        )
        self.assertEqual(
            docket, self.ca2_docket, "Should match using docket number core"
        )


class UpdateFromTextCommandTest(TestCase):
    """Test the input processing and DB querying for the command"""

    def setUp(self):
        self.vt = CourtFactory(id="vt")
        self.sc = CourtFactory(id="sc")
        self.docket_sc = DocketFactory(court=self.sc, docket_number="20")

        # Different dates, status and courts to test command behaviour
        self.opinion_2020 = OpinionFactory(
            cluster=OpinionClusterFactory(
                docket=DocketFactory(court=self.vt, docket_number="12"),
                date_filed=date(2020, 6, 1),
                precedential_status="Published",
                source=SOURCES.COURT_M_HARVARD,
            ),
            plain_text="""Docket Number: 2020-12
            Disposition: Affirmed
            2020 VT 11
            Originating Court Docket Number: 18-2222
            """,
        )
        self.opinion_2020_unpub = OpinionFactory(
            cluster=OpinionClusterFactory(
                docket=DocketFactory(court=self.vt, docket_number="13"),
                date_filed=date(2020, 7, 1),
                precedential_status="Unpublished",
                source=SOURCES.COURT_WEBSITE,
            ),
            plain_text="Docket Number: 2020-13\nDisposition: Affirmed",
        )

        self.opinion_sc = OpinionFactory(
            cluster=OpinionClusterFactory(
                docket=self.docket_sc,
                date_filed=date(2021, 6, 1),
                precedential_status="Published",
                source=SOURCES.COURT_WEBSITE,
            ),
            plain_text="Some text with no matches",
            id=101,
        )

        self.opinion_2022 = OpinionFactory(
            cluster=OpinionClusterFactory(
                docket=DocketFactory(court=self.vt, docket_number="13"),
                date_filed=date(2022, 6, 1),
                precedential_status="Unpublished",
                source=SOURCES.COURT_WEBSITE,
            ),
            id=100,
            plain_text="Docket Number: 2022-13\n2022 VT 11",
        )

    def test_inputs(self):
        """Do all command inputs work properly?"""

        # will target a single opinion, for which extract_from_text
        # extracts no metadata. No object should be updated
        cmd = update_from_text.Command()
        with mock.patch(
            "cl.scrapers.tasks.get_scraper_object_by_name",
            return_value=test_opinion_scraper.Site(),
        ):
            cmd.handle(court_id="somepath.sc", opinion_ids=[101])

        self.assertFalse(
            any(
                [
                    cmd.stats["Docket"],
                    cmd.stats["OpinionCluster"],
                    cmd.stats["Citation"],
                    cmd.stats["Opinion"],
                ]
            ),
            "No object should be modified",
        )

        # will target 1 opinion, there are 2 in the time period
        # and 3 for the court
        with mock.patch(
            "cl.scrapers.tasks.get_scraper_object_by_name",
            return_value=test_opinion_scraper.Site(),
        ):
            update_from_text.Command().handle(
                court_id="somepath.vt",
                opinion_ids=[],
                date_filed_gte=datetime(2020, 5, 1),
                date_filed_lte=datetime(2021, 6, 1),
                cluster_status="Published",
            )

        # Test that objects were actually updated / created
        self.assertEqual(
            Citation.objects.filter(cluster=self.opinion_2020.cluster).count(),
            1,
            "There should be a single citation for this cluster",
        )
        self.opinion_2020.refresh_from_db()
        self.opinion_2020.cluster.refresh_from_db()
        self.opinion_2020.cluster.docket.refresh_from_db()
        self.assertEqual(
            self.opinion_2020.cluster.disposition,
            "Affirmed",
            "OpinionCluster.disposition was not updated",
        )
        self.assertEqual(
            self.opinion_2020.cluster.docket.docket_number,
            "2020-12",
            "Docket.docket_number was not updated",
        )

        # Check that other objects in the time period and court
        # were not modified. Meaning, the filter worked
        self.assertEqual(
            self.opinion_2020_unpub.cluster.docket.docket_number,
            "13",
            "Unpublished docket should not be modified",
        )
        self.assertEqual(
            self.opinion_2020.cluster.docket.originating_court_information.docket_number,
            "18-2222",
            "Originating Court Information was not created",
        )


class CommandInputTest(TestCase):
    def test_get_module_by_court_id(self):
        """Test if get_module_by_court_id helper is working properly"""
        try:
            get_module_by_court_id("lactapp", "opinions")
            self.fail("Court id matches more than 1 Site object, should fail")
        except ValueError:
            pass

        try:
            get_module_by_court_id("ca1", "something")
            self.fail("Invalid module type, should fail")
        except ValueError:
            pass

        # same court, different type
        self.assertEqual(
            "juriscraper.opinions.united_states.federal_appellate.ca1",
            get_module_by_court_id("ca1", "opinions"),
        )
        self.assertEqual(
            "juriscraper.oral_args.united_states.federal_appellate.ca1",
            get_module_by_court_id("ca1", "oral_args"),
        )


class OpinionVersionTest(ESIndexTestCase, TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rebuild_index("search.OpinionCluster")
        cls.rebuild_index("search.Docket")

    @patch("cl.lib.es_signal_processor.compute_single_opinion_embeddings.si")
    def test_merge_versions_by_download_url(self, compute_embeddings_mock):
        """Can we merge opinion versions and delete ES documents correctly?

        This a end to end test. It's testing
        - Docket deletion, metadata merging and related objects updating
        - Cluster deletion and metadata merging
        - Opinion.main_version population
        - ElasticSearch deletion
        """
        court_id = "nev"
        court = CourtFactory.create(id=court_id)
        docket_number = "2020-11111"
        appeal_from = "Some lower court"
        main_docket = DocketFactory.create(
            court=court, docket_number=docket_number, appeal_from_str=""
        )
        # Will help to see if we can match this docket and update its
        # related objects
        version_docket = DocketFactory.create(
            court=court,
            docket_number=docket_number,
            appeal_from_str=appeal_from,
        )

        # Create related objects to the version docket so we can update their
        # references on merging
        version_docket_another_cluster = OpinionClusterFactory.create(
            docket=version_docket, source=SOURCES.COURT_WEBSITE
        )
        version_audio = AudioWithParentsFactory.create(docket=version_docket)

        # Opinions will have the same URL, but it has a different docket number
        not_comparable_docket = DocketFactory.create(
            court=court, docket_number="2021-11111"
        )

        other_dates = "Argued on March 10 2025"
        summary = "Something..."
        main_cluster = OpinionClusterFactory.create(
            docket=main_docket,
            other_dates="",
            summary="",
            source=SOURCES.COURT_WEBSITE,
        )
        cluster2 = OpinionClusterFactory.create(
            docket=main_docket,
            # other_dates should overwrite the empty field in the main cluster
            other_dates=other_dates,
            summary="",
            source=SOURCES.COURT_WEBSITE,
        )
        cluster2_id = cluster2.id
        cluster3 = OpinionClusterFactory.create(
            docket=version_docket,
            other_dates="",
            summary=summary,
            source=SOURCES.COURT_WEBSITE,
        )
        cluster4 = OpinionClusterFactory.create(
            docket=DocketFactory.create(), source=SOURCES.COURT_WEBSITE
        )
        cluster5 = OpinionClusterFactory.create(
            docket=not_comparable_docket, source=SOURCES.COURT_WEBSITE
        )

        main_citation = CitationWithParentsFactory.create(
            cluster=main_cluster, volume="10000", reporter="U.S.", page="1"
        )
        repeated_citation = CitationWithParentsFactory.create(
            cluster=cluster2, volume="10000", reporter="U.S.", page="1"
        )
        new_citation = CitationWithParentsFactory.create(
            cluster=cluster2,
            volume="20",
            reporter="Nev.",
            page="20",
            type=Citation.STATE,
        )

        plain_text = (
            """Lorem ipsum dolor sit amet, consectetur adipiscing
        elit, sed do eiusmod tempor incididunt ut labore et dolore magna
        aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco
        laboris nisi ut aliquip ex ea commodo consequat.
        Duis aute irure dolor in reprehenderit in voluptate velit esse cillum
        dolore eu fugiat nulla pariatur...
        """
            * 3
        )
        # simulate an updated text
        # Note that similarity(text1, text2) is around 0.6 for this test
        # while similarity(text2, text1) is greater than 0.9
        updated_plain_text = f"100 Nev 2\n{plain_text}\n"
        download_url = "http://caseinfo.nvsupreme/111.pdf"
        author_str = "A Judge"

        should_ignore_version = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(
                docket=version_docket, source=SOURCES.COURT_M_HARVARD
            ),
            download_url=download_url,
            plain_text=plain_text,
            main_version=None,
            sha1="xxxx",
            html="",
        )
        # Creation order matters, since we can't override date_created
        # the opinion we intend to be the main version must be created last
        version = OpinionFactory.create(
            cluster=cluster2,
            # see if we can pick up opinions with different protocols
            download_url=download_url.replace("http", "https"),
            plain_text=plain_text,
            html="",
            # This field should be updated
            author_str=author_str,
            sha1="22222",
            html_with_citations="something...",
        )
        # the version cluster may have other opinions linked to it that are
        # not versions. Ensure we migrate them to the main cluster after this
        # version cluster is deleted
        not_a_version_in_version_cluster = OpinionFactory.create(
            cluster=cluster2,
            sha1="123456",
        )
        version2 = OpinionFactory.create(
            cluster=cluster3,
            download_url=download_url,
            plain_text=plain_text,
            html="",
            author_str="",
            sha1="33333",
        )
        unrelated_opinion = OpinionFactory.create(
            cluster=cluster4,
            download_url=download_url.replace("111", "222"),
            sha1="44444",
        )
        same_url_different_docket_number = OpinionFactory.create(
            cluster=cluster5,
            download_url=download_url,
            plain_text=plain_text,
            sha1="5555",
        )
        main_opinion = OpinionFactory.create(
            cluster=main_cluster,
            download_url=download_url,
            plain_text=updated_plain_text,
            html="",
            author_str="",
            sha1="11111",
        )

        # test cleanup of objects related to citation annotation
        version_parenthetical = ParentheticalFactory.create(
            describing_opinion=version, described_opinion=unrelated_opinion
        )
        version_opinions_cited = OpinionsCitedWithParentsFactory.create(
            citing_opinion=version, cited_opinion=unrelated_opinion
        )
        version_opinions_cited_cluster = unrelated_opinion.cluster
        version_opinions_cited_cluster.citation_count = 10
        version_opinions_cited_cluster.save()
        version_unmatched_citation = UnmatchedCitation.objects.create(
            citing_opinion=version,
            status=1,
            citation_string="",
            court_id="",
            volume="1",
            reporter="Nev",
            page="1",
            type=1,
        )

        # Test Opinion.joined_by merging
        person1 = PersonFactory()
        person2 = PersonFactory()
        main_opinion.joined_by.add(person1)
        version.joined_by.add(person1)
        version.joined_by.add(person2)

        # Check that elasticsearch docs exist before the merging
        self.assertTrue(
            OpinionClusterDocument.exists(id=cluster2.id),
            "OpinionClusterDocument does not exist",
        )
        self.assertTrue(
            OpinionDocument.exists(id=ES_CHILD_ID(version.id).OPINION),
            "OpinionDocument does not exist",
        )

        # Function to test
        merge_versions_by_download_url(download_url.rsplit("/", 1)[0])

        # Check elasticsearch deletions
        self.assertFalse(
            OpinionClusterDocument.exists(id=cluster2.id),
            "OpinionClusterDocument was not deleted",
        )
        self.assertFalse(
            OpinionDocument.exists(id=ES_CHILD_ID(version.id).OPINION),
            "OpinionDocument was not deleted",
        )
        self.assertFalse(
            DocketDocument.exists(id=version_docket.id),
            "Docket document was not deleted",
        )

        # Time to test
        should_ignore_version.refresh_from_db()
        version.refresh_from_db()
        main_opinion.refresh_from_db()
        main_cluster.refresh_from_db()
        new_citation.refresh_from_db()
        unrelated_opinion.refresh_from_db()
        version2.refresh_from_db()
        same_url_different_docket_number.refresh_from_db()
        version_docket_another_cluster.refresh_from_db()
        version_audio.refresh_from_db()
        not_a_version_in_version_cluster.refresh_from_db()

        # Opinions
        self.assertEqual(
            should_ignore_version.main_version,
            None,
            "Opinion.main_version should not be updated for a non COURT_WEBSITE source cluster",
        )
        self.assertEqual(
            version.main_version,
            main_opinion,
            "Opinion.main_version was not updated",
        )
        self.assertEqual(
            version2.main_version,
            main_opinion,
            "version2 Opinion.main_version was not updated",
        )
        self.assertEqual(
            main_opinion.author_str,
            author_str,
            "Opinion.author_str was not updated in the main object",
        )
        self.assertEqual(
            main_opinion.joined_by.count(),
            2,
            "Opinion.joined_by was not updated",
        )

        self.assertEqual(
            unrelated_opinion.main_version_id,
            None,
            "`unrelated_opinion` should not be updated",
        )
        self.assertEqual(
            same_url_different_docket_number.main_version_id,
            None,
            "`same_url_different_docket_number` should not have it's version updated",
        )
        self.assertEqual(
            not_a_version_in_version_cluster.cluster_id,
            main_cluster.id,
            "non version opinion in the version cluster should be migrated to the main version cluster",
        )

        # Clusters
        try:
            cluster2.refresh_from_db()
            self.fail("`cluster2` should had been deleted")
            cluster3.refresh_from_db()
            self.fail("`cluster3` should had been deleted")
        except OpinionCluster.DoesNotExist:
            pass

        redirection = ClusterRedirection.objects.filter(
            deleted_cluster_id=cluster2_id,
            cluster=main_cluster,
            reason=ClusterRedirection.VERSION,
        ).exists()
        self.assertTrue(
            redirection,
            "ClusterRedirection object from `cluster2` to `main_cluster` was not created",
        )

        self.assertEqual(
            main_cluster.other_dates,
            other_dates,
            "main_cluster.other_dates was not updated on merge",
        )
        self.assertEqual(
            main_cluster.summary,
            summary,
            "main_cluster.summary was not updated on merge",
        )

        # Docket
        main_docket.refresh_from_db()
        self.assertEqual(
            main_docket.appeal_from_str,
            appeal_from,
            "Docket.appeal_from_str should be updated",
        )
        try:
            version_docket.refresh_from_db()
            self.fail("Version docket should be deleted")
        except Docket.DoesNotExist:
            pass
        self.assertEqual(
            version_docket_another_cluster.docket_id,
            main_docket.id,
            "The cluster assigned to `version_docket` should be assigned to `main_docket`",
        )
        self.assertEqual(
            version_audio.docket_id,
            main_docket.id,
            "The audio assigned to `version_docket` should be assigned to `main_docket`",
        )

        # Citations
        try:
            repeated_citation.refresh_from_db()
            self.fail("`repeated_citation` should had been deleted")
        except Citation.DoesNotExist:
            pass

        self.assertEqual(
            new_citation.cluster_id,
            main_cluster.id,
            "new_citation.cluster_id was not updated",
        )

        # test cleanup of objects related to citation annotation
        self.assertEqual(version.html_with_citations, "")

        try:
            version_parenthetical.refresh_from_db()
            self.fail("version's parenthetical should be deleted")
        except Parenthetical.DoesNotExist:
            pass

        try:
            version_opinions_cited.refresh_from_db()
            self.fail("version's OpinionsCited should be deleted")
        except OpinionsCited.DoesNotExist:
            pass

        version_opinions_cited_cluster.refresh_from_db()
        self.assertEqual(version_opinions_cited_cluster.citation_count, 9)

        try:
            version_unmatched_citation.refresh_from_db()
            self.fail("version's UnmatchedCitation should be deleted")
        except UnmatchedCitation.DoesNotExist:
            pass

        # Check that the new citation was indexed in the OpinionClusterDocument
        ocd = OpinionClusterDocument.get(id=main_cluster.id)
        self.assertTrue(
            str(new_citation) in ocd.citation,
            f"{str(new_citation)} not in {ocd.citation}",
        )

    def test_find_and_merge_versions_task(self):
        """Does the scraper versioning task work?"""
        download_url = "https://something.com/1"
        plain_text = "Something ..."
        docket = DocketFactory(docket_number="111")

        should_ignore = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(
                docket=docket, source=SOURCES.COURT_M_HARVARD
            ),
            download_url=download_url,
            plain_text=plain_text,
            main_version=None,
        )
        previous_main = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(
                docket=docket, source=SOURCES.COURT_WEBSITE
            ),
            download_url=download_url,
            plain_text=plain_text,
            main_version=None,
        )
        a_version = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(
                docket=docket, source=SOURCES.COURT_WEBSITE
            ),
            download_url=download_url,
            plain_text=plain_text,
            main_version=previous_main,
        )
        main = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(
                docket=docket, source=SOURCES.COURT_WEBSITE
            ),
            download_url=download_url,
            plain_text=plain_text,
            main_version=None,
        )

        find_and_merge_versions(pk=main.id)
        a_version.refresh_from_db()
        previous_main.refresh_from_db()
        should_ignore.refresh_from_db()

        self.assertEqual(previous_main.main_version.id, main.id)
        # test transitive main_version update
        self.assertEqual(a_version.main_version.id, main.id)

        # should ignore due to OpinionCluster.source
        self.assertEqual(should_ignore.main_version, None)

    def test_source_merging(self):
        """Can we merge both Docket and Cluster sources?"""
        self.assertEqual(
            Docket.merge_sources(Docket.SCRAPER, Docket.SCRAPER_AND_HARVARD),
            Docket.SCRAPER_AND_HARVARD,
        )
        self.assertEqual(
            Docket.merge_sources(Docket.SCRAPER, Docket.DIRECT_INPUT),
            Docket.SCRAPER + Docket.DIRECT_INPUT,
        )

        self.assertEqual(
            SOURCES.merge_sources(
                SOURCES.COURT_WEBSITE, SOURCES.COURT_WEBSITE
            ),
            SOURCES.COURT_WEBSITE,
        )
        self.assertEqual(
            SOURCES.merge_sources(
                SOURCES.COURT_WEBSITE,
                SOURCES.COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD,
            ),
            SOURCES.COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD,
        )
        self.assertEqual(
            SOURCES.merge_sources(
                SOURCES.COURT_WEBSITE, SOURCES.PUBLIC_RESOURCE
            ),
            SOURCES.COURT_M_RESOURCE,
        )
        self.assertEqual(
            SOURCES.merge_sources(
                SOURCES.HARVARD_CASELAW, SOURCES.COLUMBIA_M_COURT
            ),
            SOURCES.COLUMBIA_M_COURT_M_HARVARD,
        )

    def test_string_merging(self):
        """Can we merge strings while reducing repetition?"""
        cases = [
            ("Bender", "Bender, P.J.E.", "Bender, P.J.E."),
            ("Mundy, Sallie", "Justice Sallie Mundy", "Justice Sallie Mundy"),
            (
                "Per Curiam",
                "Breckenridge, Stith, Draper, Russell, Wilson, Fischer",
                "Per Curiam Breckenridge, Stith, Draper, Russell, Wilson, Fischer",
            ),
            (
                "Ishee, Lee, Irving, Griffis, Barnes, Carlton, Maxwell, Fair, James, Wilson",
                "Irving, Ishee, Carlton, Lee, Griffis, Barnes, Roberts, Maxwell, Fair, James",
                "Ishee; Lee; Irving; Griffis; Barnes; Carlton; Maxwell; Fair; James; Wilson; Roberts",
            ),
            (
                "Ishee, Lee, Irving, Griffis, Barnes, Carlton, Maxwell, Fair, James, Wilson".replace(
                    ",", ";"
                ),
                "Irving, Ishee, Carlton, Lee, Griffis, Barnes, Roberts, Maxwell, Fair, James",
                "Ishee; Lee; Irving; Griffis; Barnes; Carlton; Maxwell; Fair; James; Wilson; Roberts",
            ),
            (
                "Simpson, Wojcik, Pellegrini",
                "Simpson, J.",
                "Simpson, Wojcik, Pellegrini",
            ),
        ]
        for str1, str2, expected_result in cases:
            self.assertEqual(merge_judge_names(str1, str2), expected_result)

    def test_transitive_redirection(self):
        """Can we keep existing ClusterRedirections when its target cluster is
        versioned?"""
        to_keep = OpinionClusterWithParentsFactory.create(id=99999)
        to_delete = OpinionClusterWithParentsFactory.create(id=888888)
        existing_redirection_id = 77777
        ClusterRedirection.objects.create(
            deleted_cluster_id=existing_redirection_id,
            cluster=to_delete,
            reason=ClusterRedirection.DUPLICATE,
        )

        ClusterRedirection.create_from_clusters(
            to_keep, to_delete, ClusterRedirection.VERSION
        )

        self.assertTrue(
            ClusterRedirection.objects.filter(
                deleted_cluster_id=existing_redirection_id,
                cluster=to_keep,
                reason=ClusterRedirection.DUPLICATE,
            ).exists(),
            "Existing re-direction was not re-assigned to new cluster",
        )

    def test_loose_text_similarity_merging(self):
        """Can we attempt merges with a loose text similarity threshold?"""
        court_id = "nev"
        court = CourtFactory.create(id=court_id)
        docket_number = "CV-22222"
        main_docket = DocketFactory.create(
            court=court, docket_number=docket_number
        )
        download_url = "http://somethingelse.court/111.pdf"

        version_candidate = OpinionFactory.create(
            cluster=OpinionClusterFactory(
                docket=main_docket, source=SOURCES.COURT_WEBSITE
            ),
            download_url=download_url,
            plain_text="something else...",
            html="",
            author_str="Some Author",
            sha1="yyy",
        )

        opinion = OpinionFactory.create(
            cluster=OpinionClusterFactory(
                docket=main_docket, source=SOURCES.COURT_WEBSITE
            ),
            download_url=download_url,
            plain_text="something...",
            html="",
            author_str="Another Author",
            sha1="xxx",
        )
        base_path = "cl.scrapers.management.commands.merge_opinion_versions"
        with (
            mock.patch(
                f"{base_path}.get_text_similarity"
            ) as patched_get_text_similarity,
            mock.patch(
                f"{base_path}.merge_opinion_versions"
            ) as patched_merge_opinion_versions,
        ):
            patched_get_text_similarity.return_value = (False, True, 0.75, 0.8)
            merge_versions_by_download_url(download_url.rsplit("/", 1)[0])
            # assert that merging was attempted
            patched_get_text_similarity.assert_called()
            patched_merge_opinion_versions.assert_called()

        version_candidate.refresh_from_db()
        self.assertTrue(
            version_candidate.main_version_id is None,
            "Loose versioning should not pass when metadata differs ",
        )


class DeleteDuplicatesTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        nev = CourtFactory.create(id="nev")
        docket_number = "11111"
        docket = DocketFactory.create(court=nev, docket_number=docket_number)
        docket2 = DocketFactory.create(court=nev, docket_number=docket_number)
        same_cluster_fields = {
            "docket": docket,
            "source": SOURCES.COURT_WEBSITE,
            "case_name": "something",
            "case_name_full": "something full",
            "precedential_status": "Precedential",
            "date_filed": "2019-01-01",
        }
        cls.hash = "xxxxxxxx"
        same_opinion_fields = {
            "author": None,
            "plain_text": "Something....",
            "sha1": cls.hash,
            "download_url": "https://something.com/a_pdf.pdf",
        }
        cls.author = "Some author"  # to check metadata propagation

        cls.cluster_to_delete_id = 976123
        cluster_to_delete = OpinionClusterFactory.create(
            id=cls.cluster_to_delete_id, **same_cluster_fields
        )
        cls.should_delete = OpinionFactory.create(
            cluster=cluster_to_delete,
            author_str=cls.author,
            **same_opinion_fields,
        )

        # the factories will create different values which will stop the merge
        cls.should_not_merge = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(
                docket=docket2, source=SOURCES.COURT_WEBSITE
            ),
            **same_opinion_fields,
        )

        # the same, but with a different hash
        cls.different_hash_cluster_id = 123976
        cls.different_hash_cluster = OpinionClusterFactory.create(
            id=cls.different_hash_cluster_id, **same_cluster_fields
        )
        opinion_fields = {**same_opinion_fields}
        opinion_fields["sha1"] = "yyyyyyyyy"
        cls.different_hash_duplicate = OpinionFactory.create(
            cluster=cls.different_hash_cluster, **opinion_fields
        )

        cls.cluster_to_keep = OpinionClusterFactory.create(
            **same_cluster_fields
        )
        cls.op_to_keep = OpinionFactory.create(
            cluster=cls.cluster_to_keep, **same_opinion_fields
        )

        # for text comparison
        coloctapp = CourtFactory.create(id="coloctapp")
        dn = "2222"
        docket = DocketFactory.create(court=coloctapp, docket_number=dn)
        same_cluster_fields["docket"] = docket

        # make sure we only delete identical opinions, after timestamp cleaning
        cls.timestamped_op_do_not_delete = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(**same_cluster_fields),
            sha1="yyy",
            plain_text="Something 20 Dec 2024 21:06:18 Something else",
            author_str="author",
            download_url="https://x.com/1",
            author=None,
        )
        cls.timestamped_op_to_delete = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(**same_cluster_fields),
            sha1="xxx",
            plain_text="Something 19 Dec 2024 21:06:18",
            author_str="author",
            download_url="https://x.com/1",
            author=None,
        )
        cls.timestamped_op_to_keep = OpinionFactory.create(
            cluster=OpinionClusterFactory.create(**same_cluster_fields),
            sha1="zzzz",
            plain_text="Something 01 Jan 2024 01:06:18",
            author_str="author",
            download_url="https://x.com/1",
            author=None,
        )

    def test_same_hash_duplicate_deletion(self):
        """Test that we can delete same hash duplicates

        - confirm deletion
        - confirm ClusterDuplication is created, with proper values
        - abort deletion if something doesn't match
        """
        stats = defaultdict(lambda: 0)
        delete_duplicates.delete_same_hash_duplicates(
            stats, [SOURCES.COURT_WEBSITE]
        )

        try:
            self.should_delete.refresh_from_db()
            self.fail("`should_delete` should be deleted as a duplicate")
        except Opinion.DoesNotExist:
            pass

        self.op_to_keep.refresh_from_db()
        self.assertEqual(
            self.op_to_keep.author_str,
            self.author,
            "metadata was not propagated",
        )

        self.assertTrue(
            ClusterRedirection.objects.filter(
                deleted_cluster_id=self.cluster_to_delete_id,
                cluster=self.cluster_to_keep,
                reason=ClusterRedirection.DUPLICATE,
            ).exists(),
            "ClusterRedirection with proper values was not created",
        )

        try:
            self.should_not_merge.refresh_from_db()
        except Opinion.DoesNotExist:
            self.fail("`should_not_merge` should still exist")

    def test_cleanup_content_method(self):
        """Can we delete different hash duplicates using the `cleanup_content` method"""
        stats = defaultdict(lambda: 0)
        site = test_opinion_scraper.Site()
        with mock.patch(
            "cl.scrapers.management.commands.delete_duplicates.get_cleaned_content_hash"
        ) as patched_get_cleaned_content_hash:
            patched_get_cleaned_content_hash.return_value = self.hash
            delete_duplicates.delete_cleaned_up_content_duplicates(
                stats, "nev", site
            )

        try:
            self.different_hash_cluster.refresh_from_db()
            self.fail(
                "`different_hash_cluster` should be deleted as a duplicate"
            )
        except OpinionCluster.DoesNotExist:
            pass

        try:
            self.different_hash_duplicate.refresh_from_db()
            self.fail(
                "`different_hash_duplicate` should be deleted as a duplicate"
            )
        except Opinion.DoesNotExist:
            pass

        self.assertTrue(
            ClusterRedirection.objects.filter(
                deleted_cluster_id=self.different_hash_cluster_id,
                cluster=self.cluster_to_keep,
                reason=ClusterRedirection.DUPLICATE,
            ).exists(),
            "ClusterRedirection with proper values was not created",
        )

    def test_delete_by_text_comparison(self):
        """Test that we can delete opinions by text comparison"""
        stats = defaultdict(lambda: 0)

        delete_duplicates.delete_by_text_comparison(stats, "coloctapp")

        try:
            self.timestamped_op_to_delete.refresh_from_db()
            self.fail("Timestamped opinion should be deleted")
        except Opinion.DoesNotExist:
            pass

        try:
            self.timestamped_op_do_not_delete.refresh_from_db()
        except Opinion.DoesNotExist:
            self.fail("Should not delete an opinion with different text")

        try:
            delete_duplicates.delete_by_text_comparison(stats, "scotus")
            self.fail("Should raise error due to unsupported court")
        except ValueError:
            pass


class SubscribeToSCOTUSTest(TestCase):
    def setUp(self):
        self.scotus = CourtFactory.create(id="scotus")
        self.docket_number = "25-260"
        self.docket_scotus = DocketFactory.create(
            court=self.scotus, docket_number=self.docket_number
        )
        self.docket_pk = self.docket_scotus.pk

        self.test_asset_dir = (
            Path(settings.INSTALL_ROOT)
            / "cl"
            / "scrapers"
            / "test_assets"
            / "scotus_subscription"
        )

    def add_response(self, file_name: str, **kwargs):
        with open(
            self.test_asset_dir / f"{file_name}.headers.json", "rb"
        ) as f:
            headers = json.load(f)

        content_type = headers["Content-Type"]
        body_extension = content_type.split(";")[0].split("/")[-1]
        if (
            "Content-Encoding" in headers
            and headers["Content-Encoding"] == "gzip"
        ):
            body_extension = f"{body_extension}.gz"

        with open(
            self.test_asset_dir / f"{file_name}.body.{body_extension}", "rb"
        ) as f:
            body = f.read()

        response = responses.Response(headers=headers, body=body, **kwargs)
        responses.add(response)
        return response

    def test_transcription_cleaning(self):
        messy = "RoMeo Juleett.; 5 Seven- .Three"
        clean = process_scotus_captcha_transcription(messy)
        self.assertEqual(clean, "rj573")

    @responses.activate
    @mock.patch("django.conf.settings.OPENAI_TRANSCRIPTION_KEY", "123")
    @mock.patch("cl.scrapers.tasks.call_llm_transcription")
    @mock.patch("cl.lib.celery_utils.get_task_wait")
    def test_subscription_task(
        self, mock_wait: MagicMock, mock_transcription: MagicMock
    ):
        scotus_root = "https://file.supremecourt.gov"
        form_url = (
            f"{scotus_root}/CaseNotification?caseNumber={self.docket_number}"
        )
        subscription_email = "scotus@recap.email"
        captcha_solution = "mo9su"
        captcha_id = "3de9089d-108c-4c2f-b235-7979460b1cb2"
        verification_token = "CfDJ8LWjh78o-U5EigyPTWy9BmfxWSmFTEKR1TK7KTiNnwMLP5CZNLNqEUAPQDHopwbVWJWv0IAFiH3Bc3ANa1MqRpCjj5W9VoDr3HDwtFvrKDVr_NhsqCtfn47gr_jp2cYNyuC7V6HvOn4FAxVP98tlC3I"
        mock_wait.return_value = 0
        mock_transcription.return_value = " ".join(
            [c for c in captcha_solution]
        )

        self.add_response(
            "1_get",
            url=form_url,
            method="GET",
            match=[
                matchers.header_matcher(
                    {
                        "User-Agent": "Free Law Project",
                    }
                )
            ],
        )
        self.add_response(
            "2_post",
            url=f"{scotus_root}/Captcha/Reset",
            method="POST",
            match=[
                matchers.header_matcher(
                    {
                        "User-Agent": "Free Law Project",
                        "Referer": form_url,
                        "X-Requested-With": "XMLHttpRequest",
                    }
                ),
                matchers.urlencoded_params_matcher(
                    {
                        "__RequestVerificationToken": verification_token,
                    }
                ),
            ],
        )
        self.add_response(
            "3_get",
            url=f"{scotus_root}/Captcha/audio?captchaId={captcha_id}",
            method="GET",
            match=[
                matchers.header_matcher(
                    {
                        "User-Agent": "Free Law Project",
                        "Referer": form_url,
                    }
                )
            ],
        )
        self.add_response(
            "4_post",
            url=f"{scotus_root}/Captcha/validate",
            method="POST",
            match=[
                matchers.header_matcher(
                    {
                        "User-Agent": "Free Law Project",
                        "Referer": form_url,
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    }
                ),
                matchers.urlencoded_params_matcher(
                    {
                        "__RequestVerificationToken": verification_token,
                        "captchaId": captcha_id,
                        "captcha": captcha_solution,
                    }
                ),
            ],
        )
        self.add_response(
            "5_post",
            url=f"{scotus_root}/CaseNotification/Subscribe",
            method="POST",
            match=[
                matchers.header_matcher(
                    {
                        "User-Agent": "Free Law Project",
                    }
                ),
                matchers.urlencoded_params_matcher(
                    {
                        "CaseNumber": self.docket_number,
                        "Email": subscription_email,
                        "btnRestart": "Enter another email",
                        "btnSearch": "Return to Search",
                        "WebDocketUrl": f"https://www.supremecourt.gov/search.aspx?filename=/docket/DocketFiles/html/Public/{self.docket_number}.html",
                        "captcha": captcha_solution,
                        "SubscribeButton": "Subscribe",
                        "btnCancel": "Cancel",
                        "__RequestVerificationToken": verification_token,
                    }
                ),
            ],
        )

        subscribe_to_scotus_updates.delay(self.docket_pk).get()
        self.assertEqual(
            len(mock_transcription.mock_calls),
            1,
            "Should have requested exactly 1 transcription",
        )


class SetOrderingKeysTest(SimpleTestCase):
    def test_set_ordering_keys(self):
        """Test if set_ordering_keys correctly assigns ordering_key to multiple opinions"""
        opinions_content = [
            (
                {"types": "030concurrence", "download_urls": "url1"},
                b"",
                "sha1",
            ),
            ({"types": "020lead", "download_urls": "url2"}, b"", "sha2"),
            ({"types": "040dissent", "download_urls": "url3"}, b"", "sha3"),
            (
                {"types": "030concurrence", "download_urls": "url4"},
                b"",
                "sha4",
            ),
        ]

        cl_scrape_opinions.set_ordering_keys(opinions_content)

        # Expected order based on types and original index:
        # 020lead (index 1) -> 1
        # 030concurrence (index 0) -> 2
        # 030concurrence (index 3) -> 3
        # 040dissent (index 2) -> 4

        self.assertEqual(opinions_content[1][0]["ordering_key"], 1)
        self.assertEqual(opinions_content[0][0]["ordering_key"], 2)
        self.assertEqual(opinions_content[3][0]["ordering_key"], 3)
        self.assertEqual(opinions_content[2][0]["ordering_key"], 4)
