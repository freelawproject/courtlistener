import shutil
from datetime import timedelta, date

from django.core.urlresolvers import reverse
from django.http import HttpRequest, JsonResponse
from django.test import Client, TestCase, override_settings
from django.utils.timezone import now

from cl.api.management.commands.cl_make_bulk_data import Command
from cl.api.utils import BulkJsonHistory
from cl.api.views import coverage_data
from cl.audio.models import Audio
from cl.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgumentCommand
from cl.scrapers.test_assets import test_oral_arg_scraper
from cl.search.models import \
    Docket, Court, Opinion, OpinionCluster, OpinionsCited


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
        Audio.objects.all().delete()
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
    fixtures = ['court_data.json', 'judge_judy.json',
                'test_objects_search.json']

    def setUp(self):
        self.client = Client()

        # Need pagerank file for test_pagerank_file()
        from cl.search.management.commands.cl_calculate_pagerank import Command
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
    fixtures = ['court_data.json']

    def test_coverage_data_view_provides_court_data(self):
        response = coverage_data(HttpRequest(), 'v2', 'ca9')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        self.assertContains(response, 'annual_counts')
        self.assertContains(response, 'total')


def assertCount(cls, path, q, expected_count):
    cls.client.login(username='pandora', password='password')
    print "Path and q are: %s, %s" % (path, q)
    r = cls.client.get(path, q)
    cls.assertEqual(len(r.data['results']), expected_count,
                    msg="r.data was: %s" % r.data)


class DRFJudgeApiFilterTests(TestCase):
    """Do the filters work properly?"""
    fixtures = ['judge_judy.json', 'user_with_judge_access.json',
                'court_data.json']

    def test_judge_filtering_by_first_name(self):
        """Can we filter by first name?"""
        path = reverse('person-list', kwargs={'version': 'v3'})

        # Filtering with good values brings back 1 result.
        q = {'name_first__istartswith': 'judith'}
        assertCount(self, path, q, 1)

        # Filtering with bad values brings back no results.
        q = {'name_first__istartswith': 'XXX'}
        assertCount(self, path, q, 0)

    def test_judge_filtering_by_date(self):
        """Do the various date filters work properly?"""
        path = reverse('person-list', kwargs={'version': 'v3'})

        # Exact match for her birthday
        correct_date = date(1942, 10, 21)
        q = {'date_dob': correct_date.isoformat()}
        assertCount(self, path, q, 1)

        # People born after the day before her birthday
        before = correct_date - timedelta(days=1)
        q = {'date_dob__gt': before.isoformat()}
        assertCount(self, path, q, 1)

        # Flip the logic. This should return no results.
        q = {'date_dob__lt': before.isoformat()}
        assertCount(self, path, q, 0)

    def test_nested_judge_filtering(self):
        """Can we filter across various relations?

        Each of these assertions adds another parameter making our final test
        a pretty complex combination.
        """
        path = reverse('person-list', kwargs={'version': 'v3'})
        q = dict()

        # No results for a bad query
        q['educations__degree_level'] = 'XXX'
        assertCount(self, path, q, 0)

        # One result for a good query
        q['educations__degree_level'] = 'jd'
        assertCount(self, path, q, 1)

        # Again, no results
        q['educations__degree_year'] = 1400
        assertCount(self, path, q, 0)

        # But with the correct year...one result
        q['educations__degree_year'] = 1965
        assertCount(self, path, q, 1)

        # Judy went to "New York Law School"
        q['educations__school__name__istartswith'] = "New York Law"
        assertCount(self, path, q, 1)

        # Moving on to careers. Bad value, then good.
        q['positions__job_title__icontains'] = 'XXX'
        assertCount(self, path, q, 0)
        q['positions__job_title__icontains'] = 'lawyer'
        assertCount(self, path, q, 1)

        # Moving on to titles...bad value, then good.
        q['positions__position_type'] = 'XXX'
        assertCount(self, path, q, 0)
        q['positions__position_type'] = 'c-jud'
        assertCount(self, path, q, 1)

        # Political affiliation filtering...bad, then good.
        q['political_affiliations__political_party'] = 'XXX'
        assertCount(self, path, q, 0)
        q['political_affiliations__political_party'] = 'd'
        assertCount(self, path, q, 2)

        # Sources
        about_now = '2015-12-17T00:00:00Z'
        q['sources__date_modified__gt'] = about_now
        assertCount(self, path, q, 0)
        q.pop('sources__date_modified__gt')  # Next key doesn't overwrite.
        q['sources__date_modified__lt'] = about_now
        assertCount(self, path, q, 2)

        # ABA Ratings
        q['aba_ratings__rating'] = 'q'
        assertCount(self, path, q, 0)
        q['aba_ratings__rating'] = 'nq'
        assertCount(self, path, q, 2)

    def test_education_filtering(self):
        """Can we filter education objects?"""
        path = reverse('education-list', kwargs={'version': 'v3'})
        q = dict()

        # Filter by degree
        q['degree_level'] = 'XXX'
        assertCount(self, path, q, 0)
        q['degree_level'] = 'jd'
        assertCount(self, path, q, 1)

        # Filter by degree's related field, School
        q['school__name__istartswith'] = 'XXX'
        assertCount(self, path, q, 0)
        q['school__name__istartswith'] = 'New York'
        assertCount(self, path, q, 1)

    def test_title_filtering(self):
        """Can Judge Titles be filtered?"""
        path = reverse('position-list', kwargs={'version': 'v3'})
        q = dict()

        # Filter by title_name
        q['position_type'] = 'XXX'
        assertCount(self, path, q, 0)
        q['position_type'] = 'c-jud'
        assertCount(self, path, q, 1)

    def test_reverse_filtering(self):
        """Can we filter Source objects by judge name?"""
        # I want any source notes about judge judy.
        path = reverse('source-list', kwargs={'version': 'v3'})
        q = {'person': 2}
        assertCount(self, path, q, 1)

    def test_position_filters(self):
        """Can we filter on positions"""
        path = reverse('position-list', kwargs={'version': 'v3'})
        q = dict()

        # I want positions to do with judge #2 (Judy)
        q['person'] = 2
        assertCount(self, path, q, 2)

        # Retention events
        q['retention_events__retention_type'] = 'reapp_gov'
        assertCount(self, path, q, 1)

        # Appointer was Bill, a Democrat
        q['appointer__name_first__istartswith'] = 'bill'
        q['appointer__political_affiliations__political_party'] = 'd'
        assertCount(self, path, q, 1)
        # She was not appointed by a Republican
        q['appointer__political_affiliations__political_party'] = 'r'
        assertCount(self, path, q, 0)

    def test_racial_filters(self):
        """Can we filter by race?"""
        path = reverse('person-list', kwargs={'version': 'v3'})
        q = {'race': 'w'}
        assertCount(self, path, q, 2)

        # Do an OR. This returns judges that are either black or white (not
        # that it matters, MJ)
        q['race'] = ['w', 'b']
        assertCount(self, path, q, 3)

    def test_circular_relationships(self):
        """Do filters configured using strings instead of classes work?"""
        path = reverse('education-list', kwargs={'version': 'v3'})
        q = dict()

        # Traverse person, position
        q['person__positions__job_title__icontains'] = 'xxx'
        assertCount(self, path, q, 0)
        q['person__positions__job_title__icontains'] = 'lawyer'
        assertCount(self, path, q, 2)

        # Just traverse to the judge table
        q['person__name_first'] = "Judy"  # Nope.
        assertCount(self, path, q, 0)
        q['person__name_first'] = "Judith"  # Yep.
        assertCount(self, path, q, 2)

    def test_exclusion_filters(self):
        """Can we exclude using !'s?"""
        path = reverse('position-list', kwargs={'version': 'v3'})
        q = dict()

        # I want positions to do with any judge other than judge #1
        # Note the exclamation mark. In a URL this would look like
        # "?judge!=1". Fun stuff.
        q['person!'] = 2
        assertCount(self, path, q, 1)   # Bill


