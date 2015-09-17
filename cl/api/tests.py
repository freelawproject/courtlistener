from datetime import timedelta
import shutil
from django.core.urlresolvers import reverse
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.utils.timezone import now

from cl.api.management.commands.cl_make_bulk_data import Command
from cl.search.models import Docket, Court, OpinionCluster
from cl.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgumentCommand
from cl.scrapers.test_assets import test_oral_arg_scraper


class BulkDataTest(TestCase):
    fixtures = ['test_court.json']
    tmp_data_dir = '/tmp/bulk-dir/'

    def setUp(self):
        docket = Docket(
            case_name=u'foo',
            court=Court.objects.get(pk='test'),
        )
        docket.save()
        # Must be more than a year old for all tests to be runnable.
        last_month = now().date() - timedelta(days=400)
        self.doc_cluster = OpinionCluster(
            case_name=u"foo",
            docket=docket,
            date_filed=last_month
        )
        self.doc_cluster.save(index=False)

        # Scrape the audio "site" and add its contents
        site = test_oral_arg_scraper.Site().parse()
        OralArgumentCommand().scrape_court(site, full_crawl=True)

    def tearDown(self):
        OpinionCluster.objects.all().delete()
        Docket.objects.all().delete()
        shutil.rmtree(self.tmp_data_dir)

    @override_settings(BULK_DATA_DIR=tmp_data_dir)
    def test_make_all_bulk_files(self):
        """Can we successfully generate all bulk files?"""
        Command().execute()

class BasicAPIPageTest(TestCase):
    """Test the basic views"""

    def setUp(self):
        self.client = Client()

    def test_api_index(self):
        r = self.client.get(reverse('api_index'))
        self.assertEqual(r.status_code, 200)

    def test_court_index(self):
        r = self.client.get(reverse('court_index'))
        self.assertEqual(r.status_code, 200)

    def test_rest_index(self):
        r = self.client.get(reverse('rest_index'))
        self.assertEqual(r.status_code, 200)

    def test_bulk_data_index(self):
        r = self.client.get(reverse('bulk_data_index'))
        self.assertEqual(r.status_code, 200)

    def test_pagerank_file(self):
        r = self.client.get(reverse('pagerank_file'))
        self.assertEqual(r.status_code, 200)

    def test_coverage_api(self):
        r = self.client.get(reverse('coverage_api',
                                    kwargs={'version': 2, 'court': 'ca9'}))
        self.assertEqual(r.status_code, 200)
