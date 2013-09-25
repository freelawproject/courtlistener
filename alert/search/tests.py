from django.test import TestCase
from django.test.client import Client
import time

from alert.lib import sunburnt
from alert.lib.solr_core_admin import create_solr_core, delete_solr_core, swap_solr_core
from alert.search.models import Citation, Court, Document
from alert.scrapers.test_assets import test_scraper
from alert import settings
from alert.search import models
from alert.search.management.commands.cl_calculate_pagerank import Command

class SetupException(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class SearchTest(TestCase):
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
            cite = Citation(case_name=self.site.case_names[i],
                            docket_number=self.site.docket_numbers[i],
                            neutral_cite=self.site.neutral_citations[i],
                            federal_cite_one=self.site.west_citations[i])
            cite.save(index=False)
            self.doc = Document(date_filed=self.site.case_dates[i],
                                court=self.court,
                                citation=cite,
                                precedential_status=self.site.precedential_statuses[i],
                                citation_count=cite_counts[i],
                                nature_of_suit=self.site.nature_of_suit[i],
                                judges=self.site.judges[i])
            self.doc.save()

    def tearDown(self):
        self.doc.delete()
        swap_solr_core(self.core_name, 'collection1')
        delete_solr_core(self.core_name)

    def test_a_simple_text_query(self):
        """Does typing into the main query box work?"""
        response = self.client.get('/', {'q': 'supreme'})
        self.assertIn('Tarrant', response.content)

    def test_a_case_name_query(self):
        """Does querying by case name work?"""
        response = self.client.get('/', {'q': '*:*', 'case_name': 'tarrant'})
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
        response = self.client.get('/', {'q': '*:*', 'sort': 'citeCount desc'})
        self.assertTrue(response.content.index('Disclosure') < response.content.index('Tarrant'),
                        msg="'Disclosure' should come BEFORE 'Tarrant' when ordered by descending citeCount.")
        response = self.client.get('/', {'q': '*:*', 'sort': 'citeCount asc'})
        self.assertTrue(response.content.index('Disclosure') > response.content.index('Tarrant'),
                        msg="'Disclosure' should come AFTER 'Tarrant' when ordered by ascending citeCount.")

class PagerankTest(TestCase):
    fixtures = ['test_court.json']

    def test_pagerank_calculation(self):
        """Create a few Documents and fake citation relation among them, then run the pagerank
        algorithm. Check whether this simple case can get the correct result.
        """
        # Set up some handy variables
        self.court = Court.objects.get(pk='test')

        #create 3 documents with their citations
        c1, c2, c3 = Citation(case_name="c1"), Citation(case_name="c2"), Citation(case_name="c3")
        c1.save(index=False)
        c2.save(index=False)
        c3.save(index=False)
        d1, d2, d3 = Document(), Document(), Document()
        d1.citation, d2.citation, d3.citation = c1, c2, c3
        doc_list = [d1, d2, d3]
        for d in doc_list:
            d.court = self.court
            d.citation.save(index=False)
            d.save(index=False)

        #create simple citing relation: 1 cites 2; 2 cites 3; 3 cites 1; 1 cites 3
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
        comm.do_pagerank()
        d1, d2, d3 = Document.objects.get(pk=d1.pk), Document.objects.get(pk=d2.pk), Document.objects.get(pk=d3.pk)
        doc_list = [d1, d2, d3]

        #verify that whether the answer is correct
        ANS_LIST=[1.16336, 0.64443, 1.19219]
        result = True
        for i in range(3):
            result *= abs(doc_list[i].pagerank - ANS_LIST[i]) / ANS_LIST[i] < 0.0001
        self.assertEqual(
            result,
            1,
            msg="The pagerank calculation is wrong.\n" +
                "The answer 1 is {:f}\tYour answer 1 is {:f}\n".format(ANS_LIST[0], doc_list[0].pagerank) +
                "The answer 2 is {:f}\tYour answer 2 is {:f}\n".format(ANS_LIST[1], doc_list[1].pagerank) +
                "The answer 3 is {:f}\tYour answer 3 is {:f}\n".format(ANS_LIST[2], doc_list[2].pagerank)
        )