class DRFSearchAndAudioAppsApiFilterTest(TestCase):
    fixtures = ['judge_judy.json', 'test_objects_search.json',
                'test_objects_audio.json', 'court_data.json',
                'user_with_judge_access.json']

    def test_cluster_filters(self):
        """Do a variety of cluster filters work?"""
        path = reverse('opinioncluster-list', kwargs={'version': 'v3'})
        q = dict()

        # Related filters
        q['panel__id'] = 2
        assertCount(self, path, q, 1)
        q['non_participating_judges!'] = 1  # Exclusion filter.
        assertCount(self, path, q, 1)
        q['sub_opinions__author'] = 2
        assertCount(self, path, q, 4)

        # Boolean filter
        q['per_curiam'] = False
        assertCount(self, path, q, 4)

        # Integer lookups
        q = dict()
        q['scdb_votes_majority__gt'] = 10
        assertCount(self, path, q, 0)
        q['scdb_votes_majority__gt'] = 1
        assertCount(self, path, q, 1)

    def test_opinion_filter(self):
        """Do a variety of opinion filters work?"""
        path = reverse('opinion-list', kwargs={'version': 'v3'})
        q = dict()

        # Simple filters
        q['sha1'] = 'asdfasdfasdfasdfasdfasddf-nope'
        assertCount(self, path, q, 0)
        q['sha1'] = 'asdfasdfasdfasdfasdfasddf'
        assertCount(self, path, q, 6)

        # Related filters
        q['cluster__panel'] = 1
        assertCount(self, path, q, 0)
        q['cluster__panel'] = 2
        assertCount(self, path, q, 4)

        q = dict()
        q['author__name_first__istartswith'] = "Nope"
        assertCount(self, path, q, 0)
        q['author__name_first__istartswith'] = "jud"
        assertCount(self, path, q, 6)

        q = dict()
        q['joined_by__name_first__istartswith'] = "Nope"
        assertCount(self, path, q, 0)
        q['joined_by__name_first__istartswith'] = "jud"
        assertCount(self, path, q, 1)

        q = dict()
        types = ['010combined']
        q['type'] = types
        assertCount(self, path, q, 5)
        types.append('020lead')
        assertCount(self, path, q, 6)

    def test_docket_filters(self):
        """Do a variety of docket filters work?"""
        path = reverse('docket-list', kwargs={'version': 'v3'})
        q = dict()

        # Simple filter
        q['docket_number'] = '14-1165-nope'
        assertCount(self, path, q, 0)
        q['docket_number'] = 'docket number 1'
        assertCount(self, path, q, 1)

        # Related filters
        q['court'] = 'test-nope'
        assertCount(self, path, q, 0)
        q['court'] = 'test'
        assertCount(self, path, q, 1)

        q['clusters__panel__name_first__istartswith'] = 'jud-nope'
        assertCount(self, path, q, 0)
        q['clusters__panel__name_first__istartswith'] = 'jud'
        assertCount(self, path, q, 1)

        q['audio_files__sha1'] = 'de8cff186eb263dc06bdc5340860eb6809f898d3-nope'
        assertCount(self, path, q, 0)
        q['audio_files__sha1'] = 'de8cff186eb263dc06bdc5340860eb6809f898d3'
        assertCount(self, path, q, 1)

    def test_audio_filters(self):
        path = reverse('audio-list', kwargs={'version': 'v3'})
        q = dict()

        # Simple filter
        q['sha1'] = 'de8cff186eb263dc06bdc5340860eb6809f898d3-nope'
        assertCount(self, path, q, 0)
        q['sha1'] = 'de8cff186eb263dc06bdc5340860eb6809f898d3'
        assertCount(self, path, q, 1)

        # Related filter
        q['docket__court'] = 'test-nope'
        assertCount(self, path, q, 0)
        q['docket__court'] = 'test'
        assertCount(self, path, q, 1)

        # Multiple choice filter
        q = dict()
        sources = ['C']
        q['source'] = sources
        assertCount(self, path, q, 2)
        sources.append('CR')
        assertCount(self, path, q, 3)

    def test_opinion_cited_filters(self):
        """Do the filters on the opinions_cited work?"""
        path = reverse('opinionscited-list', kwargs={'version': 'v3'})
        q = dict()

        # Simple related filter
        q['citing_opinion__sha1'] = 'asdf-nope'
        assertCount(self, path, q, 0)
        q['citing_opinion__sha1'] = 'asdfasdfasdfasdfasdfasddf'
        assertCount(self, path, q, 4)

        # Fancy filter: Citing Opinions written by judges with first name
        # istartingwith "jud"
        q['citing_opinion__author__name_first__istartswith'] = 'jud-nope'
        assertCount(self, path, q, 0)
        q['citing_opinion__author__name_first__istartswith'] = 'jud'
        assertCount(self, path, q, 4)


