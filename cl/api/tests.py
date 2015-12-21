from datetime import timedelta, date
import shutil
from django.core.urlresolvers import reverse
from django.http import HttpRequest, JsonResponse
from django.test import Client, TestCase, override_settings
from django.utils.timezone import now

from cl.audio.models import Audio
from cl.api.management.commands.cl_make_bulk_data import Command
from cl.api.views import coverage_data
from cl.search.models import \
    Docket, Court, Opinion, OpinionCluster, OpinionsCited
from cl.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgumentCommand
from cl.scrapers.test_assets import test_oral_arg_scraper


class BulkDataTest(TestCase):
    fixtures = ['court_data.json']
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
        opinion = Opinion.objects.create(
            cluster=self.doc_cluster,
            type='Lead Opinion'
        )
        opinion2 = Opinion.objects.create(
            cluster=self.doc_cluster,
            type='Concurrence'
        )
        OpinionsCited.objects.create(
            citing_opinion=opinion2,
            cited_opinion=opinion
        )

        # Scrape the audio "site" and add its contents
        site = test_oral_arg_scraper.Site().parse()
        OralArgumentCommand().scrape_court(site, full_crawl=True)

    def tearDown(self):
        OpinionCluster.objects.all().delete()
        Docket.objects.all().delete()
        try:
            shutil.rmtree(self.tmp_data_dir)
        except OSError:
            pass

    @override_settings(BULK_DATA_DIR=tmp_data_dir)
    def test_make_all_bulk_files(self):
        """Can we successfully generate all bulk files?"""
        Command().execute()

    def test_database_has_objects_for_bulk_export(self):
        self.assertTrue(Opinion.objects.count() > 0, 'Opinions exist')
        self.assertTrue(Audio.objects.count() > 0, 'Audio exist')
        self.assertTrue(Docket.objects.count() > 0, 'Docket exist')
        self.assertTrue(Court.objects.count() > 0, 'Court exist')
        self.assertEqual(
            Court.objects.get(pk='test').full_name,
            'Testing Supreme Court'
        )


