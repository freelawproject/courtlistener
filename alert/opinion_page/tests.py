from alert.search.models import Citation, Court, Document, Docket
from alert.scrapers.test_assets import test_opinion_scraper
from django.test import TestCase
from django.test.client import Client


class ViewDocumentTest(TestCase):
    fixtures = ['test_court.json']

    def setUp(self):
        # Set up some handy variables
        self.court = Court.objects.get(pk='test')
        self.client = Client()

        # Add a document to the index
        site = test_opinion_scraper.Site().parse()
        cite = Citation(
            docket_number=site.docket_numbers[0],
            neutral_cite=site.neutral_citations[0],
            federal_cite_one=site.west_citations[0]
        )
        cite.save(index=False)
        docket = Docket(
            court=self.court,
            case_name=site.case_names[0],
        )
        docket.save()
        self.doc = Document(
            date_filed=site.case_dates[0],
            citation=cite,
            docket=docket,
            precedential_status=site.precedential_statuses[0],
        )
        self.doc.save(index=False)

    def tearDown(self):
        self.doc.delete()

    def test_simple_url_check_for_document(self):
        """Does the page load properly?"""
        response = self.client.get('/opinion/1/asdf/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Tarrant', response.content)
