# coding=utf-8
import hashlib
import os
import time

from cl import settings
from cl.audio.models import Audio
from cl.lib.solr_core_admin import (
    create_solr_core, delete_solr_core, swap_solr_core
)
from cl.lib.string_utils import trunc
from cl.lib import sunburnt
from cl.lib.test_helpers import CitationTest
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.models import UrlHash, ErrorLog
from cl.scrapers.management.commands.cl_report_scrape_status import \
    generate_report
from cl.scrapers.management.commands.cl_scrape_opinions import get_extension
from cl.scrapers.management.commands.cl_scrape_opinions import \
    Command as OpinionCommand
from cl.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgCommand
from cl.scrapers.management.commands.cl_report_scrape_status import \
    tally_errors
from cl.scrapers.tasks import extract_from_txt, extract_doc_content, \
    extract_by_ocr
from cl.scrapers.test_assets import test_opinion_scraper, \
    test_oral_arg_scraper
from cl.search.models import Court, Document, Docket

from celery.task.sets import subtask
from datetime import timedelta
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils.timezone import now


class IngestionTest(TestCase):
    fixtures = ['test_court.json']

    def setUp(self):
        # Set up a testing core in Solr and swap it in
        self.core_name = '%s.test-%s' % (self.__module__, time.time())
        create_solr_core(self.core_name)
        swap_solr_core('collection1', self.core_name)
        self.si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='rw')

        # Set up a handy court object
        self.court = Court.objects.get(pk='test')

    def tearDown(self):
        swap_solr_core(self.core_name, 'collection1')
        delete_solr_core(self.core_name)

    def test_ingest_opinions(self):
        """Can we successfully ingest opinions at a high level?"""
        site = test_opinion_scraper.Site()
        site.method = "LOCAL"
        parsed_site = site.parse()
        OpinionCommand().scrape_court(parsed_site, full_crawl=True)

    def test_ingest_oral_arguments(self):
        """Can we successfully ingest oral arguments at a high level?"""
        site = test_oral_arg_scraper.Site()
        site.method = "LOCAL"
        parsed_site = site.parse()
        OralArgCommand().scrape_court(parsed_site, full_crawl=True)

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
        site = test_opinion_scraper.Site().parse()

        test_strings = [
            'supreme',
            'intelligence',
            'indiana',
            'reagan',
            'indiana',
            'fidelity'
        ]
        for i in range(0, len(site.case_names)):
            path = os.path.join(settings.INSTALL_ROOT, 'alert',
                                site.download_urls[i])
            with open(path) as f:
                content = f.read()
                cf = ContentFile(content)
                extension = get_extension(content)
            docket = Docket(
                case_name=site.case_names[i],
                court=self.court,
            )
            docket.save()
            doc = Document(
                date_filed=site.case_dates[i],
                docket=docket,
            )
            file_name = trunc(site.case_names[i].lower(), 75) + extension
            doc.local_path.save(file_name, cf, save=False)
            doc.save(index=False)
            doc = extract_doc_content(doc.pk, callback=subtask(extract_by_ocr))
            if extension in ['.html', '.wpd']:
                self.assertIn(test_strings[i], doc.html.lower())
            else:
                self.assertIn(test_strings[i], doc.plain_text.lower())

            doc.delete()

    def test_solr_ingestion_and_deletion(self):
        """Do items get added to the Solr index when they are ingested?"""
        site = test_opinion_scraper.Site().parse()
        path = os.path.join(
            settings.INSTALL_ROOT,
            'alert',
            site.download_urls[0]
        )  # a simple PDF
        with open(path) as f:
            content = f.read()
            cf = ContentFile(content)
            extension = get_extension(content)
        docket = Docket(
            court=self.court,
            case_name=site.case_names[0],
        )
        docket.save()
        doc = Document(
            date_filed=site.case_dates[0],
            docket=docket,
        )
        file_name = trunc(site.case_names[0].lower(), 75) + extension
        doc.local_path.save(file_name, cf, save=False)
        doc.save(index=False)

        # Extract content and then find citations. Once complete, commit the
        # changes.
        extract_doc_content(doc.pk, callback=subtask(extract_by_ocr))
        self.si.commit()

        response = self.si.raw_query(**{'q': 'supreme', 'caller': 'scraper_test',}).execute()
        count = response.result.numFound
        self.assertEqual(count, 1, "There were %s items found when there should have been 1" % count)


