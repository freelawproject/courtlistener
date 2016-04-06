# coding=utf-8
import StringIO
import datetime
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.http import HttpRequest
from django.test import TestCase, override_settings
from lxml import etree, html

from cl.lib.solr_core_admin import get_data_dir
from cl.lib.test_helpers import SolrTestCase, IndexedSolrTestCase
from cl.search.feeds import JurisdictionFeed
from cl.search.models import Court, Docket, Opinion, OpinionCluster
from cl.search.management.commands.cl_calculate_pagerank import Command
from cl.tests.base import BaseSeleniumTest


class SetupException(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class UpdateIndexCommandTest(SolrTestCase):
    args = [
        '--type', 'opinions',
        '--noinput',
    ]

    def _get_result_count(self, results):
        return results.result.numFound

    def test_updating_all_opinions(self):
        """If we have items in the DB, can we add/delete them to/from Solr?

        This tests is rather long because we need to test adding and deleting,
        and it's hard to setup/dismantle the indexes before/after every test.
        """

        # First, we add everything to Solr.
        args = list(self.args)  # Make a copy of the list.
        args.extend([
            '--solr-url',
            'http://127.0.0.1:8983/solr/%s' % self.core_name_opinion,
            '--update',
            '--everything',
            '--do-commit',
        ])
        call_command('cl_update_index', *args)
        results = self.si_opinion.raw_query(**{'q': '*:*'}).execute()
        actual_count = self._get_result_count(results)
        self.assertEqual(
            actual_count,
            self.expected_num_results_opinion,
            msg="Did not get expected number of results.\n"
                "\tGot:\t%s\n\tExpected:\t %s" % (
                    actual_count,
                    self.expected_num_results_opinion,
                ),
        )

        # Check a simple citation query
        results = self.si_opinion.raw_query(**{'q': 'cites:3'}).execute()
        actual_count = self._get_result_count(results)
        expected_citation_count = 2
        self.assertEqual(
            actual_count,
            expected_citation_count,
            msg="Did not get the expected number of citation counts.\n"
                "\tGot:\t %s\n\tExpected:\t%s" % (
                    actual_count,
                    expected_citation_count,
                ),
        )

        # Next, we delete everything from Solr
        args = list(self.args)  # Make a copy of the list.
        args.extend([
            '--solr-url',
            'http://127.0.0.1:8983/solr/%s' % self.core_name_opinion,
            '--delete',
            '--everything',
            '--do-commit',
        ])
        call_command('cl_update_index', *args)
        results = self.si_opinion.raw_query(**{'q': '*:*'}).execute()
        actual_count = self._get_result_count(results)
        expected_citation_count = 0
        self.assertEqual(
            actual_count,
            expected_citation_count,
            msg="Did not get the expected number of counts in empty index.\n"
                "\tGot:\t %s\n\tExpected:\t%s" % (
                    actual_count,
                    expected_citation_count,
                ),
        )

        # Add things back, but do it by ID
        args = list(self.args)  # Make a copy of the list.
        args.extend([
            '--solr-url',
            'http://127.0.0.1:8983/solr/%s' % self.core_name_opinion,
            '--update',
            '--items', '1', '2', '3',
            '--do-commit',
        ])
        call_command('cl_update_index', *args)
        results = self.si_opinion.raw_query(**{'q': '*:*'}).execute()
        actual_count = self._get_result_count(results)
        expected_citation_count = 3
        self.assertEqual(
            actual_count,
            expected_citation_count,
            msg="Did not get the expected number of citation counts.\n"
                "\tGot:\t %s\n\tExpected:\t%s" % (
                    actual_count,
                    expected_citation_count,
                ),
        )


class ModelTest(TestCase):
    fixtures = ['test_court.json']

    def test_save_old_opinion(self):
        """Can we save opinions older than 1900?"""
        court = Court.objects.get(pk='test')

        docket = Docket(case_name=u"Blah", court=court, source=Docket.DEFAULT)
        docket.save()
        oc = OpinionCluster(
            case_name=u"Blah",
            docket=docket,
            date_filed=datetime.date(1899, 1, 1),
        )
        oc.save()
        o = Opinion(cluster=oc, type='Lead Opinion')

        try:
            cf = ContentFile(StringIO.StringIO('blah').read())
            o.file_with_date = datetime.date(1899, 1, 1)
            o.local_path.save('file_name.pdf', cf, save=False)
            o.save(index=True)
        except ValueError as e:
            raise ValueError("Unable to save a case older than 1900. Did you "
                             "try to use `strftime`...again?")


class SearchTest(IndexedSolrTestCase):
    def test_a_simple_text_query(self):
        """Does typing into the main query box work?"""
        r = self.client.get('/', {'q': 'supreme'})
        self.assertIn('Honda', r.content)
        self.assertIn('1 Result', r.content)

    def test_a_case_name_query(self):
        """Does querying by case name work?"""
        r = self.client.get('/', {'q': '*:*', 'case_name': 'honda'})
        self.assertIn('Honda', r.content)

    def test_a_query_with_white_space_only(self):
        """Does everything work when whitespace is in various fields?"""
        r = self.client.get('/', {'q': ' ',
                                  'judge': ' ',
                                  'case_name': ' '})
        self.assertIn('Honda', r.content)
        self.assertNotIn('deadly', r.content)

    def test_a_query_with_a_date(self):
        """Does querying by date work?"""
        response = self.client.get('/', {'q': '*:*',
                                         'filed_after': '1795-06',
                                         'filed_before': '1796-01'})
        self.assertIn('Honda', response.content)

    def test_faceted_queries(self):
        """Does querying in a given court return the document? Does querying
        the wrong facets exclude it?
        """
        r = self.client.get('/', {'q': '*:*', 'court_test': 'on'})
        self.assertIn('Honda', r.content)
        r = self.client.get('/', {'q': '*:*', 'stat_Errata': 'on'})
        self.assertNotIn('Honda', r.content)
        self.assertIn("Debbas", r.content)

    def test_a_docket_number_query(self):
        """Can we query by docket number?"""
        r = self.client.get('/', {'q': '*:*', 'docket_number': '2'})
        self.assertIn(
            'Honda',
            r.content,
            "Result not found by docket number!"
        )

    def test_a_west_citation_query(self):
        """Can we query by citation number?"""
        get_dicts = [{'q': '*:*', 'citation': '33'},
                     {'q': 'citation:33'}]
        for get_dict in get_dicts:
            r = self.client.get('/', get_dict)
            self.assertIn('Honda', r.content)

    def test_a_neutral_citation_query(self):
        """Can we query by neutral citation numbers?"""
        r = self.client.get('/', {'q': '*:*', 'neutral_cite': '22'})
        self.assertIn('Honda', r.content)

    def test_a_query_with_a_old_date(self):
        """Do we have any recurrent issues with old dates and strftime (issue
        220)?"""
        r = self.client.get('/', {'q': '*:*', 'filed_after': '1890'})
        self.assertEqual(200, r.status_code)

    def test_a_judge_query(self):
        """Can we query by judge name?"""
        r = self.client.get('/', {'q': '*:*', 'judge': 'david'})
        self.assertIn('Honda', r.content)
        r = self.client.get('/', {'q': 'judge:david'})
        self.assertIn('Honda', r.content)

    def test_a_nature_of_suit_query(self):
        """Can we query by nature of suit?"""
        r = self.client.get('/', {'q': 'suitNature:"copyright"'})
        self.assertIn('Honda', r.content)

    def test_citation_filtering(self):
        """Can we find Documents by citation filtering?"""
        r = self.client.get('/', {'q': '*:*', 'cited_lt': 7, 'cited_gt': 5})
        self.assertIn(
            'Honda',
            r.content,
            msg=u'Did not get case back when filtering by citation count.'
        )
        r = self.client.get('/', {'q': '*:*', 'cited_lt': 100, 'cited_gt': 80})
        self.assertIn(
            "had no results",
            r.content,
            msg=u'Got case back when filtering by crazy citation count.'
        )

    def test_citation_ordering(self):
        """Can the results be re-ordered by citation count?"""
        r = self.client.get('/', {'q': '*:*', 'order_by': 'citeCount desc'})
        most_cited_name = 'case name cluster 3'
        less_cited_name = 'Howard v. Honda'
        self.assertTrue(
            r.content.index(most_cited_name) < r.content.index(less_cited_name),
            msg="'%s' should come BEFORE '%s' when ordered by descending "
                "citeCount." % (most_cited_name, less_cited_name))

        r = self.client.get('/', {'q': '*:*', 'order_by': 'citeCount asc'})
        self.assertTrue(
            r.content.index(most_cited_name) > r.content.index(less_cited_name),
            msg="'%s' should come AFTER '%s' when ordered by ascending "
                "citeCount." % (most_cited_name, less_cited_name))

    def test_oa_results_basic(self):
        r = self.client.get('/', {'type': 'oa'})
        self.assertIn('Jose', r.content)

    def test_oa_results_date_argued_ordering(self):
        r = self.client.get('/', {'type': 'oa', 'order_by': 'dateArgued desc'})
        self.assertTrue(
            r.content.index('SEC') < r.content.index('Jose'),
            msg="'SEC' should come BEFORE 'Jose' when order_by desc."
        )

        r = self.client.get('/', {'type': 'oa', 'order_by': 'dateArgued asc'})
        self.assertTrue(
            r.content.index('Jose') < r.content.index('SEC'),
            msg="'Jose' should come AFTER 'SEC' when order_by asc."
        )

    def test_oa_case_name_filtering(self):
        r = self.client.get('/', {'type': 'oa', 'case_name': 'jose'})
        actual = len(html.fromstring(r.content).xpath('//article'))
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by " \
                "case name. Expected %s, but got %s." % (expected, actual)
        )

    def test_oa_jurisdiction_filtering(self):
        r = self.client.get('/', {'type': 'oa', 'court': 'test'})
        actual = len(html.fromstring(r.content).xpath('//article'))
        expected = 2
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
                "jurisdiction. Expected %s, but got %s." % (actual, expected)
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
        response = self.client.get('/?neutral_cite=-')
        self.assertEqual(response.status_code, 200)
        self.assertIn('deadly', response.content,
                      msg="Invalid search did not result in \"deadly\" error.")


