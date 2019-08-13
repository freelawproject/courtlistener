# coding=utf-8
from __future__ import print_function

import json
import shutil
from datetime import timedelta, date

import redis
from django.conf import settings
from django.contrib.auth.models import User, Permission
from django.core import mail
from django.core.management import call_command
from django.urls import reverse, ResolverMatch
from django.http import HttpRequest, JsonResponse
from django.test import Client, override_settings, RequestFactory, TestCase, \
    TransactionTestCase
from django.utils.timezone import now
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN

from cl.api.utils import BulkJsonHistory, SEND_API_WELCOME_EMAIL_COUNT
from cl.api.views import coverage_data
from cl.audio.api_views import AudioViewSet
from cl.audio.models import Audio
from cl.lib.test_helpers import IndexedSolrTestCase
from cl.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgumentCommand
from cl.scrapers.test_assets import test_oral_arg_scraper
from cl.search.models import Docket, Court, Opinion, OpinionCluster, \
    OpinionsCited
from cl.stats.models import Event


class BasicAPIPageTest(TestCase):
    """Test the basic views"""
    fixtures = ['judge_judy.json', 'test_objects_search.json']

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
        # Need pagerank file for test_pagerank_file()
        from cl.search.management.commands.cl_calculate_pagerank import Command
        command = Command()
        command.do_pagerank(chown=False)
        r = self.client.get(reverse('pagerank_file'))
        self.assertEqual(r.status_code, 200)

    def test_coverage_api(self):
        r = self.client.get(reverse('coverage_data',
                                    kwargs={'version': 2, 'court': 'ca1'}))
        self.assertEqual(r.status_code, 200)

    def test_coverage_api_via_url(self):
        # Should hit something like:
        #  https://www.courtlistener.com/api/rest/v2/coverage/ca1/
        r = self.client.get('/api/rest/v2/coverage/ca1/')
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


class CoverageTests(IndexedSolrTestCase):

    def test_coverage_data_view_provides_court_data(self):
        response = coverage_data(HttpRequest(), 'v2', 'ca1')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, JsonResponse)
        self.assertContains(response, 'annual_counts')
        self.assertContains(response, 'total')

    def test_coverage_data_all_courts(self):
        r = self.client.get(reverse('coverage_data', kwargs={
            'version': '3',
            'court': 'all',
        }))
        j = json.loads(r.content)
        self.assertTrue(len(j['annual_counts'].keys()) > 0)
        self.assertIn('total', j)

    def test_coverage_data_specific_court(self):
        r = self.client.get(reverse('coverage_data', kwargs={
            'version': '3',
            'court': 'ca1',
        }))
        j = json.loads(r.content)
        self.assertTrue(len(j['annual_counts'].keys()) > 0)
        self.assertIn('total', j)


class ApiQueryCountTests(TransactionTestCase):
    """Check that the number of queries for an API doesn't explode

    I expect these tests to regularly need updating as new features are added
    to the APIs, but in the meantime, they're important checks because of how
    easy it is to explode the APIs. The issue that happens here is that if
    you're not careful, adding a related field to a model will add at least 20
    queries to each API request, one per returned item. This *kills*
    performance.
    """
    fixtures = ['test_objects_query_counts.json', 'attorney_party.json',
                'user_with_recap_api_access.json', 'test_objects_audio.json',
                'recap_processing_queue_query_counts.json']

    def setUp(self):
        # Add the permissions to the user.
        u = User.objects.get(pk=6)
        ps = Permission.objects.filter(codename='has_recap_api_access')
        u.user_permissions.add(*ps)

        self.assertTrue(self.client.login(
            username='recap-user', password='password'))

    def test_audio_api_query_counts(self):
        with self.assertNumQueries(4):
            path = reverse('audio-list', kwargs={'version': 'v3'})
            self.client.get(path)

    def test_search_api_query_counts(self):
        with self.assertNumQueries(7):
            path = reverse('docket-list', kwargs={'version': 'v3'})
            self.client.get(path)

        with self.assertNumQueries(8):
            path = reverse('docketentry-list', kwargs={'version': 'v3'})
            self.client.get(path)

        with self.assertNumQueries(6):
            path = reverse('recapdocument-list', kwargs={'version': 'v3'})
            self.client.get(path)

        with self.assertNumQueries(7):
            path = reverse('opinioncluster-list', kwargs={'version': 'v3'})
            self.client.get(path)

        with self.assertNumQueries(5):
            path = reverse('opinion-list', kwargs={'version': 'v3'})
            self.client.get(path)

    def test_party_api_query_counts(self):
        with self.assertNumQueries(7):
            path = reverse('party-list', kwargs={'version': 'v3'})
            self.client.get(path)

        with self.assertNumQueries(6):
            path = reverse('attorney-list', kwargs={'version': 'v3'})
            self.client.get(path)

    def test_recap_upload_api_query_counts(self):
        with self.assertNumQueries(3):
            path = reverse('processingqueue-list', kwargs={'version': 'v3'})
            self.client.get(path)

        with self.assertNumQueries(5):
            path = reverse('fast-recapdocument-list', kwargs={'version': 'v3'})
            self.client.get(path)


