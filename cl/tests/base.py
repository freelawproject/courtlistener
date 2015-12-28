"""
Base class(es) for functional testing CourtListener using Selenium and PhantomJS
"""
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test.utils import override_settings
from selenium import webdriver
from cl.lib.solr_core_admin import (
    create_solr_core, swap_solr_core, delete_solr_core
)
from cl.search.tasks import add_or_update_opinions, add_or_update_audio_files
from cl.search.models import Opinion
from cl.audio.models import Audio
import os, sys

DESKTOP_WINDOW = (1024, 768)
MOBILE_WINDOW = (640, 960)

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

    @classmethod
    def tearDownClass(cls):
        if cls.server_url == cls.live_server_url:
            super(BaseSeleniumTest, cls).tearDownClass()

    def setUp(self):
        self.browser = webdriver.PhantomJS(
            executable_path='/usr/local/phantomjs/phantomjs',
            service_log_path='/var/log/courtlistener/django.log',
        )
        self.browser.implicitly_wait(3)
        self.browser.set_window_size(DESKTOP_WINDOW[0], DESKTOP_WINDOW[1])
        self._initialize_test_solr()
        self._update_index()

    def tearDown(self):
        if self.screenshot:
            filename = type(self).__name__ + '.png'
            print '\nSaving screenshot: %s' % (filename,)
            self.browser.save_screenshot(type(self).__name__ + '.png')
        self.browser.quit()
        self._teardown_test_solr()

    def assert_text_in_body(self, text):
        self.assertIn(text, self.browser.find_element_by_tag_name('body').text)

    def assert_text_not_in_body(self, text):
        self.assertNotIn(
            text,
            self.browser.find_element_by_tag_name('body').text
        )

    def attempt_sign_in(self, username, password):
        signin = self.browser.find_element_by_link_text('Sign in / Register')
        signin.click()
        self.assertIn('Sign In', self.browser.title)
        self.browser.find_element_by_id('username').send_keys(username)
        self.browser.find_element_by_id('password').send_keys(password + '\n')
        self.assertTrue(self.extract_result_count_from_serp() > 0)

    def extract_result_count_from_serp(self):
        results = self.browser.find_element_by_id('result-count').text.strip()
        try:
            count = long(results.split(' ')[0].replace(',', ''))
        except IndexError, ValueError:
            self.fail('Cannot extract result count from SERP.')
        return count

    @staticmethod
    def _initialize_test_solr():
        """ Try to initialize a pair of Solr cores for testing purposes """

        # data_dir, if left blank, ends up bing put in /tmp/solr/...
        create_solr_core(
            TEST_OPINION_CORE,
            data_dir=os.path.join(settings.INSTALL_ROOT, 'Solr',
                'data_opinion_test'),
            schema='schema.xml',
            config='solrconfig.xml',
            instance_dir='/usr/local/solr/example/solr/opinion_test')
        create_solr_core(
            TEST_AUDIO_CORE,
            data_dir=os.path.join(settings.INSTALL_ROOT, 'Solr',
                'data_audio_test'),
            schema='schema.xml',
            config='solrconfig.xml',
            instance_dir='/usr/local/solr/example/solr/audio_test',
        )

    @staticmethod
    def _update_index():
        # For now, until some model/api issues are worked out for Audio
        # objects, we'll avoid using the cl_update_index command and do
        # this the hard way using tasks
        opinion_keys = Opinion.objects.values_list('pk', flat=True)
        add_or_update_opinions(opinion_keys)
        audio_keys = Audio.objects.values_list('pk', flat=True)
        add_or_update_audio_files(audio_keys)

    @staticmethod
    def _teardown_test_solr():
        """ Try to clean up and remove the test Solr cores """
        delete_solr_core(TEST_OPINION_CORE, delete_data_dir=True)
        delete_solr_core(TEST_AUDIO_CORE, delete_data_dir=True)
