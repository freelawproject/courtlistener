"""
Base class(es) for functional testing CourtListener using Selenium and PhantomJS
"""
import os
import sys

from contextlib import contextmanager

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test.utils import override_settings
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import staleness_of

from cl.audio.models import Audio
from cl.lib.solr_core_admin import create_temp_solr_core, delete_solr_core
from cl.search.models import Opinion
from cl.search.tasks import add_or_update_opinions, add_or_update_audio_files

PHANTOMJS_TIMEOUT = 45
if 'PHANTOMJS_TIMEOUT' in os.environ:
    try:
        PHANTOMJS_TIMEOUT = int(os.environ['PHANTOMJS_TIMEOUT'])
    except ValueError:
        pass

DESKTOP_WINDOW = (1024, 768)
MOBILE_WINDOW = (500, 120)


@override_settings(
    SOLR_OPINION_URL=settings.SOLR_OPINION_TEST_URL,
    SOLR_AUDIO_URL=settings.SOLR_AUDIO_TEST_URL,
)
class BaseSeleniumTest(StaticLiveServerTestCase):
    """Base class for Selenium Tests. Sets up a few attributes:
        * server_url - either from a sys argument for liveserver or
            the default from the LiveServerTestCase
        * browser - instance of PhantomJS Selenium WebDriver
        * screenshot - boolean for if the test should save a final screenshot
        Also sets window size to default of 1024x768.
    """

    driverClass = webdriver.Remote

    @classmethod
    def setUpClass(cls):
        if 'SELENIUM_DEBUG' in os.environ:
            cls.screenshot = True
        else:
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
        self.resetBrowser()
        self._initialize_test_solr()
        self._update_index()

    def resetBrowser(self, window_width=DESKTOP_WINDOW[0], window_height=DESKTOP_WINDOW[1]):
        try:
            self.browser.quit()
        except AttributeError:
            # it's ok we forgive you http://stackoverflow.com/a/610923
            pass
        finally:
            options = webdriver.ChromeOptions()
            options.add_argument('window-size=%s,%s' % (window_width, window_height))
            self.browser = self.driverClass('http://10.0.2.2:9515', options.to_capabilities())

        self.browser.implicitly_wait(10)

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

    # See http://www.obeythetestinggoat.com/how-to-get-selenium-to-wait-for-page-load-after-a-click.html
    @contextmanager
    def wait_for_page_load(self, timeout=10):
        old_page = self.browser.find_element_by_tag_name('html')
        yield
        WebDriverWait(self.browser, timeout).until(staleness_of(old_page))

    def click_link_for_new_page(self, link_text, timeout=10):
        with self.wait_for_page_load(timeout=timeout):
            self.browser.find_element_by_link_text(link_text).click()

    def attempt_sign_in(self, username, password):
        self.click_link_for_new_page('Sign in / Register')
        self.assertIn('Sign In', self.browser.title)
        self.browser.find_element_by_id('username').send_keys(username)
        self.browser.find_element_by_id('password').send_keys(password + '\n')
        self.assertTrue(self.extract_result_count_from_serp() > 0)

    def extract_result_count_from_serp(self):
        results = self.browser.find_element_by_id('result-count').text.strip()
        try:
            count = long(results.split(' ')[0].replace(',', ''))
        except (IndexError, ValueError):
            self.fail('Cannot extract result count from SERP.')
        return count

    @staticmethod
    def _initialize_test_solr():
        """ Try to initialize a pair of Solr cores for testing purposes """
        root = settings.INSTALL_ROOT
        create_temp_solr_core(
            settings.SOLR_OPINION_TEST_CORE_NAME,
            os.path.join(root, 'Solr', 'conf', 'schema.xml'),
        )
        create_temp_solr_core(
            settings.SOLR_AUDIO_TEST_CORE_NAME,
            os.path.join(root, 'Solr', 'conf', 'audio_schema.xml'),
        )

    @staticmethod
    def _update_index():
        # For now, until some model/api issues are worked out for Audio
        # objects, we'll avoid using the cl_update_index command and do
        # this the hard way using tasks
        opinion_keys = Opinion.objects.values_list('pk', flat=True)
        add_or_update_opinions(opinion_keys, force_commit=True)
        audio_keys = Audio.objects.values_list('pk', flat=True)
        add_or_update_audio_files(audio_keys, force_commit=True)

    @staticmethod
    def _teardown_test_solr():
        """ Try to clean up and remove the test Solr cores """
        delete_solr_core(settings.SOLR_OPINION_TEST_CORE_NAME)
        delete_solr_core(settings.SOLR_AUDIO_TEST_CORE_NAME)
