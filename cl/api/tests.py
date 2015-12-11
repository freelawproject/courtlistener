from datetime import timedelta
import shutil
from django.core.urlresolvers import reverse
from django.http import HttpRequest, JsonResponse
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.utils.timezone import now

from cl.api.management.commands.cl_make_bulk_data import Command
from cl.api.views import coverage_data
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

    def test_rest_docs(self):
        r = self.client.get(reverse('rest_docs'))
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

    def test_coverage_api_via_url(self):
        # Should hit something like:
        #  https://www.courtlistener.com/api/rest/v2/coverage/ca2/
        r = self.client.get('/api/rest/v2/coverage/ca2/')
        self.assertEqual(r.status_code, 200)

    def test_api_info_page_displays_latest_rest_docs_by_default(self):
        response = self.client.get('/api/rest-info/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'rest-docs-vlatest.html')

    def test_api_info_page_can_display_different_versions_of_rest_docs(self):
        for version in ['v1', 'v2']:
            response = self.client.get('/api/rest-info/%s/' % (version,))
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, 'rest-docs-%s.html' % (version,))
            self.assertContains(response, 'REST API - %s' % (version.upper(),))


class ApiViewTest(TestCase):
    """Tests views in API module via direct calls and not HTTP"""

    def test_coverage_data_view_provides_court_data(self):
        response = coverage_data(HttpRequest(), 'v2', 'ca9')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        self.assertContains(response, 'annual_counts')
        self.assertContains(response, 'total')
