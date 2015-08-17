import os
import time
from cl.audio.models import Audio
from cl.lib import sunburnt
from cl.lib.solr_core_admin import (
    create_solr_core, swap_solr_core, delete_solr_core
)
from cl.scrapers.management.commands.cl_scrape_oral_arguments import Command
from cl.scrapers.test_assets import test_oral_arg_scraper
from cl.search.models import Court
from django.conf import settings
from django.test import TestCase


class SolrTestCase(TestCase):
    """A generic class that contains the setUp and tearDown functions for
    inheriting children.

    Good for tests with both audio and documents.
    """
    fixtures = ['test_court.json', 'judge_judy.json', 'test_objects.json']

    def setUp(self):
        # Set up some handy variables
        self.court = Court.objects.get(pk='test')

        # Set up testing cores in Solr and swap them in
        self.core_name_opinion = '%s.opinion-test-%s' % \
                                 (self.__module__, time.time())
        self.core_name_audio = '%s.audio-test-%s' % \
                               (self.__module__, time.time())
        create_solr_core(self.core_name_opinion)
        create_solr_core(
            self.core_name_audio,
            schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                                'audio_schema.xml'),
            instance_dir='/usr/local/solr/example/solr/audio',
        )
        swap_solr_core('collection1', self.core_name_opinion)
        swap_solr_core('audio', self.core_name_audio)
        self.si_opinion = sunburnt.SolrInterface(
            settings.SOLR_OPINION_URL, mode='rw')
        self.si_audio = sunburnt.SolrInterface(
            settings.SOLR_AUDIO_URL, mode='rw')

        #TODO: Get this added back.
        # Scrape the audio "site" and add its contents
        # self.site_audio = test_oral_arg_scraper.Site().parse()
        # Command().scrape_court(self.site_audio, full_crawl=True)

        self.expected_num_results_opinion = 3
        self.expected_num_results_audio = 2
        self.si_opinion.commit()
        self.si_audio.commit()

    def tearDown(self):
        Audio.objects.all().delete()
        swap_solr_core(self.core_name_opinion, 'collection1')
        swap_solr_core(self.core_name_audio, 'audio')
        delete_solr_core(self.core_name_opinion)
        delete_solr_core(self.core_name_audio)