class JudgeSearchTest(IndexedSolrTestCase):
    def test_sorting(self):
        """Can we do sorting on various fields?"""
        sort_fields = ['name_reverse asc', 'dob desc', 'dod desc']
        for sort_field in sort_fields:
            r = self.client.get('/', {'type': 'p', 'ordered_by': sort_field})
            self.assertNotIn(
                'deadly',
                r.content.lower(),
                msg="Got a deadly error when doing a judge search ordered "
                    "by %s" % sort_field
            )


class FeedTest(IndexedSolrTestCase):
    def test_jurisdiction_feed(self):
        """Can we simply load the jurisdiction feed?"""
        response = self.client.get(reverse('jurisdiction_feed',
                                           kwargs={'court': 'test'}))
        self.assertEqual(200, response.status_code,
                         msg="Did not get 200 OK status code for jurisdiction "
                             "feed")
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ('//a:feed/a:entry', 5),
            ('//a:feed/a:entry/a:title', 5),
        )
        for test, expected_count in node_tests:
            actual_count = len(xml_tree.xpath(
                test,
                namespaces={'a': 'http://www.w3.org/2005/Atom'})
            )
            self.assertEqual(
                actual_count,
                expected_count,
                msg="Did not find %s node(s) with XPath query: %s. "
                    "Instead found: %s" % (expected_count, test, actual_count)
            )


