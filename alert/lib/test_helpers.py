import os
import time
from django.test import TestCase
from alert.audio.models import Audio
from alert.lib import sunburnt
from alert.lib.solr_core_admin import create_solr_core, swap_solr_core, \
    delete_solr_core
from alert.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgCommand
from alert.scrapers.test_assets import test_opinion_scraper, \
    test_oral_arg_scraper
from alert.search.models import Court, Citation, Docket, Document
from django.conf import settings


class SolrOpinionTestCase(TestCase):
    """A generic class that contains the setUp and tearDown functions for
    inheriting children.
    """
    fixtures = ['test_court.json']

    def setUp(self):
        # Set up some handy variables
        self.court = Court.objects.get(pk='test')

        # Set up a testing core in Solr and swap it in
        self.core_name = '%s.test-%s' % (self.__module__, time.time())
        create_solr_core(self.core_name)
        swap_solr_core('collection1', self.core_name)
        self.si = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='rw')

        # Add two documents to the index, but don't extract their contents
        self.site = test_opinion_scraper.Site().parse()
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


class SolrAudioTestCase(TestCase):
    fixtures = ['test_court.json']

    def setUp(self):
        # Create Solr cores for audio and swap it in
        self.core_name = '%s.test-%s' % (self.__module__, time.time())
        create_solr_core(
            self.core_name,
            schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                                'audio_schema.xml'),
            instance_dir='/usr/local/solr/example/solr/audio',
        )
        swap_solr_core('audio', self.core_name)
        self.si = sunburnt.SolrInterface(settings.SOLR_AUDIO_URL, mode='rw')

        # Uses the scraper framework to add a few items to the DB.
        site = test_oral_arg_scraper.Site()
        site.method = "LOCAL"
        parsed_site = site.parse()
        OralArgCommand().scrape_court(parsed_site, full_crawl=True)

    def tearDown(self):
        Audio.objects.all().delete()
        swap_solr_core(self.core_name, 'audio')
        delete_solr_core(self.core_name)