class DRFFieldSelectionTest(TestCase):
    fixtures = ['judge_judy.json', 'test_objects_search.json',
                'user_with_judge_access.json', 'court_data.json']

    def test_only_some_fields_returned(self):
        """Can we return only some of the fields?"""

        # First check the Judge endpoint, one of our more complicated ones.
        path = reverse('person-list', kwargs={'version': 'v3'})
        fields_to_return = ['educations', 'date_modified', 'slug']
        q = {'fields': ','.join(fields_to_return)}
        self.client.login(username='pandora', password='password')
        r = self.client.get(path, q)
        self.assertEqual(len(r.data['results'][0].keys()),
                         len(fields_to_return))

        # One more check for good measure.
        path = reverse('opinioncluster-list', kwargs={'version': 'v3'})
        fields_to_return = ['per_curiam', 'slug']
        r = self.client.get(path, q)
        self.assertEqual(len(r.data['results'][0].keys()),
                         len(fields_to_return))


class BulkJsonHistoryTest(TestCase):

    def setUp(self):
        self.history = BulkJsonHistory('test')

    def tearDown(self):
        self.history.delete_from_disk()

    def test_load_the_file(self):
        data = self.history.load_json_file()
        self.assertEqual(
            {},
            data,
        )

    def test_load_date_when_none(self):
        d = self.history.get_last_good_date()
        self.assertIsNone(d)

    def test_set_date_then_load_it(self):
        self.history.add_current_attempt_and_save()
        self.history.mark_success_and_save()
        d = self.history.get_last_good_date()
        self.assertAlmostEqual(
            # The date serialized is within ten seconds of now.
            d,
            now(),
            delta=timedelta(seconds=10)
        )

    def test_add_current_attempt(self):
        self.history.add_current_attempt_and_save()
        d = self.history.get_last_attempt()
        self.assertAlmostEqual(
            d,
            now(),
            delta=timedelta(seconds=10)
        )