class ApiEventCreationTestCase(TestCase):
    """Check that events are created properly."""

    fixtures = ['user_with_recap_api_access.json']

    @staticmethod
    def flush_stats():
        # Flush existing stats (else previous tests cause issues)
        r = redis.StrictRedis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DATABASES['STATS'],
        )
        r.flushdb()

    def setUp(self):
        # Add the permissions to the user.
        self.user = User.objects.get(pk=6)
        ps = Permission.objects.filter(codename='has_recap_api_access')
        self.user.user_permissions.add(*ps)
        self.flush_stats()

    def tearDown(self):
        Event.objects.all().delete()
        self.flush_stats()

    def hit_the_api(self):
        path = reverse('audio-list', kwargs={'version': 'v3'})
        request = RequestFactory().get(path)

        # Create the view and change the milestones to be something we can test
        # (Otherwise, we need to make 1,000 requests in this test)
        view = AudioViewSet.as_view({'get': 'list'})
        view.milestones = [1]

        # Set the attributes needed in the absence of middleware
        request.user = self.user
        request.resolver_match = ResolverMatch(
            view,
            {'version': 'v3'},
            'audio-list',
        )

        view(request)

    def test_is_the_welcome_email_sent(self):
        """Do we send welcome emails for new API users?"""
        # Create correct number of API requests
        for _ in range(0, SEND_API_WELCOME_EMAIL_COUNT):
            self.hit_the_api()

        # Did the email get sent?
        expected_email_count = 1
        self.assertEqual(expected_email_count, len(mail.outbox))

    def test_are_events_created_properly(self):
        """Are event objects created as API requests are made?"""
        self.hit_the_api()

        expected_event_count = 1
        self.assertEqual(expected_event_count, Event.objects.count())


class DRFOrderingTests(TestCase):
    """Does ordering work generally and specifically?"""
    fixtures = ['judge_judy.json', 'authtest_data.json',
                'test_objects_search.json']

    def test_position_ordering(self):
        path = reverse('position-list', kwargs={'version': 'v3'})
        r = self.client.get(path, {'order_by': 'date_start'})
        self.assertLess(r.data['results'][0]['date_start'],
                        r.data['results'][-1]['date_start'])
        r = self.client.get(path, {'order_by': '-date_start'})
        self.assertGreater(r.data['results'][0]['date_start'],
                           r.data['results'][-1]['date_start'])

    def test_opinion_ordering_by_id(self):
        path = reverse('opinion-list', kwargs={'version': 'v3'})
        r = self.client.get(path, {'order_by': 'id'})
        self.assertLess(r.data['results'][0]['resource_uri'],
                        r.data['results'][-1]['resource_uri'])
        r = self.client.get(path, {'order_by': '-id'})
        self.assertGreater(r.data['results'][0]['resource_uri'],
                           r.data['results'][-1]['resource_uri'])