class BasicAPIPageTest(TestCase):
    """Test the basic views"""
    fixtures = ['judge_judy.json', 'test_objects_search.json']

    def setUp(self):
        self.client = Client()

        # Need pagerank file for test_pagerank_file()
        from cl.search.management.commands.cl_calculate_pagerank_networkx \
            import Command
        command = Command()
        command.do_pagerank(chown=False)

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
        r = self.client.get(reverse('coverage_data',
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
            header = 'REST API &ndash; %s' % (version.upper(),)
            self.assertContains(response, header)


class ApiViewTest(TestCase):
    """Tests views in API module via direct calls and not HTTP"""

    def test_coverage_data_view_provides_court_data(self):
        response = coverage_data(HttpRequest(), 'v2', 'ca9')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        self.assertContains(response, 'annual_counts')
        self.assertContains(response, 'total')


class DRFJudgeApiFilterTests(TestCase):
    """Do the filters work properly?"""
    fixtures = ['judge_judy.json']

    def assertCount(self, path, q, expected_count):
        r = self.client.get(path, q)
        self.assertEqual(len(r.data['results']), expected_count)

    def test_judge_filtering_by_first_name(self):
        """Can we filter by first name?"""
        path = reverse('judge-list', kwargs={'version': 'v3'})

        # Filtering with good values brings back 1 result.
        q = {'name_first__istartswith': 'judith'}
        self.assertCount(path, q, 1)

        # Filtering with bad values brings back no results.
        q = {'name_first__istartswith': 'XXX'}
        self.assertCount(path, q, 0)

    def test_judge_filtering_by_date(self):
        """Do the various date filters work properly?"""
        path = reverse('judge-list', kwargs={'version': 'v3'})

        # Exact match for her birthday
        correct_date = date(1942, 10, 21)
        q = {'date_dob': correct_date.isoformat()}
        self.assertCount(path, q, 1)

        # People born after the day before her birthday
        before = correct_date - timedelta(days=1)
        q = {'date_dob__gt': before.isoformat()}
        self.assertCount(path, q, 1)

        # Flip the logic. This should return no results.
        q = {'date_dob__lt': before.isoformat()}
        self.assertCount(path, q, 0)

    def test_nested_judge_filtering(self):
        """Can we filter across various relations?

        Each of these assertions adds another parameter making our final test
        a pretty complex combination.
        """
        path = reverse('judge-list', kwargs={'version': 'v3'})
        q = dict()

        # No results for a bad query
        q['educations__degree'] = 'XXX'
        self.assertCount(path, q, 0)

        # One result for a good query
        q['educations__degree'] = 'JD'
        self.assertCount(path, q, 1)

        # Again, no results
        q['educations__degree_year'] = 1400
        self.assertCount(path, q, 0)

        # But with the correct year...one result
        q['educations__degree_year'] = 1965
        self.assertCount(path, q, 1)

        # Judy went to "New York Law School"
        q['educations__school__name__istartswith'] = "New York Law"
        self.assertCount(path, q, 1)

        # Moving on to careers. Bad value, then good.
        q['careers__job_title__icontains'] = 'XXX'
        self.assertCount(path, q, 0)
        q['careers__job_title__icontains'] = 'lawyer'
        self.assertCount(path, q, 1)

        # Moving on to titles...bad value, then good.
        q['titles__title_name'] = 'XXX'
        self.assertCount(path, q, 0)
        q['titles__title_name'] = 'c-jud'
        self.assertCount(path, q, 1)

        # Political affiliation filtering...bad, then good.
        q['political_affiliations__political_party'] = 'XXX'
        self.assertCount(path, q, 0)
        q['political_affiliations__political_party'] = 'd'
        self.assertCount(path, q, 1)

        # Sources
        about_now = '2015-12-17T00:00:00Z'
        q['sources__date_modified__gt'] = about_now
        self.assertCount(path, q, 0)
        q.pop('sources__date_modified__gt')  # Next key doesn't overwrite.
        q['sources__date_modified__lt'] = about_now
        self.assertCount(path, q, 1)

        # ABA Ratings
        q['aba_ratings__rating'] = 'q'
        self.assertCount(path, q, 0)
        q['aba_ratings__rating'] = 'nq'
        self.assertCount(path, q, 1)

    def test_education_filtering(self):
        """Can we filter education objects?"""
        path = reverse('education-list', kwargs={'version': 'v3'})
        q = dict()

        # Filter by degree
        q['degree'] = 'XXX'
        self.assertCount(path, q, 0)
        q['degree'] = 'JD'
        self.assertCount(path, q, 1)

        # Filter by degree's related field, School
        q['school__name__istartswith'] = 'XXX'
        self.assertCount(path, q, 0)
        q['school__name__istartswith'] = 'New York'
        self.assertCount(path, q, 1)

    def test_title_filtering(self):
        """Can Judge Titles be filtered?"""
        path = reverse('title-list', kwargs={'version': 'v3'})
        q = dict()

        # Filter by title_name
        q['title_name'] = 'XXX'
        self.assertCount(path, q, 0)
        q['title_name'] = 'c-jud'
        self.assertCount(path, q, 1)

    def test_reverse_filtering(self):
        """Can we filter Source objects by judge name?"""
        # I want any source notes about judge judy.
        path = reverse('source-list', kwargs={'version': 'v3'})
        q = {'judge': 1}
        self.assertCount(path, q, 1)

    def test_position_filters(self):
        """Can we filter on positions"""
        path = reverse('position-list', kwargs={'version': 'v3'})
        q = dict()

        # I want positions to do with judge #1 (Judy)
        q['judge'] = 1
        self.assertCount(path, q, 1)

        # Retention events
        q['rentention_events__retention_type'] = 'reapp_gov'
        self.assertCount(path, q, 1)

        # Appointer was Bill, a Democrat
        q['appointer__name_first__istartswith'] = 'bill'
        q['appointer__political_affiliations__political_party'] = 'd'
        self.assertCount(path, q, 1)
        # She was not appointed by a Republican
        q['appointer__political_affiliations__political_party'] = 'r'
        self.assertCount(path, q, 0)

    def test_racial_filters(self):
        """Can we filter by race?"""
        path = reverse('judge-list', kwargs={'version': 'v3'})
        q = {'race': 'w'}
        self.assertCount(path, q, 1)

        # Do an OR. This returns judges that are either black or white (not
        # that it matters, MJ)
        q['race'] = ['w', 'b']
        self.assertCount(path, q, 1)


class DRFFieldSelectionTest(TestCase):
    fixtures = ['judge_judy.json', 'test_objects_search.json']

    def test_only_some_fields_returned(self):
        """Can we return only some of the fields?"""

        # First check the Judge endpoint, one of our more compliated ones.
        path = reverse('judge-list', kwargs={'version': 'v3'})
        fields_to_return = ['educations', 'date_modified', 'slug']
        q = {'fields': ','.join(fields_to_return)}
        r = self.client.get(path, q)
        self.assertEqual(len(r.data['results'][0].keys()),
                         len(fields_to_return))

        # One more check for good measure.
        path = reverse('opinioncluster-list', kwargs={'version': 'v3'})
        fields_to_return = ['per_curiam', 'slug']
        r = self.client.get(path, q)
        self.assertEqual(len(r.data['results'][0].keys()),
                         len(fields_to_return))
