import os
from cl.lib import sunburnt
from cl.lib.solr_core_admin import (
    create_solr_core, swap_solr_core, delete_solr_core
)
from cl.search.models import Court
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from lxml import etree

core_name_opinion = 'opinion_test'
core_name_audio = 'audio_test'

@override_settings(
    SOLR_OPINION_URL='http://127.0.0.1:8983/solr/%s' % core_name_opinion,
    SOLR_AUDIO_URL='http://127.0.0.1:8983/solr/%s' % core_name_audio,
)
class EmptySolrTestCase(TestCase):
    """Sets up an empty Solr index for tests that need to set up data manually.

    Other Solr test classes subclass this one, adding additional content or
    features.
    """

    def setUp(self):
        # Set up testing cores in Solr and swap them in
        self.core_name_opinion = core_name_opinion
        self.core_name_audio = core_name_audio
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

        self.si_opinion.commit()
        self.si_audio.commit()

    def tearDown(self):
        swap_solr_core(self.core_name_opinion, 'collection1')
        swap_solr_core(self.core_name_audio, 'audio')
        delete_solr_core(self.core_name_opinion)
        delete_solr_core(self.core_name_audio)


class SolrTestCase(EmptySolrTestCase):
    """A standard Solr test case with content included in the database,  but not
    yet indexed into the database.
    """
    fixtures = ['test_court.json', 'judge_judy.json',
                'test_objects_search.json', 'test_objects_audio.json']

    def setUp(self):
        # Set up some handy variables
        super(SolrTestCase, self).setUp()

        self.court = Court.objects.get(pk='test')
        self.expected_num_results_opinion = 3
        self.expected_num_results_audio = 2


class IndexedSolrTestCase(SolrTestCase):
    """Similar to the SolrTestCase, but the data is indexed in Solr"""

    def setUp(self):
        super(IndexedSolrTestCase, self).setUp()

        for obj_type, core_name in {
            'audio': self.core_name_audio,
            'opinions': self.core_name_opinion,
        }.items():
            args = [
                '--type', obj_type,
                '--solr-url', 'http://127.0.0.1:8983/solr/%s' % core_name,
                '--update',
                '--everything',
                '--do-commit',
                '--noinput',
            ]
            call_command('cl_update_index', *args)


class SitemapTest(IndexedSolrTestCase):
    def __init__(self, *args, **kwargs):
        super(SitemapTest, self).__init__(*args, ** kwargs)
        self.expected_item_count = None
        self.sitemap_url = None

    def does_the_sitemap_have_content(self):
        """Does content get into the sitemap?"""
        response = self.client.get(self.sitemap_url)
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        node_count = len(xml_tree.xpath(
            '//s:url',
            namespaces={'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'},
        ))
        self.assertEqual(
            node_count,
            self.expected_item_count,
            msg="Did not get the right number of items in the sitemap.\n"
                "\tCounted:\t%s\n"
                "\tExpected:\t%s" % (node_count, self.expected_item_count)
        )