@override_settings(
    MEDIA_ROOT=os.path.join(settings.INSTALL_ROOT, 'cl/assets/media/test/')
)
class JurisdictionFeedTest(TestCase):

    fixtures = ['court_data.json']

    def setUp(self):
        self.good_item = {
            'title': 'Opinion Title',
            'court': 'SCOTUS',
            'absolute_url': 'http://absolute_url',
            'caseName': 'Case Name',
            'status': 'Precedential',
            'dateFiled': datetime.date(2015, 12, 25),
            'local_path': 'txt/2015/12/28/opinion_text.txt'
        }
        self.zero_item = self.good_item.copy()
        self.zero_item.update({
            'local_path': 'txt/2015/12/28/opinion_text_bad.junk'
        })
        self.bad_item = self.good_item.copy()
        self.bad_item.update({
            'local_path': 'asdfasdfasdfasdfasdfasdfasdfasdfasdjkfasdf'
        })
        self.pdf_item = self.good_item.copy()
        self.pdf_item.update({
            'local_path': 'pdf/2013/06/12/' \
                + 'in_re_motion_for_consent_to_disclosure_of_court_records.pdf'
        })
        self.null_item = self.good_item.copy()
        self.null_item.update({
            'local_path': None
        })
        self.feed = JurisdictionFeed()
        super(JurisdictionFeedTest, self).setUp()

    def test_proper_calculation_of_length(self):
        """
        Does the item_enclosure_length method count the file size properly?
        """
        self.assertEqual(self.feed.item_enclosure_length(self.good_item), 31293)
        self.assertEqual(
            self.feed.item_enclosure_length(self.zero_item),
            0,
            'item %s should be zero bytes' % (self.zero_item['local_path'])
        )

    def test_enclosure_length_returns_none_on_bad_input(self):
        """Given a bad path to a nonexistant file, do we safely return None?"""
        self.assertIsNone(self.feed.item_enclosure_length(self.bad_item))

    def test_item_enclosure_mime_type(self):
        """Does the mime type detection work correctly?"""
        self.assertEqual(
            self.feed.item_enclosure_mime_type(self.good_item),
            'text/plain'
        )

    def test_item_enclosure_mime_type_handles_bogus_files(self):
        """
        Does the mime type detection safely return a good default value when
        given a file it can't detect the mime type for?
        """
        self.assertEqual(
            self.feed.item_enclosure_mime_type(self.zero_item),
            'application/octet-stream',
        )
        self.assertEqual(
            self.feed.item_enclosure_mime_type(self.bad_item),
            'application/octet-stream',
        )

    def test_feed_renders_with_item_without_file_path(self):
        """
        For Opinions without local_path attributes (that is they don't have a
        corresponding original PDF/txt/doc file) can we render the feed without
        the enclosures
        """
        fake_results = [self.null_item]

        class FakeFeed(JurisdictionFeed):
            link = 'http://localhost'
            def items(self, obj):
                return fake_results
        court = Court.objects.get(pk='test')
        request = HttpRequest()
        request.path = '/feed'
        try:
            feed = FakeFeed().get_feed(court, request)
            xml = feed.writeString('utf-8')
            self.assertIn(
                'feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-us"',
                xml
            )
            self.assertNotIn('enclosure', xml)
        except Exception as e:
            self.fail('Could not call get_feed(): %s' % (e,))


