import os
from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.timezone import now

from cl.alerts.factories import AlertFactory
from cl.alerts.models import Alert
from cl.api.factories import WebhookFactory
from cl.api.models import WebhookEvent, WebhookEventType
from cl.audio.factories import AudioWithParentsFactory
from cl.audio.models import Audio
from cl.donate.factories import DonationFactory
from cl.donate.models import Donation
from cl.lib.microservice_utils import microservice
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.management.commands import (
    cl_report_scrape_status,
    cl_scrape_opinions,
    cl_scrape_oral_arguments,
)
from cl.scrapers.models import ErrorLog, UrlHash
from cl.scrapers.tasks import extract_doc_content, process_audio_file
from cl.scrapers.test_assets import test_opinion_scraper, test_oral_arg_scraper
from cl.scrapers.utils import get_extension
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import Court, Docket, Opinion
from cl.settings import MEDIA_ROOT
from cl.tests.cases import ESIndexTestCase, SimpleTestCase, TestCase
from cl.tests.fixtures import ONE_SECOND_MP3_BYTES, SMALL_WAV_BYTES
from cl.users.factories import UserProfileWithParentsFactory


class ScraperIngestionTest(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="test", jurisdiction="F")
        cls.user_profile = UserProfileWithParentsFactory()
        cls.donation = DonationFactory(
            donor=cls.user_profile.user,
            amount=20,
            status=Donation.PROCESSED,
            send_annual_reminder=True,
        )
        cls.webhook_enabled = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        cls.search_alert_oa = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA",
            query="type=oa",
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
            case_name="Tarrant Regional Water District v. Herrmann old",
            docket_number="11-889",
            court=self.court,
            source=Docket.SCRAPER,
            pacer_case_id=None,
        )

        d_2 = DocketFactory(
            case_name="State of Indiana v. Charles Barker old",
            docket_number="49S00-0308-DP-392",
            court=self.court,
            source=Docket.SCRAPER,
            pacer_case_id=None,
        )

        d_3 = DocketFactory(
            case_name="Intl Fidlty Ins Co v. Ideal Elec Sec Co old",
            docket_number="96-7169",
            court=self.court,
            source=Docket.SCRAPER,
            pacer_case_id="12345",
        )

        site = test_opinion_scraper.Site()
        site.method = "LOCAL"
        parsed_site = site.parse()
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
        self.assertEqual(
            d_1.case_name, "Tarrant Regional Water District v. Herrmann"
        )
        self.assertEqual(d_2.case_name, "State of Indiana v. Charles Barker")
        self.assertEqual(
            d_3.case_name, "Intl Fidlty Ins Co v. Ideal Elec Sec Co"
        )

    def test_ingest_oral_arguments(self) -> None:
        """Can we successfully ingest oral arguments at a high level?"""

        d_1 = DocketFactory(
            case_name="Jeremy v. Julian old",
            docket_number="23-232388",
            court=self.court,
            source=Docket.SCRAPER,
            pacer_case_id=None,
        )

        site = test_oral_arg_scraper.Site()
        site.method = "LOCAL"
        parsed_site = site.parse()
        with self.captureOnCommitCallbacks(execute=True):
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
        self.assertEqual(d_1.case_name, "Jeremy v. Julian")

        # Confirm that OA Search Alerts are properly triggered after an OA is
        # scraped and its MP3 file is processed.
        # Two webhook events should be sent, both of them to user_profile user
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 2)

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

    def test_parsing_xml_opinion_site_to_site_object(self) -> None:
        """Does a basic parse of a site reveal the right number of items?"""
        site = test_opinion_scraper.Site().parse()
        self.assertEqual(len(site.case_names), 6)

    def test_parsing_xml_oral_arg_site_to_site_object(self) -> None:
        """Does a basic parse of an oral arg site work?"""
        site = test_oral_arg_scraper.Site().parse()
        self.assertEqual(len(site.case_names), 2)


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
        extract_doc_content(doc_opinion.pk, ocr_available=False)
        doc_opinion.refresh_from_db()
        self.assertIn("indiana", doc_opinion.plain_text.lower())

    def test_image_based_pdf(self) -> None:
        """Can we ingest an image based pdf file?"""
        image_opinion = Opinion.objects.get(pk=2)
        extract_doc_content(image_opinion.pk, ocr_available=True)
        image_opinion.refresh_from_db()
        self.assertIn("intelligence", image_opinion.plain_text.lower())

    def test_text_based_pdf(self) -> None:
        """Can we ingest a text based pdf file?"""
        txt_opinion = Opinion.objects.get(pk=3)
        extract_doc_content(txt_opinion.pk, ocr_available=False)
        txt_opinion.refresh_from_db()
        self.assertIn("tarrant", txt_opinion.plain_text.lower())

    def test_html_content_extraction(self) -> None:
        """Can we ingest an html file?"""
        html_opinion = Opinion.objects.get(pk=4)
        extract_doc_content(html_opinion.pk, ocr_available=False)
        html_opinion.refresh_from_db()
        self.assertIn("reagan", html_opinion.html.lower())

    def test_wpd_content_extraction(self) -> None:
        """Can we ingest a wpd file?"""
        wpd_opinion = Opinion.objects.get(pk=5)
        extract_doc_content(wpd_opinion.pk, ocr_available=False)
        wpd_opinion.refresh_from_db()
        self.assertIn("greene", wpd_opinion.html.lower())

    def test_txt_content_extraction(self) -> None:
        """Can we ingest a txt file?"""
        txt_opinion = Opinion.objects.get(pk=6)
        extract_doc_content(txt_opinion.pk, ocr_available=False)
        txt_opinion.refresh_from_db()
        self.assertIn("ideal", txt_opinion.plain_text.lower())


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


