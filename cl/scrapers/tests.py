import os
from datetime import timedelta

from django.conf import settings
from django.test import TestCase
from django.utils.timezone import now

from cl.audio.models import Audio
from cl.lib.test_helpers import IndexedSolrTestCase
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.management.commands import (
    cl_report_scrape_status,
    cl_scrape_opinions,
    cl_scrape_oral_arguments,
)
from cl.scrapers.models import ErrorLog, UrlHash
from cl.scrapers.tasks import (
    extract_doc_content,
    extract_from_txt,
    process_audio_file,
)
from cl.scrapers.test_assets import test_opinion_scraper, test_oral_arg_scraper
from cl.scrapers.transformer_extractor_utils import convert_and_clean_audio
from cl.scrapers.utils import get_extension
from cl.search.models import Court, Opinion


class ScraperIngestionTest(TestCase):
    fixtures = ["test_court.json"]

    def test_ingest_opinions_from_scraper(self) -> None:
        """Can we successfully ingest opinions at a high level?"""
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
            "Should have 6 test opinions, not %s" % count,
        )

    def test_ingest_oral_arguments(self):
        """Can we successfully ingest oral arguments at a high level?"""
        site = test_oral_arg_scraper.Site()
        site.method = "LOCAL"
        parsed_site = site.parse()
        cl_scrape_oral_arguments.Command().scrape_court(
            parsed_site, full_crawl=True
        )

        # There should now be two items in the database.
        audio_files = Audio.objects.all()
        self.assertEqual(2, audio_files.count())

    def test_parsing_xml_opinion_site_to_site_object(self):
        """Does a basic parse of a site reveal the right number of items?"""
        site = test_opinion_scraper.Site().parse()
        self.assertEqual(len(site.case_names), 6)

    def test_parsing_xml_oral_arg_site_to_site_object(self):
        """Does a basic parse of an oral arg site work?"""
        site = test_oral_arg_scraper.Site().parse()
        self.assertEqual(len(site.case_names), 2)


class IngestionTest(IndexedSolrTestCase):
    def test_doc_content_extraction(self):
        """Can we ingest a doc file?"""
        image_opinion = Opinion.objects.get(pk=1)
        extract_doc_content(image_opinion.pk, ocr_available=False)
        image_opinion.refresh_from_db()
        self.assertIn("indiana", image_opinion.plain_text.lower())

    def test_image_based_pdf(self):
        """Can we ingest an image based pdf file?"""
        image_opinion = Opinion.objects.get(pk=2)
        extract_doc_content(image_opinion.pk, ocr_available=True)
        image_opinion.refresh_from_db()
        self.assertIn("intelligence", image_opinion.plain_text.lower())

    def test_text_based_pdf(self):
        """Can we ingest a text based pdf file?"""
        txt_opinion = Opinion.objects.get(pk=3)
        extract_doc_content(txt_opinion.pk, ocr_available=False)
        txt_opinion.refresh_from_db()
        self.assertIn("tarrant", txt_opinion.plain_text.lower())

    def test_html_content_extraction(self):
        """Can we ingest an html file?"""
        html_opinion = Opinion.objects.get(pk=4)
        extract_doc_content(html_opinion.pk, ocr_available=False)
        html_opinion.refresh_from_db()
        self.assertIn("reagan", html_opinion.html.lower())

    def test_wpd_content_extraction(self):
        """Can we ingest a wpd file?"""
        wpd_opinion = Opinion.objects.get(pk=5)
        extract_doc_content(wpd_opinion.pk, ocr_available=False)
        wpd_opinion.refresh_from_db()
        self.assertIn("greene", wpd_opinion.html.lower())

    def test_txt_content_extraction(self):
        """Can we ingest a txt file?"""
        txt_opinion = Opinion.objects.get(pk=6)
        extract_doc_content(txt_opinion.pk, ocr_available=False)
        txt_opinion.refresh_from_db()
        self.assertIn("ideal", txt_opinion.plain_text.lower())

    def test_txt_extraction_with_bad_data(self):
        """Can we extract text from nasty files lacking encodings?"""

        path = os.path.join(
            settings.MEDIA_ROOT,
            "test",
            "search",
            "txt_file_with_no_encoding.txt",
        )
        content, err = extract_from_txt(path)
        self.assertFalse(
            err, "Error reported while extracting text from %s" % path
        )
        self.assertIn(
            "¶  1.  DOOLEY, J.   Plaintiffs",
            content,
            "Issue extracting/encoding text from file at: %s" % path,
        )