class FilteringCountTestCase(object):
    """Mixin for adding an additional test assertion."""

    # noinspection PyPep8Naming
    def assertCountInResults(self, expected_count):
        print("Path and q are: %s, %s" % (self.path, self.q))
        r = self.client.get(self.path, self.q)
        self.assertLess(r.status_code, 400)  # A valid status code?
        got = len(r.data['results'])
        self.assertEqual(
            got,
            expected_count,
            msg="Expected %s, but got %s.\n\n"
                "r.data was: %s" % (expected_count, got, r.data)
        )


class DRFJudgeApiFilterTests(TestCase, FilteringCountTestCase):
    """Do the filters work properly?"""
    fixtures = ['judge_judy.json', 'authtest_data.json']

    def setUp(self):
        self.assertTrue(self.client.login(
            username='pandora', password='password'))
        self.q = dict()

    def test_judge_filtering_by_first_name(self):
        """Can we filter by first name?"""
        self.path = reverse('person-list', kwargs={'version': 'v3'})

        # Filtering with good values brings back 1 result.
        self.q = {'name_first__istartswith': 'judith'}
        self.assertCountInResults(1)

        # Filtering with bad values brings back no results.
        self.q = {'name_first__istartswith': 'XXX'}
        self.assertCountInResults( 0)

    def test_judge_filtering_by_date(self):
        """Do the various date filters work properly?"""
        self.path = reverse('person-list', kwargs={'version': 'v3'})

        # Exact match for her birthday
        correct_date = date(1942, 10, 21)
        self.q = {'date_dob': correct_date.isoformat()}
        self.assertCountInResults(1)

        # People born after the day before her birthday
        before = correct_date - timedelta(days=1)
        self.q = {'date_dob__gt': before.isoformat()}
        self.assertCountInResults(1)

        # Flip the logic. This should return no results.
        self.q = {'date_dob__lt': before.isoformat()}
        self.assertCountInResults(0)

    def test_nested_judge_filtering(self):
        """Can we filter across various relations?

        Each of these assertions adds another parameter making our final test
        a pretty complex combination.
        """
        self.path = reverse('person-list', kwargs={'version': 'v3'})

        # No results for a bad query
        self.q['educations__degree_level'] = 'XXX'
        self.assertCountInResults(0)

        # One result for a good query
        self.q['educations__degree_level'] = 'jd'
        self.assertCountInResults(1)

        # Again, no results
        self.q['educations__degree_year'] = 1400
        self.assertCountInResults(0)

        # But with the correct year...one result
        self.q['educations__degree_year'] = 1965
        self.assertCountInResults(1)

        # Judy went to "New York Law School"
        self.q['educations__school__name__istartswith'] = "New York Law"
        self.assertCountInResults(1)

        # Moving on to careers. Bad value, then good.
        self.q['positions__job_title__icontains'] = 'XXX'
        self.assertCountInResults(0)
        self.q['positions__job_title__icontains'] = 'lawyer'
        self.assertCountInResults(1)

        # Moving on to titles...bad value, then good.
        self.q['positions__position_type'] = 'XXX'
        self.assertCountInResults(0)
        self.q['positions__position_type'] = 'c-jud'
        self.assertCountInResults(1)

        # Political affiliation filtering...bad, then good.
        self.q['political_affiliations__political_party'] = 'XXX'
        self.assertCountInResults(0)
        self.q['political_affiliations__political_party'] = 'd'
        self.assertCountInResults(2)

        # Sources
        about_now = '2015-12-17T00:00:00Z'
        self.q['sources__date_modified__gt'] = about_now
        self.assertCountInResults(0)
        self.q.pop('sources__date_modified__gt')  # Next key doesn't overwrite.
        self.q['sources__date_modified__lt'] = about_now
        self.assertCountInResults(2)

        # ABA Ratings
        self.q['aba_ratings__rating'] = 'q'
        self.assertCountInResults(0)
        self.q['aba_ratings__rating'] = 'nq'
        self.assertCountInResults(2)

    def test_education_filtering(self):
        """Can we filter education objects?"""
        self.path = reverse('education-list', kwargs={'version': 'v3'})

        # Filter by degree
        self.q['degree_level'] = 'XXX'
        self.assertCountInResults(0)
        self.q['degree_level'] = 'jd'
        self.assertCountInResults(1)

        # Filter by degree's related field, School
        self.q['school__name__istartswith'] = 'XXX'
        self.assertCountInResults(0)
        self.q['school__name__istartswith'] = 'New York'
        self.assertCountInResults(1)

    def test_title_filtering(self):
        """Can Judge Titles be filtered?"""
        self.path = reverse('position-list', kwargs={'version': 'v3'})

        # Filter by title_name
        self.q['position_type'] = 'XXX'
        self.assertCountInResults(0)
        self.q['position_type'] = 'c-jud'
        self.assertCountInResults(1)

    def test_reverse_filtering(self):
        """Can we filter Source objects by judge name?"""
        # I want any source notes about judge judy.
        self.path = reverse('source-list', kwargs={'version': 'v3'})
        self.q = {'person': 2}
        self.assertCountInResults(1)

    def test_position_filters(self):
        """Can we filter on positions"""
        self.path = reverse('position-list', kwargs={'version': 'v3'})

        # I want positions to do with judge #2 (Judy)
        self.q['person'] = 2
        self.assertCountInResults(2)

        # Retention events
        self.q['retention_events__retention_type'] = 'reapp_gov'
        self.assertCountInResults(1)

        # Appointer was Bill, id of 1
        self.q['appointer'] = 1
        self.assertCountInResults(1)
        self.q['appointer'] = 3
        self.assertCountInResults(0)

    def test_racial_filters(self):
        """Can we filter by race?"""
        self.path = reverse('person-list', kwargs={'version': 'v3'})
        self.q = {'race': 'w'}
        self.assertCountInResults(2)

        # Do an OR. This returns judges that are either black or white (not
        # that it matters, MJ)
        self.q['race'] = ['w', 'b']
        self.assertCountInResults(3)

    def test_circular_relationships(self):
        """Do filters configured using strings instead of classes work?"""
        self.path = reverse('education-list', kwargs={'version': 'v3'})

        # Traverse person, position
        self.q['person__positions__job_title__icontains'] = 'xxx'
        self.assertCountInResults(0)
        self.q['person__positions__job_title__icontains'] = 'lawyer'
        self.assertCountInResults(2)

        # Just traverse to the judge table
        self.q['person__name_first'] = "Judy"  # Nope.
        self.assertCountInResults(0)
        self.q['person__name_first'] = "Judith"  # Yep.
        self.assertCountInResults(2)

    def test_exclusion_filters(self):
        """Can we exclude using !'s?"""
        self.path = reverse('position-list', kwargs={'version': 'v3'})

        # I want positions to do with any judge other than judge #1
        # Note the exclamation mark. In a URL this would look like
        # "?judge!=1". Fun stuff.
        self.q['person!'] = 2
        self.assertCountInResults(1)   # Bill