class PagerankTest(TestCase):
    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def test_pagerank_calculation(self):
        """Create a few items and fake citation relation among them, then
        run the pagerank algorithm. Check whether this simple case can get the
        correct result.
        """
        # calculate pagerank of these 3 document
        comm = Command()
        self.verbosity = 1
        comm.do_pagerank(chown=False)

        # read in the pagerank file, converting to a dict
        pr_values_from_file = {}
        data_path = get_data_dir('collection1') + "external_pagerank"
        with open(data_path) as f:
            for line in f:
                pk, value = line.split('=')
                pr_values_from_file[pk] = float(value.strip())

        # Verify that whether the answer is correct, based on calculations in
        # Gephi
        answers = {
            '1': 0.369323534954,
            '2': 0.204581549974,
            '3': 0.378475867453,
        }
        for key, value in answers.items():
            self.assertTrue(
                abs(pr_values_from_file[key] - value) < 0.0001,
                msg="The answer for item %s was %s when it should have been "
                    "%s" % (key, pr_values_from_file[key],
                            answers[key],)
            )


class OpinionSearchFunctionalTest(BaseSeleniumTest):
    """
    Test some of the primary search functionality of CL: searching opinions.
    These tests should exercise all aspects of using the search box and SERP.
    """
    fixtures = ['test_court.json', 'authtest_data.json',
                'judge_judy.json', 'test_objects_search.json',
                'functest_opinions.json', 'test_objects_audio.json']

    def _perform_wildcard_search(self):
        searchbox = self.browser.find_element_by_id('id_q')
        searchbox.send_keys('\n')
        result_count = self.browser.find_element_by_id('result-count')
        self.assertIn('Results', result_count.text)

    def test_toggle_to_oral_args_search_results(self):
        # Dora navigates to the global SERP from the homepage
        self.browser.get(self.server_url)
        self._perform_wildcard_search()
        self.extract_result_count_from_serp()

        # Dora sees she has Opinion results, but wants Oral Arguments
        self.assertTrue(self.extract_result_count_from_serp() > 0)
        label = (self.browser
                 .find_element_by_css_selector('label[for="id_type_0"]'))
        self.assertEqual('Opinions', label.text.strip())
        self.assertIn('selected', label.get_attribute('class'))
        self.assert_text_in_body('Date Filed')
        self.assert_text_not_in_body('Date Argued')

        # She clicks on Oral Arguments
        self.browser \
            .find_element_by_css_selector('label[for="id_type_1"]') \
            .click()

        # And notices her result set is now different
        oa_label = self.browser. \
            find_element_by_css_selector('label[for="id_type_1"]')
        self.assertIn('selected', oa_label.get_attribute('class'))
        self.assert_text_in_body('Date Argued')
        self.assert_text_not_in_body('Date Filed')

    def test_search_and_facet_docket_numbers(self):
        # Dora goes to CL and performs an initial wildcard Search
        self.browser.get(self.server_url)
        self._perform_wildcard_search()
        initial_count = self.extract_result_count_from_serp()

        # Seeing a result that has a docket number displayed, she wants
        # to find all similar opinions with the same or similar docket
        # number
        search_results = self.browser.find_element_by_id('search-results')
        self.assertIn('Docket Number:', search_results.text)

        # She types part of the docket number into the docket number
        # filter on the left and hits enter
        text_box = self.browser.find_element_by_id('id_docket_number')
        text_box.send_keys('1337\n')

        # The SERP refreshes and she sees resuls that
        # only contain fragments of the docker number she entered
        new_count = self.extract_result_count_from_serp()
        self.assertTrue(new_count < initial_count)

        search_results = self.browser.find_element_by_id('search-results')
        for result in search_results.find_elements_by_tag_name('article'):
            self.assertIn('1337', result.text)

    def test_opinion_search_result_detail_page(self):
        # Dora navitages to CL and does a simple wild card search
        self.browser.get(self.server_url)
        self.browser.find_element_by_id('id_q').send_keys('voutila\n')

        # Seeing an Opinion immediately on the first page of results, she
        # wants more details so she clicks the title and drills into the result
        articles = self.browser.find_elements_by_tag_name('article')
        articles[0].find_elements_by_tag_name('a')[0].click()

        # She is brought to the detail page for the results
        self.assertNotIn('Search Results', self.browser.title)
        self.assert_text_in_body('Back to Search Results')
        article_text = self.browser.find_element_by_tag_name('article').text

        # and she can see lots of detail! This includes things like:
        # The name of the jurisdiction/court,
        # the status of the Opinion, any citations, the docket number,
        # the Judges, and a unique fingerpring ID
        meta_data = (self.browser
                     .find_elements_by_css_selector('.meta-data-header'))
        headers = [u'Filed:', u'Precedential Status:', u'Citations:',
                   u'Docket Number:', u'Judges:', u'Nature of suit:']
        for header in headers:
            self.assertIn(header, [meta.text for meta in meta_data])

        # The complete body of the opinion is also displayed for her to
        # read on the page
        self.assertNotEqual(
                self.browser.find_element_by_id('opinion-content').text.strip(),
                ''
        )

        # She wants to dig a big deeper into the influence of this Opinion,
        # so she's able to see links to the first five citations on the left
        # and a link to the full list
        cited_by = self.browser.find_element_by_id('cited-by')
        self.assertIn('Cited By', cited_by.find_element_by_tag_name('h3').text)
        citations = cited_by.find_elements_by_tag_name('li')
        self.assertTrue(0 < len(citations) < 6)

        # She clicks the "Full List of Citations" link and is brought to
        # a SERP page with all the citations, generated by a query
        full_list = (cited_by
                     .find_element_by_link_text('View All Citing Opinions'))
        full_list.click()

        # She notices this submits a new query targeting anything citing the
        # original opinion she was viewing. She notices she's back on the SERP
        self.assertIn('Search Results for', self.browser.title)
        query = self.browser.find_element_by_id('id_q').get_attribute('value')
        self.assertIn('cites:', query)

        # She wants to go back to the Opinion page, so she clicks back in her
        # browser, expecting to return to the Opinion details
        self.browser.back()
        self.assertNotIn('Search Results', self.browser.title)
        self.assertEqual(
                self.browser.find_element_by_tag_name('article').text,
                article_text
        )

        # She now wants to see details on the list of Opinions cited within
        # this particular opinion. She notices an abbreviated list on the left,
        # and can click into a Full Table of Authorities. (She does so.)
        authorities = self.browser.find_element_by_id('authorities')
        self.assertIn(
                'Authorities',
                authorities.find_element_by_tag_name('h3').text
        )
        authority_links = authorities.find_elements_by_tag_name('li')
        self.assertTrue(0 < len(authority_links) < 6)
        (authorities
         .find_element_by_link_text('View All Authorities')
         .click())
        self.assertIn('Table of Authorities', self.browser.title)

        # Like before, she's just curious of the list and clicks Back to
        # Document.
        self.browser.find_element_by_link_text('Back to Opinion').click()

        # And she's back at the Opinion in question and pretty happy about that
        self.assertNotIn('Table of Authorities', self.browser.title)
        self.assertEqual(
                self.browser.find_element_by_tag_name('article').text,
                article_text
        )

    def test_search_and_add_precedential_results(self):
        # Dora navigates to CL and just hits Search to just start with
        # a global result set
        self.browser.get(self.server_url)
        self._perform_wildcard_search()
        first_count = self.extract_result_count_from_serp()

        # She notices only Precedential results are being displayed
        prec = self.browser.find_element_by_id('id_stat_Precedential')
        non_prec = self.browser.find_element_by_id('id_stat_Non-Precedential')
        self.assertEqual(prec.get_attribute('checked'), u'true')
        self.assertIsNone(non_prec.get_attribute('checked'))
        prec_count = self.browser.find_element_by_css_selector(
                'label[for="id_stat_Precedential"]'
        )
        non_prec_count = self.browser.find_element_by_css_selector(
                'label[for="id_stat_Non-Precedential"]'
        )
        self.assertNotIn('(0)', prec_count.text)
        self.assertNotIn('(0)', non_prec_count.text)

        # Even though she notices all jurisdictions were included in her search
        self.assert_text_in_body('All Jurisdictions Selected')

        # But she also notices the option to select and include
        # non_precedential results. She checks the box.
        non_prec.click()

        # Nothing happens yet.
        # TODO: this is hacky for now...just make sure result count is same
        self.assertEqual(first_count, self.extract_result_count_from_serp())

        # She goes ahead and clicks the Search button again to resubmit
        self.browser.find_element_by_id('search-button').click()

        # She didn't change the query, so the search box should still look
        # the same (which is blank)
        self.assertEqual(
                self.browser.find_element_by_id('id_q').get_attribute('value'),
                u''
        )

        # And now she notices her result set increases thanks to adding in
        # those other opinion types!
        second_count = self.extract_result_count_from_serp()
        self.assertTrue(second_count > first_count)

    def test_basic_homepage_search_and_signin_and_signout(self):

        # Dora navigates to the CL website.
        self.browser.get(self.server_url)

        # At a glance, Dora can see the Latest Opinions, Latest Oral Arguments,
        # the searchbox (obviously important), and a place to sign in
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertIn('Latest Opinions', page_text)
        self.assertIn('Latest Oral Arguments', page_text)

        search_box = self.browser.find_element_by_id('id_q')
        search_button = self.browser.find_element_by_id('search-button')
        self.assertIn('Search', search_button.text)

        self.assertIn('Sign in / Register', page_text)

        # Dora remembers this Lissner guy and wonders if he's been involved
        # in any litigation. She types his name into the search box and hits
        # Enter
        search_box.send_keys('lissner\n')

        # The browser brings her to a search engine result page with some
        # results. She notices her query is still in the searchbox and
        # has the ability to refine via facets
        result_count = self.browser.find_element_by_id('result-count')
        self.assertIn('1 Result', result_count.text)
        search_box = self.browser.find_element_by_id('id_q')
        self.assertEqual('lissner', search_box.get_attribute('value'))

        facet_sidebar = (self.browser
                         .find_element_by_id('sidebar-facet-placeholder'))
        self.assertIn('Precedential Status', facet_sidebar.text)

        # Wanting to keep an eye on this Lissner guy, she decides to sign-in
        # and so she can create an alert
        sign_in = self.browser.find_element_by_link_text('Sign in / Register')
        sign_in.click()

        # she providers her usename and password to sign in
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertIn('Sign In', page_text)
        self.assertIn('Username', page_text)
        self.assertIn('Password', page_text)
        btn = self.browser.find_element_by_css_selector('button[type="submit"]')
        self.assertEqual('Sign In', btn.text)

        self.browser.find_element_by_id('username').send_keys('pandora')
        self.browser.find_element_by_id('password').send_keys('password')
        btn.click()

        # upon redirect, she's brought back to her original search results
        # for 'lissner'
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertNotIn(
                'Please enter a correct username and password.',
                page_text
        )
        search_box = self.browser.find_element_by_id('id_q')
        self.assertEqual('lissner', search_box.get_attribute('value'))

        # She now sees the form for creating an alert
        self.assertIn('Create an Alert', page_text)
        self.assertIn('Give the alert a name', page_text)
        self.assertIn('How often should we notify you?', page_text)
        self.browser.find_element_by_id('id_name')
        self.browser.find_element_by_id('id_rate')
        btn = self.browser.find_element_by_id('alertSave')
        self.assertEqual('Create Alert', btn.text)

        # But she decides to wait until another time. Instead she decides she
        # will log out. She notices a Profile link dropdown in the top of the
        # page, clicks it, and selects Sign out
        profile_dropdown = (self.browser
                            .find_elements_by_css_selector('a.dropdown-toggle')[1])
        self.assertEqual(profile_dropdown.text.strip(), u'Profile')

        dropdown_menu = (self.browser
                         .find_element_by_css_selector('ul.dropdown-menu'))
        self.assertIsNone(dropdown_menu.get_attribute('display'))

        profile_dropdown.click()

        sign_out = self.browser.find_element_by_link_text('Sign out')
        sign_out.click()

        # She receives a sign out confirmation with links back to the homepage,
        # the block, and an option to sign back in.
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertIn('You Have Successfully Signed Out', page_text)
        links = self.browser.find_elements_by_tag_name('a')
        self.assertIn('Go to the homepage', [link.text for link in links])
        self.assertIn('Read our blog', [link.text for link in links])

        bootstrap_btns = self.browser.find_elements_by_css_selector('a.btn')
        self.assertIn('Sign Back In', [btn.text for btn in bootstrap_btns])