class ExtractionTest(TestCase):
    def test_txt_extraction_with_bad_data(self):
        """Can we extract text from nasty files lacking encodings?"""
        path = os.path.join(settings.INSTALL_ROOT, 'alert', 'scrapers', 'test_assets', 'txt_file_with_no_encoding.txt')
        content, err = extract_from_txt(path)
        self.assertFalse(err, "Error reported while extracting text from %s" % path)
        self.assertIn(u'¶  1.  DOOLEY, J.   Plaintiffs', content,
                      "Issue extracting/encoding text from file at: %s" % path)


class ReportScrapeStatusTest(CitationTest):
    def setUp(self):
        super(ReportScrapeStatusTest, self).setUp()

        # Make some errors that we can tally
        ErrorLog(log_level='WARNING',
                 court=self.court,
                 message="test_msg").save()
        ErrorLog(log_level='CRITICAL',
                 court=self.court,
                 message="test_msg").save()

    def test_tallying_errors(self):
        errors = tally_errors()
        self.assertEqual(
            errors['test'],
            [1, 1],
            msg="Did not get expected error counts. Instead got: %s" %
                errors['test'])

    def test_simple_report_generation(self):
        """Without doing the hard work of creating and checking for actual
        errors, can we at least generate the report?"""
        generate_report()


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
            dup_checker.url2Hash.delete()

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

            dup_checker.url2Hash.delete()

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

            dup_checker.url2Hash.delete()

    def test_press_on_with_an_empty_database(self):
        for dup_checker in self.dup_checkers:
            onwards = dup_checker.press_on(
                Document,
                now(),
                now() - timedelta(days=1),
                hash=site.hash
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
                count = Document.objects.all().count()
                self.assertTrue(
                    onwards,
                    "DupChecker says to abort on dups when the database has %s "
                    "Documents." % count
                )

    def test_press_on_with_a_dup_found(self):
        # Set the dup_threshold to zero for this test
        self.dup_checkers = [DupChecker(self.court,
                                        full_crawl=True,
                                        dup_threshold=0),
                             DupChecker(self.court,
                                        full_crawl=False,
                                        dup_threshold=0)]
        content = "this is dummy content that we hash"
        content_hash = hashlib.sha1(content).hexdigest()
        for dup_checker in self.dup_checkers:
            # Create a document, then use the dup_checker to see if it exists.
            docket = Docket(court=self.court)
            docket.save()
            doc = Document(sha1=content_hash, docket=docket)
            doc.save(index=False)
            onwards = dup_checker.press_on(
                Document,
                now(),
                now(),
                lookup_value=content_hash,
                lookup_by='sha1'
            )
            if dup_checker.full_crawl:
                self.assertTrue(
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

            doc.delete()

    def test_press_on_with_dup_found_and_older_date(self):
        content = "this is dummy content that we hash"
        content_hash = hashlib.sha1(content).hexdigest()
        for dup_checker in self.dup_checkers:
            docket = Docket(court=self.court)
            docket.save()
            doc = Document(sha1=content_hash, docket=docket)
            doc.save(index=False)
            # Note that the next case occurs prior to the current one
            onwards = dup_checker.press_on(
                Document,
                now(),
                now() - timedelta(days=1),
                lookup_value=content_hash,
                lookup_by='sha1'
            )
            if dup_checker.full_crawl:
                self.assertTrue(
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
            doc.delete()