class DRFRecapApiFilterTests(TestCase, FilteringCountTestCase):
    fixtures = ['recap_docs.json', 'attorney_party.json',
                'user_with_recap_api_access.json']

    def setUp(self):
        # Add the permissions to the user.
        u = User.objects.get(pk=6)
        ps = Permission.objects.filter(codename='has_recap_api_access')
        u.user_permissions.add(*ps)

        self.assertTrue(self.client.login(
            username='recap-user', password='password'))
        self.q = dict()

    def test_docket_entry_to_docket_filters(self):
        """Do a variety of docket entry filters work?"""
        self.path = reverse('docketentry-list', kwargs={'version': 'v3'})

        # Docket filters...
        self.q['docket__id'] = 1
        self.assertCountInResults(1)
        self.q['docket__id'] = 10000000000
        self.assertCountInResults(0)
        self.q = {'docket__id!': 100000000}
        self.assertCountInResults(1)

    def test_docket_tag_filters(self):
        """Can we filter dockets by tags?"""
        self.path = reverse('docket-list', kwargs={'version': 'v3'})

        self.q = {'docket_entries__recap_documents__tags': 1}
        self.assertCountInResults(1)
        self.q = {'docket_entries__recap_documents__tags': 2}
        self.assertCountInResults(0)

    def test_docket_entry_docket_court_filters(self):
        self.path = reverse('docketentry-list', kwargs={'version': 'v3'})

        # Across docket to court...
        self.q['docket__court__id'] = 'ca1'
        self.assertCountInResults(1)
        self.q['docket__court__id'] = 'foo'
        self.assertCountInResults(0)

    def test_nested_recap_document_filters(self):
        self.path = reverse('docketentry-list', kwargs={'version': 'v3'})

        self.q['id'] = 1
        self.assertCountInResults(1)
        self.q = {'recap_documents__id': 1}
        self.assertCountInResults(1)
        self.q = {'recap_documents__id': 2}
        self.assertCountInResults(0)

        self.q = {'recap_documents__tags': 1}
        self.assertCountInResults(1)
        self.q = {'recap_documents__tags': 2}
        self.assertCountInResults(0)

        # Something wacky...
        self.q = {'recap_documents__docket_entry__docket__id': 1}
        self.assertCountInResults(1)
        self.q = {'recap_documents__docket_entry__docket__id': 2}
        self.assertCountInResults(0)

    def test_recap_document_filters(self):
        self.path = reverse('recapdocument-list', kwargs={'version': 'v3'})

        self.q['id'] = 1
        self.assertCountInResults(1)
        self.q['id'] = 2
        self.assertCountInResults(0)

        self.q = {'pacer_doc_id': 17711118263}
        self.assertCountInResults(1)
        self.q = {'pacer_doc_id': '17711118263-nope'}
        self.assertCountInResults(0)

        self.q = {'docket_entry__id': 1}
        self.assertCountInResults(1)
        self.q = {'docket_entry__id': 2}
        self.assertCountInResults(0)

        self.q = {'tags': 1}
        self.assertCountInResults(1)
        self.q = {'tags': 2}
        self.assertCountInResults(0)
        self.q = {'tags__name': 'test'}
        self.assertCountInResults(1)
        self.q = {'tags__name': 'test2'}
        self.assertCountInResults(0)

    def test_attorney_filters(self):
        self.path = reverse('attorney-list', kwargs={'version': 'v3'})

        self.q['id'] = 1
        self.assertCountInResults(1)
        self.q['id'] = 2
        self.assertCountInResults(0)

        self.q = {'docket__id': 1}
        self.assertCountInResults(1)
        self.q = {'docket__id': 2}
        self.assertCountInResults(0)

        self.q = {'parties_represented__id': 1}
        self.assertCountInResults(1)
        self.q = {'parties_represented__id': 2}
        self.assertCountInResults(0)
        self.q = {'parties_represented__name__contains': 'Honker'}
        self.assertCountInResults(1)
        self.q = {'parties_represented__name__contains': 'Honker-Nope'}
        self.assertCountInResults(0)

    def test_party_filters(self):
        self.path = reverse('party-list', kwargs={'version': 'v3'})

        self.q['id'] = 1
        self.assertCountInResults(1)
        self.q['id'] = 2
        self.assertCountInResults(0)

        # This represents dockets that the party was a part of.
        self.q = {'docket__id': 1}
        self.assertCountInResults(1)
        self.q = {'docket__id': 2}
        self.assertCountInResults(0)

        # Contrasted with this, which joins based on their attorney.
        self.q = {'attorney__docket__id': 1}
        self.assertCountInResults(1)
        self.q = {'attorney__docket__id': 2}
        self.assertCountInResults(0)

        self.q = {'name': "Honker"}
        self.assertCountInResults(1)
        self.q = {'name': "Cardinal Bonds"}
        self.assertCountInResults(0)

        self.q = {'attorney__name__icontains': 'Juneau'}
        self.assertCountInResults(1)
        self.q = {'attorney__name__icontains': 'Juno'}
        self.assertCountInResults(0)


