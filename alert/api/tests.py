from datetime import timedelta
import os
import time
from django.conf import settings
from django.test import TestCase
from django.utils.timezone import now
from alert.lib.dump_lib import make_dump_file
from alert.search.models import Docket, Citation, Court, Document


class BulkDataTest(TestCase):
    fixtures = ['test_court.json']

    def setUp(self):
        c1 = Citation(case_name=u"foo")
        c1.save(index=False)
        docket = Docket(
            case_name=u'foo',
            court=Court.objects.get(pk='test'),
        )
        docket.save()
        # Must be more than a year old for all tests to be runnable.
        last_month = now().date() - timedelta(days=400)
        self.doc = Document(
            citation=c1,
            docket=docket,
            date_filed=last_month
        )
        self.doc.save(index=False)

        self.day = last_month.day
        self.month = last_month.month
        self.year = last_month.year
        self.now = now().date()

    def tearDown(self):
        self.doc.delete()

    def test_no_year_provided_with_court_provided(self):
        """When a user doesn't provide a year and wants everything for a
        particular court, do we properly throw a 400 error?
        """
        r = self.client.get('/api/bulk/test.xml.gz')
        self.assertEqual(
            r.status_code,
            400,
            msg="Should have gotten HTTP code 400. Instead got: %s" % r.status_code
        )

    def test_no_year_provided_all_courts_requested(self):
        """If a user requests everything, do we give it to them?"""
        start_moment = time.time()
        qs = Document.objects.all()
        filename = 'all.xml'
        make_dump_file(qs, settings.DUMP_DIR, filename)
        r = self.client.get('/api/bulk/all.xml.gz')

        # Normally, the redirect hands the user off to Apache, which serves the file.
        # Since we don't always have apache set up, we make sure we get redirected and
        # we check that the file exists on disk with a non-zero filesize.
        self.assertEqual(
            r.status_code,
            302,
            msg="Redirection to bulk file failed."
        )
        file_path = os.path.join(settings.DUMP_DIR, filename + '.gz')
        self.assertGreater(
            os.path.getsize(file_path),
            0,
            msg="Bulk data file does not have content."
        )
        self.assertGreater(
            os.stat(file_path).st_mtime,
            start_moment,
            msg="File was created before the test was run, indicating it predates this test."
        )

    def test_year_based_bulk_file(self):
        """Do we generate and provide year-based bulk files properly?"""
        r = self.client.get('/api/bulk/%s/test.xml.gz' % self.year)
        self.assertEqual(r.status_code, 302, msg="Got status code of %s with content: %s" %
                                                 (r.status_code, r.content))

    def test_month_based_bulk_file(self):
        """Do we generate and provide month-based bulk files properly?"""
        r = self.client.get('/api/bulk/%s/%s/test.xml.gz' % (self.year, self.month))
        self.assertEqual(r.status_code, 302, msg="Got status code of %s with content: %s" %
                                                 (r.status_code, r.content))

    def test_day_based_bulk_file_twice(self):
        """Do we generate and provide day-based bulk files properly?

        When they come from the cache the second time, does it still work?
        """
        r = self.client.get('/api/bulk/%s/%s/%s/test.xml.gz' % (self.year, self.month, self.day))
        self.assertEqual(r.status_code, 302, msg="Got status code of %s with content: %s" %
                                                 (r.status_code, r.content))
        # 2x!
        r = self.client.get('/api/bulk/%s/%s/%s/test.xml.gz' % (self.year, self.month, self.day))
        self.assertEqual(r.status_code, 302, msg="Got status code of %s with content: %s" %
                                                 (r.status_code, r.content))

    def test_month_not_yet_complete(self):
        """A limitation is that we do not serve files until the month is complete.

        Do we throw the proper error when this is the case?
        """
        r = self.client.get('/api/bulk/%s/%s/test.xml.gz' % (self.now.year, self.now.month))
        self.assertEqual(r.status_code, 400)
        self.assertIn('partially in the future', r.content, msg="Did not get correct error message. "
                                                                "Instead got: %s" % r.content)

    def test_month_completely_in_the_future(self):
        """Do we throw an error when a date in the future is requested?"""
        r = self.client.get('/api/bulk/%s/%s/test.xml.gz' % (self.now.year + 1, self.now.month))
        self.assertEqual(r.status_code, 400)
        self.assertIn('date is in the future', r.content, msg="Did not get correct error message. "
                                                              "Instead got: %s" % r.content)

    def test_no_data_for_time_period(self):
        """If we lack data for a period of time, do we throw an error?"""
        r = self.client.get('/api/bulk/1982/06/09/test.xml.gz')
        self.assertEqual(r.status_code, 404)
        self.assertIn('not have any data', r.content, msg="Did not get correct error message. "
                                                          "Instead got: %s" % r.content)
