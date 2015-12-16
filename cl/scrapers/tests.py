# coding=utf-8
import os

from cl import settings
from cl.audio.models import Audio
from cl.lib.scrape_helpers import get_extension
from cl.lib.test_helpers import IndexedSolrTestCase
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.models import UrlHash, ErrorLog
from cl.scrapers.management.commands import (
    cl_report_scrape_status, cl_scrape_opinions, cl_scrape_oral_arguments
)
from cl.scrapers.tasks import (
    extract_from_txt, extract_doc_content, extract_by_ocr, process_audio_file
)
from cl.scrapers.test_assets import test_opinion_scraper, test_oral_arg_scraper
from cl.search.models import Court, Opinion

from celery.task.sets import subtask
from datetime import timedelta
from django.test import TestCase
from django.utils.timezone import now


class IngestionTest(IndexedSolrTestCase):
    fixtures = ['test_court.json']

    def test_ingest_opinions(self):
        """Can we successfully ingest opinions at a high level?"""
        site = test_opinion_scraper.Site()
        site.method = "LOCAL"
        parsed_site = site.parse()
        cl_scrape_opinions.Command().scrape_court(parsed_site, full_crawl=True)

        opinions = Opinion.objects.all()
        self.assertTrue(opinions.count() == 6, 'Should have 6 test opinions.')

    def test_ingest_oral_arguments(self):
        """Can we successfully ingest oral arguments at a high level?"""
        site = test_oral_arg_scraper.Site()
        site.method = "LOCAL"
        parsed_site = site.parse()
        cl_scrape_oral_arguments.Command().scrape_court(
            parsed_site,
            full_crawl=True
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

    def test_content_extraction(self):
        """Do all of the supported mimetypes get extracted to text
        successfully, including OCR?"""
        test_strings = [
            'supreme',
            'intelligence',
            'indiana',
            'reagan',
            'indiana',
            'fidelity'
        ]
        opinions = Opinion.objects.all()
        for op, test_string in zip(opinions, test_strings):
            ext = get_extension(op.local_path.file.read())
            op = extract_doc_content(op.pk, callback=subtask(extract_by_ocr))
            if ext in ['.html', '.wpd']:
                self.assertIn(test_string, op.html.lower())
            else:
                self.assertIn(test_string, op.plain_text.lower())


class ExtractionTest(TestCase):
    def test_txt_extraction_with_bad_data(self):
        """Can we extract text from nasty files lacking encodings?"""
        path = os.path.join(settings.MEDIA_ROOT, 'test', 'search',
                            'txt_file_with_no_encoding.txt')
        content, err = extract_from_txt(path)
        self.assertFalse(err, "Error reported while extracting text from %s" %
                         path)
        self.assertIn(u'¶  1.  DOOLEY, J.   Plaintiffs', content,
                      "Issue extracting/encoding text from file at: %s" % path)


class ReportScrapeStatusTest(TestCase):
    fixtures = ['test_court.json', 'judge_judy.json',
                'test_objects_search.json']

    def setUp(self):
        super(ReportScrapeStatusTest, self).setUp()
        self.court = Court.objects.get(pk='test')
        # Make some errors that we can tally
        ErrorLog(log_level='WARNING',
                 court=self.court,
                 message="test_msg").save()
        ErrorLog(log_level='CRITICAL',
                 court=self.court,
                 message="test_msg").save()

    def test_tallying_errors(self):
        errors = cl_report_scrape_status.tally_errors()
        self.assertEqual(
            errors['test'],
            [1, 1],
            msg="Did not get expected error counts. Instead got: %s" %
                errors['test'])

    @staticmethod
    def test_simple_report_generation():
        """Without doing the hard work of creating and checking for actual
        errors, can we at least generate the report?

        A better version of this test would check the contents of the generated
        report by importing it from the test inbox.
        """
        cl_report_scrape_status.generate_report()


class DupcheckerTest(TestCase):
    fixtures = ['test_court.json']

    def setUp(self):
        self.court = Court.objects.get(pk='test')
        self.dup_checkers = [DupChecker(self.court, full_crawl=True),
                             DupChecker(self.court, full_crawl=False)]

    def test_abort_when_new_court_website(self):
        """Tests what happens when a new website is discovered."""
        site = test_opinion_scraper.Site()
        site.hash = 'this is a dummy hash code string'

        for dup_checker in self.dup_checkers:
            abort = dup_checker.abort_by_url_hash(site.url, site.hash)
            if dup_checker.full_crawl:
                self.assertFalse(
                    abort,
                    "DupChecker says to abort during a full crawl."
                )
            else:
                self.assertFalse(
                    abort,
                    "DupChecker says to abort on a court that's never been "
                    "crawled before."
                )

            # The checking function creates url2Hashes, that we must delete as
            # part of cleanup.
            dup_checker.url_hash.delete()

    def test_abort_on_unchanged_court_website(self):
        """Similar to the above, but we create a UrlHash object before
        checking if it exists."""
        site = test_opinion_scraper.Site()
        site.hash = 'this is a dummy hash code string'
        for dup_checker in self.dup_checkers:
            UrlHash(id=site.url, sha1=site.hash).save()
            abort = dup_checker.abort_by_url_hash(site.url, site.hash)
            if dup_checker.full_crawl:
                self.assertFalse(
                    abort,
                    "DupChecker says to abort during a full crawl."
                )
            else:
                self.assertTrue(
                    abort,
                    "DupChecker says not to abort on a court that's been "
                    "crawled before with the same hash"
                )

            dup_checker.url_hash.delete()

    def test_abort_on_changed_court_website(self):
        """Similar to the above, but we create a UrlHash with a different
        hash before checking if it exists.
        """
        site = test_opinion_scraper.Site()
        site.hash = 'this is a dummy hash code string'
        for dup_checker in self.dup_checkers:
            UrlHash(pk=site.url, sha1=site.hash).save()
            abort = dup_checker.abort_by_url_hash(
                site.url,
                "this is a *different* hash!")
            if dup_checker.full_crawl:
                self.assertFalse(
                    abort,
                    "DupChecker says to abort during a full crawl."
                )
            else:
                self.assertFalse(
                    abort,
                    "DupChecker says to abort on a court where the hash has "
                    "changed."
                )

            dup_checker.url_hash.delete()

    def test_press_on_with_an_empty_database(self):
        site = test_opinion_scraper.Site()
        site.hash = 'this is a dummy hash code string'
        for dup_checker in self.dup_checkers:
            onwards = dup_checker.press_on(
                Opinion,
                now(),
                now() - timedelta(days=1),
                lookup_value='content',
                lookup_by='sha1'
            )
            if dup_checker.full_crawl:
                self.assertTrue(
                    onwards,
                    "DupChecker says to abort during a full crawl. This should "
                    "never happen."
                )
            elif dup_checker.full_crawl is False:
                count = Opinion.objects.all().count()
                self.assertTrue(
                    onwards,
                    "DupChecker says to abort on dups when the database has %s "
                    "Documents." % count
                )


class DupcheckerWithFixturesTest(TestCase):
    fixtures = ['test_court.json', 'judge_judy.json',
                'test_objects_search.json']

    def setUp(self):
        self.court = Court.objects.get(pk='test')

        # Set the dup_threshold to zero for these tests
        self.dup_checkers = [
            DupChecker(self.court, full_crawl=True, dup_threshold=0),
            DupChecker(self.court, full_crawl=False, dup_threshold=0),
        ]

        # Set up the hash value using one in the fixture.
        self.content_hash = 'asdfasdfasdfasdfasdfasddf'

    def test_press_on_with_a_dup_found(self):
        for dup_checker in self.dup_checkers:
            onwards = dup_checker.press_on(
                Opinion,
                now(),
                now(),
                lookup_value=self.content_hash,
                lookup_by='sha1'
            )
            if dup_checker.full_crawl:
                self.assertFalse(
                    onwards,
                    'DupChecker returned %s during a full crawl.' % onwards
                )

            elif dup_checker.full_crawl is False:
                self.assertFalse(
                    onwards,
                    "DupChecker returned %s but there should be a duplicate in "
                    "the database. dup_count is %s, and dup_threshold is %s" %
                    (onwards, dup_checker.dup_count, dup_checker.dup_threshold)
                )
                self.assertTrue(
                    dup_checker.emulate_break,
                    "We should have hit a break but didn't."
                )

    def test_press_on_with_dup_found_and_older_date(self):
        for dup_checker in self.dup_checkers:
            # Note that the next case occurs prior to the current one
            onwards = dup_checker.press_on(
                Opinion,
                now(),
                now() - timedelta(days=1),
                lookup_value=self.content_hash,
                lookup_by='sha1'
            )
            if dup_checker.full_crawl:
                self.assertFalse(
                    onwards,
                    'DupChecker says to %s during a full crawl.' % onwards)
            else:
                self.assertFalse(
                    onwards,
                    "DupChecker returned %s but there should be a duplicate in "
                    "the database. dup_count is %s, and dup_threshold is %s" %
                    (onwards, dup_checker.dup_count, dup_checker.dup_threshold)
                )
                self.assertTrue(
                    dup_checker.emulate_break,
                    "We should have hit a break but didn't."
                )

class AudioFileTaskTest(TestCase):

    fixtures = ['judge_judy.json', 'test_objects_search.json',
                'test_objects_audio.json']

    def test_process_audio_file(self):
        audio = Audio.objects.get(pk=1)
        audio.duration = None
        audio.save()

        audio = Audio.objects.get(pk=1)
        self.assertNotEqual(audio.duration, 15)

        process_audio_file(pk=1)
        audio = Audio.objects.get(pk=1)
        self.assertEqual(audio.duration, 15)
