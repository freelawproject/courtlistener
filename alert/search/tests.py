from datadiff import diff
from django.test import TestCase
from django.test.client import Client
import simplejson
import time


from alert.lib import sunburnt
from alert.lib.solr_core_admin import create_solr_core, delete_solr_core, swap_solr_core, get_data_dir_location
from alert.search.models import Citation, Court, Document, Docket
from alert.scrapers.test_assets import test_scraper
from alert import settings
from alert.search.management.commands.cl_calculate_pagerank_networkx import Command
from datetime import date


class SetupException(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


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


class SolrTestCase(TestCase):
    """A generic class that contains the setUp and tearDown functions for inheriting children.
    """
    fixtures = ['test_court.json']

    def setUp(self):
        # Set up some handy variables
        self.court = Court.objects.get(pk='test')
        self.client = Client()

        # Set up a testing core in Solr and swap it in
        self.core_name = '%s.test-%s' % (self.__module__, time.time())
        create_solr_core(self.core_name)
        swap_solr_core('collection1', self.core_name)
        self.si = sunburnt.SolrInterface(settings.SOLR_URL, mode='rw')

        # Add two documents to the index, but don't extract their contents
        self.site = test_scraper.Site().parse()
        cite_counts = (4, 6)
        for i in range(0, 2):
            cite = Citation(
                case_name=self.site.case_names[i],
                docket_number=self.site.docket_numbers[i],
                neutral_cite=self.site.neutral_citations[i],
                federal_cite_one=self.site.west_citations[i],
            )
            cite.save(index=False)
            docket = Docket(
                case_name=self.site.case_names[i],
                court=self.court,
            )
            docket.save()
            self.doc = Document(
                date_filed=self.site.case_dates[i],
                citation=cite,
                docket=docket,
                precedential_status=self.site.precedential_statuses[i],
                citation_count=cite_counts[i],
                nature_of_suit=self.site.nature_of_suit[i],
                judges=self.site.judges[i],
            )
            self.doc.save()

        self.expected_num_results = 2

    def tearDown(self):
        self.doc.delete()
        swap_solr_core(self.core_name, 'collection1')
        delete_solr_core(self.core_name)


class SearchTest(SolrTestCase):
    def test_a_simple_text_query(self):
        """Does typing into the main query box work?"""
        response = self.client.get('/', {'q': 'supreme'})
        self.assertIn('Tarrant', response.content)

    def test_a_case_name_query(self):
        """Does querying by case name work?"""
        response = self.client.get('/', {'q': '*:*', 'caseName': 'tarrant'})
        self.assertIn('Tarrant', response.content)

    def test_a_query_with_a_date(self):
        """Does querying by date work?"""
        response = self.client.get('/', {'q': '*:*',
                                         'filed_after': '2013-06',
                                         'filed_before': '2013-07'})
        self.assertIn('Tarrant', response.content)

    def test_faceted_queries(self):
        """Does querying in a given court return the document? Does querying the wrong facets exclude it?"""
        response = self.client.get('/', {'q': '*:*', 'court_test': 'on'})
        self.assertIn('Tarrant', response.content)
        response = self.client.get('/', {'q': '*:*', 'stat_Errata': 'on'})
        self.assertNotIn('Tarrant', response.content)

    def test_a_docket_number_query(self):
        """Can we query by docket number?"""
        response = self.client.get('/', {'q': '*:*', 'docket_number': '11-889'})
        self.assertIn('Tarrant', response.content, "Result not found by docket number!")

    def test_a_west_citation_query(self):
        """Can we query by citation number?"""
        get_dicts = [{'q': '*:*', 'citation': '44'},
                     {'q': 'citation:44'},
                     {'q': 'westcite:44'}]  # Tests query field lower-casing, and the deprecated field.
        for get_dict in get_dicts:
            response = self.client.get('/', get_dict)
            self.assertIn('Tarrant', response.content)

    def test_a_neutral_citation_query(self):
        """Can we query by neutral citation numbers?"""
        response = self.client.get('/', {'q': '*:*', 'neutral_cite': '44'})
        self.assertIn('Tarrant', response.content)

    def test_a_query_with_a_old_date(self):
        """Do we have any recurrent issues with old dates and strftime (issue 220)?"""
        response = self.client.get('/', {'q': '*:*', 'filed_after': '1890'})
        self.assertEqual(200, response.status_code)

    def test_a_judge_query(self):
        """Can we query by judge name?"""
        response = self.client.get('/', {'q': '*:*', 'judge': 'david'})
        self.assertIn('Tarrant', response.content)
        response = self.client.get('/', {'q': 'judge:david'})
        self.assertIn('Tarrant', response.content)

    def test_a_nature_of_suit_query(self):
        """Can we query by nature of suit?"""
        response = self.client.get('/', {'q': 'suitNature:copyright'})
        self.assertIn('Tarrant', response.content)

    def test_citation_filtering(self):
        """Can we find Documents by citation filtering?"""
        msg = "%s case back when filtering by citation count."
        response = self.client.get('/', {'q': '*:*', 'cited_lt': 5, 'cited_gt': 3})
        self.assertIn('Tarrant', response.content, msg=msg % 'Did not get')
        response = self.client.get('/', {'q': '*:*', 'cited_lt': 10, 'cited_gt': 8})
        self.assertNotIn('Tarrant', response.content, msg=msg % 'Got')

    def test_citation_ordering(self):
        """Can the results be re-ordered by citation count?"""
        response = self.client.get('/', {'q': '*:*', 'order_by': 'citeCount desc'})
        self.assertTrue(response.content.index('Disclosure') < response.content.index('Tarrant'),
                        msg="'Disclosure' should come BEFORE 'Tarrant' when ordered by descending citeCount.")
        response = self.client.get('/', {'q': '*:*', 'order_by': 'citeCount asc'})
        self.assertTrue(response.content.index('Disclosure') > response.content.index('Tarrant'),
                        msg="'Disclosure' should come AFTER 'Tarrant' when ordered by ascending citeCount.")

    def test_homepage(self):
        """Is the homepage loaded when no GET parameters are provided?"""
        response = self.client.get('/')
        self.assertIn('id="homepage"', response.content, msg="Did not find the #homepage id when attempting to load the "
                                                         "homepage")

    def test_fail_gracefully(self):
        """Do we fail gracefully when an invalid search is created?"""
        response = self.client.get('/?citation=-')
        self.assertEqual(response.status_code, 200)
        self.assertIn('deadly', response.content, msg="Invalid search did not result in \"deadly\" error.")


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


class ApiTest(SolrTestCase):
    fixtures = ['test_court.json', 'authtest_data.json']

    def test_api_meta_data(self):
        """Does the content of the search API have the right meta data?"""
        self.client.login(username='pandora', password='password')
        api_versions = ['v1', 'v2']
        api_endpoint_parameters = {
            'search': '?q=*:*&format=json',
            'jurisdiction': '?format=json',
        }
        for v in api_versions:
            for endpoint, params in api_endpoint_parameters.iteritems():
                r = self.client.get('/api/rest/%s/%s/%s' % (v, endpoint, params))
                json_actual = simplejson.loads(r.content)

                with open('search/test_assets/api_%s_%s_test_results.json' % (v, endpoint), 'r') as f:
                    json_correct = simplejson.load(f)

                if endpoint == 'search':
                    # Drop the timestamps and scores b/c they can differ
                    for j in [json_actual, json_correct]:
                        for o in j['objects']:
                            o['timestamp'] = None
                            o['score'] = None
                elif endpoint == 'jurisdiction':
                    # Drop any non-testing jurisdiction, cause they change over time
                    objects = []
                    for court in json_actual['objects']:
                        if court['id'] == 'test':
                            court['date_modified'] = None
                            objects.append(court)
                            json_actual['objects'] = objects
                            break
                    json_actual['meta']['total_count'] = 1
                msg = "Response from search API did not match expected results (api version: %s, endpoint: %s):\n%s" % (
                    v,
                    endpoint,
                    diff(json_actual,
                         json_correct,
                         fromfile='actual',
                         tofile='correct')
                )
                self.assertEqual(
                    json_actual,
                    json_correct,
                    msg=msg,
                )

    def test_api_result_count(self):
        """Do we get back the number of results we expect in the meta data and in 'objects'?"""
        self.client.login(username='pandora', password='password')
        api_versions = ['v1', 'v2']
        for v in api_versions:
            r = self.client.get('/api/rest/%s/search/?q=*:*&format=json' % v)
            json = simplejson.loads(r.content)
            # Test the meta data
            self.assertEqual(self.expected_num_results,
                             json['meta']['total_count'],
                             msg="Metadata result count does not match (api version: '%s'):\n"
                                 "  Got:\t%s\n"
                                 "  Expected:\t%s\n" % (v,
                                                        json['meta']['total_count'],
                                                        self.expected_num_results,))
            # Test the actual data
            num_actual_results = len(json['objects'])
            self.assertEqual(self.expected_num_results,
                             num_actual_results,
                             msg="Actual number of results varies from expected number (api version: '%s'):\n"
                                 "  Got:\t%s\n"
                                 "  Expected:\t%s\n" % (v, num_actual_results, self.expected_num_results))

    def test_api_able_to_login(self):
        """Can we login properly?"""
        username, password = 'pandora', 'password'
        logged_in_successfully = self.client.login(username=username, password=password)
        self.assertTrue(logged_in_successfully,
                        msg="Unable to log into the test client with:\n"
                            "  Username:\t%s\n"
                            "  Password:\t%s\n" % (username, password))


class PagerankTest(TestCase):
    fixtures = ['test_court.json']

    def test_pagerank_calculation(self):
        """Create a few Documents and fake citation relation among them, then run the pagerank
        algorithm. Check whether this simple case can get the correct result.
        """
        # Set up some handy variables
        self.court = Court.objects.get(pk='test')

        #create 3 documents with their citations and dockets
        c1, c2, c3 = Citation(case_name=u"c1"), Citation(case_name=u"c2"), Citation(case_name=u"c3")
        c1.save(index=False)
        c2.save(index=False)
        c3.save(index=False)
        docket1 = Docket(
            case_name=u"c1",
            court=self.court,
        )
        docket2 = Docket(
            case_name=u"c2",
            court=self.court,
        )
        docket3 = Docket(
            case_name=u"c3",
            court=self.court,
        )
        d1, d2, d3 = Document(date_filed=date.today()), Document(date_filed=date.today()), Document(date_filed=date.today())
        d1.citation, d2.citation, d3.citation = c1, c2, c3
        d1.docket, d2.docket, d3.docket = docket1, docket2, docket3
        doc_list = [d1, d2, d3]
        for d in doc_list:
            d.citation.save(index=False)
            d.save(index=False)

        #create simple citing relation: 1 cites 2 and 3; 2 cites 3; 3 cites 1;
        d1.cases_cited.add(d2.citation)
        d2.citation_count += 1
        d2.cases_cited.add(d3.citation)
        d3.citation_count += 1
        d3.cases_cited.add(d1.citation)
        d1.citation_count += 1
        d1.cases_cited.add(d3.citation)
        d3.citation_count += 1
        d1.save(index=False)
        d2.save(index=False)
        d3.save(index=False)

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

        # Verify that whether the answer is correct, based on calculations in Gephi
        answers = {
            '1': 0.387790,
            '2': 0.214811,
            '3': 0.397400,
        }
        for key, value in answers.iteritems():
            self.assertTrue(
                (abs(pr_values_from_file[key]) - value) < 0.0001,
                msg="The answer for item %s was %s when it should have been %s" % (key, pr_values_from_file[key],
                                                                                   answers[key], )
            )
