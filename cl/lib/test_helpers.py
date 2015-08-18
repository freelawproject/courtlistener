import os
from django.core.management import call_command
from cl.lib import sunburnt
from cl.lib.solr_core_admin import (
    create_solr_core, swap_solr_core, delete_solr_core
)
from cl.search.models import Court
from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings

core_name_opinion = 'opinion_test'
core_name_audio = 'audio_test'

@override_settings(
    SOLR_OPINION_URL='http://127.0.0.1:8983/solr/%s' % core_name_opinion,
    SOLR_AUDIO_URL='http://127.0.0.1:8983/solr/%s' % core_name_audio,
)
class SolrTestCase(TestCase):
    """A generic class that contains the setUp and tearDown functions for
    inheriting children.

    Good for tests with both audio and documents.
    """
    fixtures = ['test_court.json', 'judge_judy.json',
                'test_objects_search.json', 'test_objects_audio.json']

    def setUp(self):
        # Set up some handy variables
        self.court = Court.objects.get(pk='test')

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

        self.expected_num_results_opinion = 3
        self.expected_num_results_audio = 2
        self.si_opinion.commit()
        self.si_audio.commit()

    def tearDown(self):
        swap_solr_core(self.core_name_opinion, 'collection1')
        swap_solr_core(self.core_name_audio, 'audio')
        delete_solr_core(self.core_name_opinion)
        delete_solr_core(self.core_name_audio)


class IndexedSolrTestCase(SolrTestCase):
    """Similar to the above test case, but the data is indexed in Solr"""

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

