import os

import scorched
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from lxml import etree

from cl.lib import sunburnt
from cl.lib.solr_core_admin import delete_solr_core, create_temp_solr_core
from cl.search.models import Court


@override_settings(
    SOLR_OPINION_URL=settings.SOLR_OPINION_TEST_URL,
    SOLR_AUDIO_URL=settings.SOLR_AUDIO_TEST_URL,
    SOLR_PEOPLE_URL=settings.SOLR_PEOPLE_TEST_URL,
    SOLR_RECAP_URL=settings.SOLR_RECAP_TEST_URL,
    SOLR_URLS=settings.SOLR_TEST_URLS,
)
class EmptySolrTestCase(TestCase):
    """Sets up an empty Solr index for tests that need to set up data manually.

    Other Solr test classes subclass this one, adding additional content or
    features.
    """

    def setUp(self):
        # Set up testing cores in Solr and swap them in
        self.core_name_opinion = settings.SOLR_OPINION_TEST_CORE_NAME
        self.core_name_audio = settings.SOLR_AUDIO_TEST_CORE_NAME
        self.core_name_people = settings.SOLR_PEOPLE_TEST_CORE_NAME
        self.core_name_recap = settings.SOLR_RECAP_TEST_CORE_NAME
        root = settings.INSTALL_ROOT
        create_temp_solr_core(
            self.core_name_opinion,
            os.path.join(root, 'Solr', 'conf', 'schema.xml'),
        )
        create_temp_solr_core(
            self.core_name_audio,
            os.path.join(root, 'Solr', 'conf', 'audio_schema.xml'),
        )
        create_temp_solr_core(
            self.core_name_people,
            os.path.join(root, 'Solr', 'conf', 'person_schema.xml'),
        )
        create_temp_solr_core(
            self.core_name_recap,
            os.path.join(root, 'Solr', 'conf', 'recap_schema.xml')
        )
        self.si_opinion = sunburnt.SolrInterface(
            settings.SOLR_OPINION_URL, mode='rw')
        self.si_audio = sunburnt.SolrInterface(
            settings.SOLR_AUDIO_URL, mode='rw')
        self.si_people = sunburnt.SolrInterface(
            settings.SOLR_PEOPLE_URL, mode='rw')
        # This will cause headaches, but it follows in the mission to slowly
        # migrate off of sunburnt. This was added after the items above, and so
        # uses scorched, not sunburnt.
        self.si_recap = scorched.SolrInterface(
            settings.SOLR_RECAP_URL, mode='rw')

    def tearDown(self):
        delete_solr_core(self.core_name_opinion)
        delete_solr_core(self.core_name_audio)
        delete_solr_core(self.core_name_people)
        delete_solr_core(self.core_name_recap)


class SolrTestCase(EmptySolrTestCase):
    """A standard Solr test case with content included in the database,  but not
    yet indexed into the database.
    """
    fixtures = ['test_court.json', 'judge_judy.json',
                'test_objects_search.json', 'test_objects_audio.json',
                'authtest_data.json']

    def setUp(self):
        # Set up some handy variables
        super(SolrTestCase, self).setUp()

        self.court = Court.objects.get(pk='test')
        self.expected_num_results_opinion = 6
        self.expected_num_results_audio = 2


class IndexedSolrTestCase(SolrTestCase):
    """Similar to the SolrTestCase, but the data is indexed in Solr"""

    def setUp(self):
        super(IndexedSolrTestCase, self).setUp()
        cores = {
            'audio': self.core_name_audio,
            'opinions': self.core_name_opinion,
            'person': self.core_name_people,
        }
        for obj_type, core_name in cores.items():
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
