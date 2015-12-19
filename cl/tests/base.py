"""
Base class(es) for functional testing CourtListener using Selenium and PhantomJS
"""
from django.conf import settings
from django.core.management import call_command
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test.utils import override_settings
from selenium import webdriver
from cl.lib import sunburnt
from cl.lib.solr_core_admin import (
    create_solr_core, swap_solr_core, delete_solr_core
)
import os, sys, requests

DESKTOP_WINDOW = (1024, 768)
MOBILE_WINDOW = (500, 600)

TEST_OPINION_CORE = 'opinion_test'
TEST_AUDIO_CORE = 'audio_test'

@override_settings(
    SOLR_OPINION_URL='http://127.0.0.1:8983/solr/%s' % TEST_OPINION_CORE,
    SOLR_AUDIO_URL='http://127.0.0.1:8983/solr/%s' % TEST_AUDIO_CORE,
)
class BaseSeleniumTest(StaticLiveServerTestCase):
    """Base class for Selenium Tests. Sets up a few attributes:
        * server_url - either from a sys argument for liveserver or
            the default from the LiveServerTestCase
        * browser - instance of PhantomJS Selenium WebDriver
        * screenshot - boolean for if the test should save a final screenshot
        Also sets window size to default of 1024x768.
    """

    @classmethod
    def setUpClass(cls):
        cls.screenshot = False
        for arg in sys.argv:
            if 'liveserver' in arg:
                cls.server_url = 'http://' + arg.split('=')[1]
                return
        super(BaseSeleniumTest, cls).setUpClass()
        cls.server_url = cls.live_server_url
        cls._initialize_test_solr()

    @classmethod
    def tearDownClass(cls):
        if cls.server_url == cls.live_server_url:
            super(BaseSeleniumTest, cls).tearDownClass()
        cls._teardown_test_solr()

    def setUp(self):
        self.browser = webdriver.PhantomJS(
            executable_path='/usr/local/phantomjs/phantomjs',
            service_log_path='/var/log/courtlistener/django.log',
        )
        self.browser.implicitly_wait(1)
        self.browser.set_window_size(DESKTOP_WINDOW[0], DESKTOP_WINDOW[1])
        self._update_index()

    def tearDown(self):
        if self.screenshot:
            print '\nSaving screenshot...'
            self.browser.save_screenshot(type(self).__name__ + '.png')
        self.browser.quit()

    def assert_text_in_body(self, text):
        self.assertIn(text, self.browser.find_element_by_tag_name('body').text)

    @staticmethod
    def _initialize_test_solr():
        """ Try to initialize a pair of Solr cores for testing purposes """

        print '>> initializing test solr cores...'
        create_solr_core(TEST_OPINION_CORE)
        create_solr_core(
            TEST_AUDIO_CORE,
            schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                                'audio_schema.xml'),
            instance_dir='/usr/local/solr/example/solr/audio',
        )
        swap_solr_core('collection1', TEST_OPINION_CORE)
        swap_solr_core('audio', TEST_AUDIO_CORE)

    @staticmethod
    def _update_index():
        print '>> Trying to run cl_update_index...'
        for obj_type, core_name in {
            'audio': TEST_AUDIO_CORE,
            'opinions': TEST_OPINION_CORE,
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


    @staticmethod
    def _teardown_test_solr():
        """ Try to clean up and remove the test Solr cores """
        print '>> destroying test solr cores...'
        swap_solr_core(TEST_OPINION_CORE, 'collection1')
        swap_solr_core(TEST_AUDIO_CORE, 'audio')
        delete_solr_core(TEST_OPINION_CORE)
        delete_solr_core(TEST_AUDIO_CORE)


class SolrBackendTest(BaseSeleniumTest):

    fixtures = ['test_court.json', 'judge_judy.json',
                'test_objects_search.json', 'test_objects_audio.json',
                'authtest_data.json']

    def test_solr_initialized_with_opinions(self):
        """Our base test class should spin up a Solr core with Opinions"""
        r = requests.get('http://localhost:8983/solr/opinion_test/query',
            params={'q':'lissner'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('Lissner v. Saad', r.text)