class ReportScrapeStatusTest(TestCase):
    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
    ]

    def setUp(self) -> None:
        super(ReportScrapeStatusTest, self).setUp()
        self.court = Court.objects.get(pk="test")
        # Make some errors that we can tally
        ErrorLog(
            log_level="WARNING", court=self.court, message="test_msg"
        ).save()
        ErrorLog(
            log_level="CRITICAL", court=self.court, message="test_msg"
        ).save()

    def test_tallying_errors(self) -> None:
        errors = cl_report_scrape_status.tally_errors()
        self.assertEqual(
            errors["test"],
            [1, 1],
            msg=f"Did not get expected error counts. Instead got: {errors['test']}",
        )

    @staticmethod
    def test_simple_report_generation():
        """Without doing the hard work of creating and checking for actual
        errors, can we at least generate the report?

        A better version of this test would check the contents of the generated
        report by importing it from the test inbox.
        """
        cl_report_scrape_status.generate_report()


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
            onwards = dup_checker.press_on(
                Opinion,
                now(),
                now() - timedelta(days=1),
                lookup_value="content",
                lookup_by="sha1",
            )
            if dup_checker.full_crawl:
                self.assertTrue(
                    onwards,
                    "DupChecker says to abort during a full crawl. This should "
                    "never happen.",
                )
            elif dup_checker.full_crawl is False:
                count = Opinion.objects.all().count()
                self.assertTrue(
                    onwards,
                    "DupChecker says to abort on dups when the database has %s "
                    "Documents." % count,
                )


class DupcheckerWithFixturesTest(TestCase):
    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
    ]

    def setUp(self) -> None:
        super(DupcheckerWithFixturesTest, self).setUp()
        self.court = Court.objects.get(pk="test")

        # Set the dup_threshold to zero for these tests
        self.dup_checkers = [
            DupChecker(self.court, full_crawl=True, dup_threshold=0),
            DupChecker(self.court, full_crawl=False, dup_threshold=0),
        ]

        # Set up the hash value using one in the fixture.
        self.content_hash = "asdfasdfasdfasdfasdfasddf"

    def test_press_on_with_a_dup_found(self) -> None:
        for dup_checker in self.dup_checkers:
            onwards = dup_checker.press_on(
                Opinion,
                now(),
                now(),
                lookup_value=self.content_hash,
                lookup_by="sha1",
            )
            if dup_checker.full_crawl:
                self.assertFalse(
                    onwards,
                    "DupChecker returned True during a full crawl, but there "
                    "should be duplicates in the database.",
                )
                self.assertFalse(
                    dup_checker.emulate_break,
                    "DupChecker said to emulate a break during a full crawl. "
                    "Nothing should stop a full crawl!",
                )

            elif dup_checker.full_crawl is False:
                self.assertFalse(
                    onwards,
                    "DupChecker returned %s but there should be a duplicate in "
                    "the database. dup_count is %s, and dup_threshold is %s"
                    % (
                        onwards,
                        dup_checker.dup_count,
                        dup_checker.dup_threshold,
                    ),
                )
                self.assertTrue(
                    dup_checker.emulate_break,
                    "We should have hit a break but didn't.",
                )

    def test_press_on_with_dup_found_and_older_date(self) -> None:
        for dup_checker in self.dup_checkers:
            # Note that the next case occurs prior to the current one
            onwards = dup_checker.press_on(
                Opinion,
                now(),
                now() - timedelta(days=1),
                lookup_value=self.content_hash,
                lookup_by="sha1",
            )
            if dup_checker.full_crawl:
                self.assertFalse(
                    onwards,
                    "DupChecker returned True during a full crawl, but there "
                    "should be duplicates in the database.",
                )
                self.assertFalse(
                    dup_checker.emulate_break,
                    "DupChecker said to emulate a break during a full crawl. "
                    "Nothing should stop a full crawl!",
                )
            else:
                self.assertFalse(
                    onwards,
                    "DupChecker returned %s but there should be a duplicate in "
                    "the database. dup_count is %s, and dup_threshold is %s"
                    % (
                        onwards,
                        dup_checker.dup_count,
                        dup_checker.dup_threshold,
                    ),
                )
                self.assertTrue(
                    dup_checker.emulate_break,
                    "We should have hit a break but didn't.",
                )


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
        process_audio_file(pk=self.audio1.id)
        af.refresh_from_db()
        measured_duration: float = af.duration  # type: ignore
        # Use almost equal because measuring MP3's is wonky.
        self.assertAlmostEqual(
            measured_duration,
            expected_duration,
            delta=5,
            msg="We should end up with the proper duration of about %s. "
            "Instead we got %s." % (expected_duration, measured_duration),
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
