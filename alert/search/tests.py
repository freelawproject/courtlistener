import StringIO
import os
import shutil
import simplejson
import time

from collections import OrderedDict
from datadiff import diff
import datetime
from django.core.files.base import ContentFile
from django.test import TestCase
from django.test.client import Client
from django.test.utils import override_settings
from lxml import html

from alert.lib.solr_core_admin import (get_data_dir_location)
from alert.lib.test_helpers import CitationTest, SolrTestCase
from alert.search.models import Citation, Court, Document, Docket
from alert import settings
from alert.search.management.commands.cl_calculate_pagerank_networkx import \
    Command


class SetupException(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class ModelTest(TestCase):
    fixtures = ['test_court.json']

    def test_save_old_opinion(self):
        """Can we save opinions older than 1900?"""
        court = Court.objects.get(pk='test')

        cite = Citation(case_name=u"Blah")
        cite.save(index=True)
        docket = Docket(
            case_name=u"Blah",
            court=court,
        )
        docket.save()
        d = Document(
            citation=cite,
            docket=docket,
            date_filed=datetime.date(1899, 1, 1),

        )

        try:
            cf = ContentFile(StringIO.StringIO('blah').read())
            d.local_path.save('file_name.pdf', cf, save=False)
            d.save(index=True)
        except ValueError:
            raise ValueError("Unable to save a case older than 1900. Did you "
                             "try to use `strftime`...again?")


class DocketUpdateSignalTest(TestCase):
    fixtures = ['test_court.json']

    def test_updating_the_docket_when_the_citation_case_name_changes(self):
        """Makes sure that the docket changes when the citation does."""
        court = Court.objects.get(pk='test')

        original_case_name = u'original case name'
        new_case_name = u'new case name'
        cite = Citation(case_name=original_case_name)
        cite.save(index=False)
        docket = Docket(
            case_name=original_case_name,
            court=court,
        )
        docket.save()
        Document(
            citation=cite,
            docket=docket,
        ).save(index=False)
        cite.case_name = new_case_name
        cite.save(index=False)
        changed_docket = Docket.objects.get(pk=docket.pk)
        self.assertEqual(changed_docket.case_name, new_case_name)


class SearchTest(SolrTestCase):
    def test_a_simple_text_query(self):
        """Does typing into the main query box work?"""
        r = self.client.get('/', {'q': 'supreme'})
        self.assertIn('Tarrant', r.content)

    def test_a_case_name_query(self):
        """Does querying by case name work?"""
        r = self.client.get('/', {'q': '*:*', 'caseName': 'tarrant'})
        self.assertIn('Tarrant', r.content)

    def test_a_query_with_white_space_only(self):
        """Does everything work when whitespace is in various fields?"""
        r = self.client.get('/', {'q': ' ',
                                  'judge': ' ',
                                  'case_name': ' '})
        self.assertIn('Tarrant', r.content)
        self.assertNotIn('deadly', r.content)

    def test_a_query_with_a_date(self):
        """Does querying by date work?"""
        response = self.client.get('/', {'q': '*:*',
                                         'filed_after': '2013-06',
                                         'filed_before': '2013-07'})
        self.assertIn('Tarrant', response.content)

    def test_faceted_queries(self):
        """Does querying in a given court return the document? Does querying
        the wrong facets exclude it?
        """
        r = self.client.get('/', {'q': '*:*', 'court_test': 'on'})
        self.assertIn('Tarrant', r.content)
        r = self.client.get('/', {'q': '*:*', 'stat_Errata': 'on'})
        self.assertNotIn('Tarrant', r.content)

    def test_a_docket_number_query(self):
        """Can we query by docket number?"""
        r = self.client.get('/', {'q': '*:*', 'docket_number': '11-889'})
        self.assertIn(
            'Tarrant',
            r.content,
            "Result not found by docket number!"
        )

    def test_a_west_citation_query(self):
        """Can we query by citation number?"""
        get_dicts = [{'q': '*:*', 'citation': '44'},
                     {'q': 'citation:44'},
                     # Tests query field lower-casing, and a deprecated field.
                     {'q': 'westcite:44'}]
        for get_dict in get_dicts:
            r = self.client.get('/', get_dict)
            self.assertIn('Tarrant', r.content)

    def test_a_neutral_citation_query(self):
        """Can we query by neutral citation numbers?"""
        r = self.client.get('/', {'q': '*:*', 'neutral_cite': '44'})
        self.assertIn('Tarrant', r.content)

    def test_a_query_with_a_old_date(self):
        """Do we have any recurrent issues with old dates and strftime (issue
        220)?"""
        r = self.client.get('/', {'q': '*:*', 'filed_after': '1890'})
        self.assertEqual(200, r.status_code)

    def test_a_judge_query(self):
        """Can we query by judge name?"""
        r = self.client.get('/', {'q': '*:*', 'judge': 'david'})
        self.assertIn('Tarrant', r.content)
        r = self.client.get('/', {'q': 'judge:david'})
        self.assertIn('Tarrant', r.content)

    def test_a_nature_of_suit_query(self):
        """Can we query by nature of suit?"""
        r = self.client.get('/', {'q': 'suitNature:copyright'})
        self.assertIn('Tarrant', r.content)

    def test_citation_filtering(self):
        """Can we find Documents by citation filtering?"""
        msg = "%s case back when filtering by citation count."
        r = self.client.get('/', {'q': '*:*', 'cited_lt': 5, 'cited_gt': 3})
        self.assertIn(
            'Tarrant',
            r.content,
            msg=msg % 'Did not get'
        )
        r = self.client.get('/', {'q': '*:*', 'cited_lt': 10, 'cited_gt': 8})
        self.assertNotIn(
            'Tarrant',
            r.content,
            msg=msg % 'Got'
        )

    def test_citation_ordering(self):
        """Can the results be re-ordered by citation count?"""
        r = self.client.get('/', {'q': '*:*', 'order_by': 'citeCount desc'})
        self.assertTrue(
            r.content.index('Disclosure') < r.content.index('Tarrant'),
            msg="'Disclosure' should come BEFORE 'Tarrant' when ordered by "
                "descending citeCount.")

        r = self.client.get('/', {'q': '*:*', 'order_by': 'citeCount asc'})
        self.assertTrue(
            r.content.index('Disclosure') > r.content.index('Tarrant'),
            msg="'Disclosure' should come AFTER 'Tarrant' when "
                "ordered by ascending citeCount.")

    def test_oa_results_basic(self):
        r = self.client.get('/', {'type': 'oa'})
        self.assertIn('Jeremy', r.content)

    def test_oa_results_date_argued_ordering(self):
        r = self.client.get('/', {'type': 'oa', 'order_by': 'dateArgued desc'})
        self.assertTrue(
            r.content.index('Ander') > r.content.index('Jeremy'),
            msg="'Ander should come AFTER 'Jeremy' when order_by desc."
        )

        r = self.client.get('/', {'type': 'oa', 'order_by': 'dateArgued asc'})
        self.assertTrue(
            r.content.index('Ander') < r.content.index('Jeremy'),
            msg="'Ander should come BEFORE 'Jeremy' when order_by asc."
        )

    def test_oa_case_name_filtering(self):
        r = self.client.get('/', {'type': 'oa', 'case_name': 'ander'})
        self.assertEqual(
            len(html.fromstring(r.content).xpath('//article')),
            1,
            msg="Did not get expected number of results when filtering by " \
                "case name."
        )

    def test_oa_jurisdiction_filtering(self):
        r = self.client.get('/', {'type': 'oa', 'court': 'test'})
        self.assertEqual(
            len(html.fromstring(r.content).xpath('//article')),
            2,
            msg="Did not get expected number of results when filtering by "
                "jurisdiction."
        )

    def test_oa_date_argued_filtering(self):
        r = self.client.get('/', {'type': 'oa', 'argued_after': '2014-10-01'})
        self.assertNotIn(
            "deadly",
            r.content,
            msg="Got a deadly error when doing a Date Argued filter."
        )

    def test_homepage(self):
        """Is the homepage loaded when no GET parameters are provided?"""
        response = self.client.get('/')
        self.assertIn('id="homepage"', response.content,
                      msg="Did not find the #homepage id when attempting to "
                          "load the homepage")

    def test_fail_gracefully(self):
        """Do we fail gracefully when an invalid search is created?"""
        response = self.client.get('/?citation=-')
        self.assertEqual(response.status_code, 200)
        self.assertIn('deadly', response.content,
                      msg="Invalid search did not result in \"deadly\" error.")


class AlertTest(TestCase):
    fixtures = ['test_court.json', 'authtest_data.json']

    def setUp(self):
        # Set up some handy variables
        self.client = Client()
        self.alert_params = {
            'alertText': 'q=asdf',
            'alertName': 'dummy alert',
            'alertFrequency': 'dly',
            'sendNegativeAlert': 'on',
        }

    def test_create_alert(self):
        """Can we create an alert by sending a post?"""
        self.client.login(username='pandora', password='password')
        r = self.client.post('/', self.alert_params, follow=True)
        self.assertEqual(r.redirect_chain[0][1], 302)
        self.assertIn('successfully', r.content)
        self.client.logout()

    def test_fail_gracefully(self):
        """Do we fail gracefully when an invalid alert form is sent?"""
        # Use a copy to shield other tests from changes.
        bad_alert_params = self.alert_params.copy()
        # Break the form
        bad_alert_params.pop('alertText', None)
        self.client.login(username='pandora', password='password')
        r = self.client.post('/', bad_alert_params, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('error creating your alert', r.content)
        self.client.logout()


@override_settings(MEDIA_ROOT='/tmp/%s' % time.time())
class ApiTest(SolrTestCase):
    fixtures = ['test_court.json', 'authtest_data.json']

    def tearDown(self):
        """For these tests we change MEDIA_ROOT so we have a safe place to put
        files as we save them. We need to delete this location once the tests
        finish.
        """
        super(ApiTest, self).tearDown()
        try:
            shutil.rmtree(self.settings().wrapped.MEDIA_ROOT)
        except OSError:
            print "WARNING: Unable to delete %s. This probably means your " \
                  "/tmp directory is getting junked up." % settings.MEDIA_ROOT

    def strip_varying_data(self, endpoint,  actual, correct):
        """A number of metadata fields vary each time the tests are run and
        thus must be stripped so as to not cause issues.
        """
        if endpoint in ('audio', 'cited-by', 'cites', 'docket', 'document',
                        'opinion'):
            for j in (actual, correct,):
                for o in j['objects']:
                    if 'time_retrieved' in o:
                        # Not all objects have this field
                        o['time_retrieved'] = None
                    o['date_modified'] = None
        elif endpoint == 'search':
            # Drop the timestamps and scores b/c they can differ
            for j in (actual, correct):
                for o in j['objects']:
                    o['timestamp'] = None
                    o['score'] = None
        elif endpoint == 'jurisdiction':
            # Drop any non-testing jurisdiction, cause they change over time
            objects = []
            for court in actual['objects']:
                if court['id'] == 'test':
                    court['date_modified'] = None
                    objects.append(court)
                    actual['objects'] = objects
                    break
            actual['meta']['total_count'] = 1
        return actual, correct

    def test_api_meta_data(self):
        """Does the content of the search API have the right meta data?"""
        self.client.login(username='pandora', password='password')
        api_endpoints = {
            'audio': {'params': '', 'api_versions': ('v2',)},
            'citation': {'params': '', 'api_versions': ('v1', 'v2',)},
            'cited-by': {'params': '&id=1', 'api_versions': ('v1', 'v2',)},
            'cites': {'params': '&id=1', 'api_versions': ('v1', 'v2',)},
            'docket': {'params': '', 'api_versions': ('v2',)},
            # opinion --> document in v2.
            'opinion': {'params': '', 'api_versions': ('v1',)},
            'document': {'params': '', 'api_versions': ('v2',)},
            'jurisdiction': {'params': '', 'api_versions': ('v1', 'v2',)},
            'search': {'params': '', 'api_versions': ('v1', 'v2',)},
        }
        # Alphabetical ordering makes the tests run consistently
        api_endpoints_ordered = OrderedDict(sorted(
            api_endpoints.items(),
            key=lambda t: t[0])
        )

        for endpoint, endpoint_dict in api_endpoints_ordered.iteritems():
            for v in endpoint_dict['api_versions']:
                r = self.client.get('/api/rest/%s/%s/?format=json%s' %
                                    (v, endpoint, endpoint_dict['params']))
                actual = simplejson.loads(r.content)

                with open(
                        os.path.join(
                            settings.INSTALL_ROOT,
                            'alert',
                            'search',
                            'test_assets',
                            'api_%s_%s_test_results.json' % (v, endpoint)
                        ),
                        'r') as f:
                    correct = simplejson.load(f)

                    actual, correct = self.strip_varying_data(
                        endpoint,
                        actual,
                        correct
                    )

                    msg = "Response from API did not match expected " \
                          "results (api version: %s, endpoint: %s):\n%s" % (
                              v,
                              endpoint,
                              diff(actual,
                                   correct,
                                   fromfile='actual',
                                   tofile='correct')
                          )
                    self.assertEqual(
                        actual,
                        correct,
                        msg=msg,
                    )

    def test_api_pagination(self):
        """Do the cited-by and cites endpoints paginate properly?"""
        self.client.login(username='pandora', password='password')

        r = self.client.get('/api/rest/v2/cites/?id=1')
        json_no_offset_no_limit = simplejson.loads(r.content)
        self.assertEqual(
            len(json_no_offset_no_limit['objects']),
            2,
            msg="Did not get the expected result count on the cites endpoint."
        )

        # Offset 1.
        r = self.client.get('/api/rest/v2/cites/?id=1&offset=1')
        json_offset_1 = simplejson.loads(r.content)

        # Do we get back one fewer results with the offset?
        self.assertEqual(
            len(json_offset_1['objects']),
            len(json_no_offset_no_limit['objects']) - 1
        )

        # Does the first item of the offset query match the second in the query
        # with no offset?
        self.assertEqual(
            json_offset_1['objects'][0]['absolute_url'],
            json_no_offset_no_limit['objects'][1]['absolute_url'],
        )

        # (1) Does the first item in a query limited to one result match the
        # first item in an unlimited query, and (2) does the first item in a
        # query limited to one result and offset by one match the second item
        # in an unlimited query?
        r = self.client.get('/api/rest/v2/cites/?id=1&limit=1')
        json_limit_1 = simplejson.loads(r.content)
        r = self.client.get('/api/rest/v2/cites/?id=1&limit=1&offset=1')
        json_limit_1_offset_1 = simplejson.loads(r.content)
        self.assertEqual(
            json_limit_1['objects'][0]['absolute_url'],
            json_no_offset_no_limit['objects'][0]['absolute_url']
        )
        self.assertEqual(
            json_limit_1_offset_1['objects'][0]['absolute_url'],
            json_no_offset_no_limit['objects'][1]['absolute_url']
        )

        # Are the results of a limit 1 and an offset 1 different?
        self.assertNotEqual(
            json_limit_1['objects'][0]['absolute_url'],
            json_limit_1_offset_1['objects'][0]['absolute_url']
        )

    def test_api_result_count(self):
        """Do we get back the number of results we expect in the meta data and
        in 'objects'?"""
        self.client.login(username='pandora', password='password')
        api_versions = ['v1', 'v2']
        for v in api_versions:
            r = self.client.get('/api/rest/%s/search/?q=*:*&format=json' % v)
            json = simplejson.loads(r.content)
            # Test the meta data
            self.assertEqual(
                self.expected_num_results_opinion,
                json['meta']['total_count'],
                msg="Metadata count does not match (api version: '%s'):\n"
                    "  Got:\t%s\n"
                    "  Expected:\t%s\n" %
                    (v, json['meta']['total_count'],
                     self.expected_num_results_opinion,)
            )
            # Test the actual data
            num_actual_results = len(json['objects'])
            self.assertEqual(
                self.expected_num_results_opinion,
                num_actual_results,
                msg="Actual number of results varies from expected number "
                    "(api version: '%s'):\n"
                    "  Got:\t%s\n"
                    "  Expected:\t%s\n" %
                    (v, num_actual_results,
                     self.expected_num_results_opinion))

    def test_api_able_to_login(self):
        """Can we login properly?"""
        username, password = 'pandora', 'password'
        logged_in_successfully = self.client.login(
            username=username, password=password)
        self.assertTrue(logged_in_successfully,
                        msg="Unable to log into the test client with:\n"
                            "  Username:\t%s\n"
                            "  Password:\t%s\n" % (username, password))


class FeedTest(SolrTestCase):
    def test_jurisdiction_feed(self):
        """Can we simply load the jurisdiction feed?"""
        response = self.client.get('/feed/court/test/')
        self.assertEqual(200, response.status_code,
                         msg="Did not get 200 OK status code for jurisdiction "
                             "feed")
        html_tree = html.fromstring(response.content)
        node_tests = (
            ('//feed/entry', 3),
            ('//feed/entry/title', 3),
        )
        for test, count in node_tests:
            node_count = len(html_tree.xpath(test))
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                    "Instead found: %s" % (count, test, node_count)
            )


class PagerankTest(CitationTest):
    def test_pagerank_calculation(self):
        """Create a few Documents and fake citation relation among them, then
        run the pagerank algorithm. Check whether this simple case can get the
        correct result.
        """
        #calculate pagerank of these 3 document
        comm = Command()
        self.verbosity = 1
        comm.do_pagerank(chown=False)

        # read in the pagerank file, converting to a dict
        pr_values_from_file = {}
        with open(get_data_dir_location() + "external_pagerank") as f:
            for line in f:
                pk, value = line.split('=')
                pr_values_from_file[pk] = float(value.strip())

        # Verify that whether the answer is correct, based on calculations in
        # Gephi
        answers = {
            '1': 0.387790,
            '2': 0.214811,
            '3': 0.397400,
        }
        for key, value in answers.iteritems():
            self.assertTrue(
                (abs(pr_values_from_file[key]) - value) < 0.0001,
                msg="The answer for item %s was %s when it should have been "
                    "%s" % (key, pr_values_from_file[key],
                            answers[key], )
            )