class DRFSearchAppAndAudioAppApiFilterTest(TestCase, FilteringCountTestCase):
    fixtures = ['judge_judy.json', 'test_objects_search.json',
                'test_objects_audio.json', 'authtest_data.json',
                'user_with_recap_api_access.json']

    def setUp(self):
        self.assertTrue(self.client.login(
            username='recap-user', password='password'))
        self.q = dict()

    def test_cluster_filters(self):
        """Do a variety of cluster filters work?"""
        self.path = reverse('opinioncluster-list', kwargs={'version': 'v3'})

        # Related filters
        self.q['panel__id'] = 2
        self.assertCountInResults(1)
        self.q['non_participating_judges!'] = 1  # Exclusion filter.
        self.assertCountInResults(1)
        self.q['sub_opinions__author'] = 2
        self.assertCountInResults(4)

        # Citation filters
        self.q = {'citations__volume': 56,
                  'citations__reporter': 'F.2d',
                  'citations__page': '9'}
        self.assertCountInResults(1)

        # Integer lookups
        self.q = dict()
        self.q['scdb_votes_majority__gt'] = 10
        self.assertCountInResults(0)
        self.q['scdb_votes_majority__gt'] = 1
        self.assertCountInResults(1)

    def test_opinion_filter(self):
        """Do a variety of opinion filters work?"""
        self.path = reverse('opinion-list', kwargs={'version': 'v3'})

        # Simple filters
        self.q['sha1'] = 'asdfasdfasdfasdfasdfasddf-nope'
        self.assertCountInResults(0)
        self.q['sha1'] = 'asdfasdfasdfasdfasdfasddf'
        self.assertCountInResults(6)

        # Boolean filter
        self.q['per_curiam'] = False
        self.assertCountInResults(6)

        # Related filters
        self.q['cluster__panel'] = 1
        self.assertCountInResults(0)
        self.q['cluster__panel'] = 2
        self.assertCountInResults(4)

        self.q = dict()
        self.q['author__name_first__istartswith'] = "Nope"
        self.assertCountInResults(0)
        self.q['author__name_first__istartswith'] = "jud"
        self.assertCountInResults(6)

        self.q = dict()
        self.q['joined_by__name_first__istartswith'] = "Nope"
        self.assertCountInResults(0)
        self.q['joined_by__name_first__istartswith'] = "jud"
        self.assertCountInResults(1)

        self.q = dict()
        types = ['010combined']
        self.q['type'] = types
        self.assertCountInResults(5)
        types.append('020lead')
        self.assertCountInResults(6)

    def test_docket_filters(self):
        """Do a variety of docket filters work?"""
        self.path = reverse('docket-list', kwargs={'version': 'v3'})

        # Simple filter
        self.q['docket_number'] = '14-1165-nope'
        self.assertCountInResults(0)
        self.q['docket_number'] = 'docket number 1 005'
        self.assertCountInResults(1)

        # Related filters
        self.q['court'] = 'test-nope'
        self.assertCountInResults(0)
        self.q['court'] = 'test'
        self.assertCountInResults(1)

        self.q['clusters__panel__name_first__istartswith'] = 'jud-nope'
        self.assertCountInResults(0)
        self.q['clusters__panel__name_first__istartswith'] = 'jud'
        self.assertCountInResults(1)

        self.q['audio_files__sha1'] = 'de8cff186eb263dc06bdc5340860eb6809f898d3-nope'
        self.assertCountInResults(0)
        self.q['audio_files__sha1'] = 'de8cff186eb263dc06bdc5340860eb6809f898d3'
        self.assertCountInResults(1)

    def test_audio_filters(self):
        self.path = reverse('audio-list', kwargs={'version': 'v3'})

        # Simple filter
        self.q['sha1'] = 'de8cff186eb263dc06bdc5340860eb6809f898d3-nope'
        self.assertCountInResults(0)
        self.q['sha1'] = 'de8cff186eb263dc06bdc5340860eb6809f898d3'
        self.assertCountInResults(1)

        # Related filter
        self.q['docket__court'] = 'test-nope'
        self.assertCountInResults(0)
        self.q['docket__court'] = 'test'
        self.assertCountInResults(1)

        # Multiple choice filter
        self.q = dict()
        sources = ['C']
        self.q['source'] = sources
        self.assertCountInResults(2)
        sources.append('CR')
        self.assertCountInResults(3)

    def test_opinion_cited_filters(self):
        """Do the filters on the opinions_cited work?"""
        self.path = reverse('opinionscited-list', kwargs={'version': 'v3'})

        # Simple related filter
        self.q['citing_opinion__sha1'] = 'asdf-nope'
        self.assertCountInResults(0)
        self.q['citing_opinion__sha1'] = 'asdfasdfasdfasdfasdfasddf'
        self.assertCountInResults(4)

        # Fancy filter: Citing Opinions written by judges with first name
        # istartingwith "jud"
        self.q['citing_opinion__author__name_first__istartswith'] = 'jud-nope'
        self.assertCountInResults(0)
        self.q['citing_opinion__author__name_first__istartswith'] = 'jud'
        self.assertCountInResults(4)