class ExtractionTest(TestCase):
    fixtures = ["tax_court_test.json"]

    def test_juriscraper_object_creation(self):
        """Can we extract text from tax court pdf and add to db?"""

        o = Opinion.objects.get(pk=76)
        self.assertFalse(
            o.cluster.citations.exists(),
            msg="Citation should not exist at beginning of test",
        )

        extract_doc_content(pk=o.pk, ocr_available=False)
        self.assertTrue(
            o.cluster.citations.exists(),
            msg="Expected citation was not created in db",
        )

    def test_juriscraper_docket_number_extraction(self):
        """Can we extract docket number from tax court pdf and add to db?"""

        o = Opinion.objects.get(pk=76)
        self.assertEqual(
            None,
            o.cluster.docket.docket_number,
            msg="Docket number should be none.",
        )
        extract_doc_content(pk=76, ocr_available=False)
        o.cluster.docket.refresh_from_db()
        self.assertEqual(
            "19031-13, 27735-13, 11905-14", o.cluster.docket.docket_number
        )


class ExtensionIdentificationTest(TestCase):
    def setUp(self):
        self.path = os.path.join(settings.MEDIA_ROOT, "test", "search")

    def test_wpd_extension(self):
        with open(os.path.join(self.path, "opinion_wpd.wpd"), "rb") as f:
            data = f.read()
        self.assertEqual(get_extension(data), ".wpd")

    def test_pdf_extension(self):
        with open(
            os.path.join(self.path, "opinion_pdf_text_based.pdf"), "rb"
        ) as f:
            data = f.read()
        self.assertEqual(get_extension(data), ".pdf")

    def test_doc_extension(self):
        with open(os.path.join(self.path, "opinion_doc.doc"), "rb") as f:
            data = f.read()
        self.assertEqual(get_extension(data), ".doc")

    def test_html_extension(self):
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

    def setUp(self):
        super(ReportScrapeStatusTest, self).setUp()
        self.court = Court.objects.get(pk="test")
        # Make some errors that we can tally
        ErrorLog(
            log_level="WARNING", court=self.court, message="test_msg"
        ).save()
        ErrorLog(
            log_level="CRITICAL", court=self.court, message="test_msg"
        ).save()

    def test_tallying_errors(self):
        errors = cl_report_scrape_status.tally_errors()
        self.assertEqual(
            errors["test"],
            [1, 1],
            msg="Did not get expected error counts. Instead got: %s"
            % errors["test"],
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

    def setUp(self):
        self.court = Court.objects.get(pk="test")
        self.dup_checkers = [
            DupChecker(self.court, full_crawl=True),
            DupChecker(self.court, full_crawl=False),
        ]

    def test_abort_when_new_court_website(self):
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

    def test_abort_on_unchanged_court_website(self):
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

    def test_abort_on_changed_court_website(self):
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

    def test_press_on_with_an_empty_database(self):
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

    def setUp(self):
        super(DupcheckerWithFixturesTest, self).setUp()
        self.court = Court.objects.get(pk="test")

        # Set the dup_threshold to zero for these tests
        self.dup_checkers = [
            DupChecker(self.court, full_crawl=True, dup_threshold=0),
            DupChecker(self.court, full_crawl=False, dup_threshold=0),
        ]

        # Set up the hash value using one in the fixture.
        self.content_hash = "asdfasdfasdfasdfasdfasddf"

    def test_press_on_with_a_dup_found(self):
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

    def test_press_on_with_dup_found_and_older_date(self):
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

    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
        "test_objects_audio.json",
    ]

    def test_process_audio_file(self):
        af = Audio.objects.get(pk=1)
        af.duration = None
        af.save()

        expected_duration = 15
        self.assertNotEqual(
            af.duration,
            expected_duration,
            msg="Do we have no duration info at the outset?",
        )

        process_audio_file(pk=1)
        af.refresh_from_db()
        measured_duration = af.duration
        # Use almost equal because measuring MP3's is wonky.
        self.assertAlmostEqual(
            measured_duration,
            expected_duration,
            delta=5,
            msg="We should end up with the proper duration of about %s. "
            "Instead we got %s." % (expected_duration, measured_duration),
        )

    def test_BTE_audio_conversion(self):
        """Can we convert wav to audio and update the metadata"""
        audio_obj = Audio.objects.get(pk=1)
        bte_respone_obj = convert_and_clean_audio(audio_obj)
        self.assertEqual(
            bte_respone_obj.status_code,
            200,
            msg="Unsuccessful audio conversion",
        )
