import os
import time

from django.conf import settings
from django.test import TestCase
from lxml import etree

from alert.lib import sunburnt
from alert.lib.solr_core_admin import create_solr_core, swap_solr_core, \
    delete_solr_core
from alert.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgCommand
from audio.models import Audio
from scrapers.test_assets import test_oral_arg_scraper


class PodcastTest(TestCase):
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

    def test_do_podcasts_have_good_content(self):
        """Can we simply load the podcast page?"""
        response = self.client.get('/podcast/court/test/')
        self.assertEqual(200, response.status_code,
                         msg="Did not get 200 OK status code for podcasts.")
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ('//channel/title', 1),
            ('//channel/link', 1),
            ('//channel/description', 1),
            ('//channel/item', 2),
            ('//channel/item/title', 2),
            ('//channel/item/enclosure/@url', 2),
        )
        for test, count in node_tests:
            node_count = len(xml_tree.xpath(test))
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s\n"
                    "Instead found: %s" % (count, test, node_count)
            )