class DRFFieldSelectionTest(TestCase):
    """Test selecting only certain fields"""
    fixtures = ['judge_judy.json', 'test_objects_search.json',
                'authtest_data.json']

    def test_only_some_fields_returned(self):
        """Can we return only some of the fields?"""

        # First check the Judge endpoint, one of our more complicated ones.
        path = reverse('person-list', kwargs={'version': 'v3'})
        fields_to_return = ['educations', 'date_modified', 'slug']
        q = {'fields': ','.join(fields_to_return)}
        self.assertTrue(self.client.login(
            username='pandora', password='password'))
        r = self.client.get(path, q)
        self.assertEqual(len(r.data['results'][0].keys()),
                         len(fields_to_return))

        # One more check for good measure.
        path = reverse('opinioncluster-list', kwargs={'version': 'v3'})
        fields_to_return = ['per_curiam', 'slug']
        r = self.client.get(path, q)
        self.assertEqual(len(r.data['results'][0].keys()),
                         len(fields_to_return))


class DRFRecapPermissionTest(TestCase):
    fixtures = ['user_with_recap_api_access.json', 'authtest_data.json']

    def setUp(self):
        # Add the permissions to the user.
        u = User.objects.get(pk=6)
        ps = Permission.objects.filter(codename='has_recap_api_access')
        u.user_permissions.add(*ps)

        self.paths = [reverse(path, kwargs={'version': 'v3'}) for path in [
            'recapdocument-list',
            'docketentry-list',
            'attorney-list',
            'party-list',
        ]]

    def test_has_access(self):
        """Does the RECAP user have access to all of the RECAP endpoints?"""
        self.assertTrue(self.client.login(
            username='recap-user', password='password'))
        for path in self.paths:
            print("Access allowed to recap user at: %s... " % path, end='')
            r = self.client.get(path)
            self.assertEqual(r.status_code, HTTP_200_OK)
            print("✓")

    def test_lacks_access(self):
        """Does a normal user lack access to the RECPAP endpoints?"""
        self.assertTrue(self.client.login(
            username='pandora', password='password'))
        for path in self.paths:
            print("Access denied to non-recap user at: %s... " % path, end='')
            r = self.client.get(path)
            self.assertEqual(r.status_code, HTTP_403_FORBIDDEN)
            print("✓")


class BulkJsonHistoryTest(TestCase):

    def setUp(self):
        self.history = BulkJsonHistory('test', settings.BULK_DATA_DIR)

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


class BulkDataTest(TestCase):
    tmp_data_dir = '/tmp/bulk-dir/'

    def setUp(self):
        docket = Docket(
            case_name=u'foo',
            court=Court.objects.get(pk='test'),
            source=Docket.DEFAULT
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
        opinion = Opinion(cluster=self.doc_cluster, type='Lead Opinion')
        opinion.save(index=False)

        opinion2 = Opinion(cluster=self.doc_cluster, type='Concurrence')
        opinion2.save(index=False)

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
        call_command('cl_make_bulk_data')

    def test_database_has_objects_for_bulk_export(self):
        self.assertTrue(Opinion.objects.count() > 0, 'Opinions exist')
        self.assertTrue(Audio.objects.count() > 0, 'Audio exist')
        self.assertTrue(Docket.objects.count() > 0, 'Docket exist')
        self.assertTrue(Court.objects.count() > 0, 'Court exist')
        self.assertEqual(
            Court.objects.get(pk='test').full_name,
            'Testing Supreme Court'
        )
