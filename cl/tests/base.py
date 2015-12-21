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
from cl.search.tasks import add_or_update_opinions
from cl.search.models import Opinion
from cl.audio.models import Audio
import os, sys

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

    @classmethod
    def tearDownClass(cls):
        if cls.server_url == cls.live_server_url:
            super(BaseSeleniumTest, cls).tearDownClass()

    def setUp(self):
        self.browser = webdriver.PhantomJS(
            executable_path='/usr/local/phantomjs/phantomjs',
            service_log_path='/var/log/courtlistener/django.log',
        )
        self.browser.implicitly_wait(1)
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

    @staticmethod
    def _initialize_test_solr():
        """ Try to initialize a pair of Solr cores for testing purposes """

        # data_dir, if left blank, ends up bing put in /tmp/solr/...
        create_solr_core(
            TEST_OPINION_CORE,
            data_dir=os.path.join(settings.INSTALL_ROOT, 'Solr',
                'data_opinion_test'),
            schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                                'schema.xml'),
            instance_dir='/usr/local/solr/example/solr/opinion_test')
        create_solr_core(
            TEST_AUDIO_CORE,
            data_dir=os.path.join(settings.INSTALL_ROOT, 'Solr',
                'data_audio_test'),
            schema=os.path.join(settings.INSTALL_ROOT, 'Solr', 'conf',
                                'audio_schema.xml'),
            instance_dir='/usr/local/solr/example/solr/audio_test',
        )

    @staticmethod
    def _update_index():
        # For now, until some model/api issues are worked out for Audio
        # objects, we'll avoid using the cl_update_index command and do
        # this the hard way using tasks
        keys = [opinion.pk for opinion in Opinion.objects.all()]
        add_or_update_opinions(keys)



    @staticmethod
    def _teardown_test_solr():
        """ Try to clean up and remove the test Solr cores """
        delete_solr_core(TEST_OPINION_CORE)
        delete_solr_core(TEST_AUDIO_CORE)
