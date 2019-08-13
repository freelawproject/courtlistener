"""
Base class(es) for functional testing CourtListener using Selenium and PhantomJS
"""
import os
import socket
from contextlib import contextmanager

import scorched
from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test.utils import override_settings
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import staleness_of

from cl.audio.models import Audio
from cl.search.models import Opinion
from cl.search.tasks import add_items_to_solr

SELENIUM_TIMEOUT = 120
if 'SELENIUM_TIMEOUT' in os.environ:
    try:
        SELENIUM_TIMEOUT = int(os.environ['SELENIUM_TIMEOUT'])
    except ValueError:
        pass

@override_settings(
    SOLR_OPINION_URL=settings.SOLR_OPINION_TEST_URL,
    SOLR_AUDIO_URL=settings.SOLR_AUDIO_TEST_URL,
    SOLR_URLS=settings.SOLR_TEST_URLS,
)
class BaseSeleniumTest(StaticLiveServerTestCase):
    """Base class for Selenium Tests. Sets up a few attributes:
      * browser - instance of Selenium WebDriver
      * screenshot - boolean for if the test should save a final screenshot
      * Also sets window size to default of 1024x768.
      * Binds the host to 0.0.0.0 to allow external access.

    See this URL for notes: https://marcgibbons.com/post/selenium-in-docker/
    """
    host = '0.0.0.0'

    @staticmethod
    def _create_browser():
        options = webdriver.ChromeOptions()
        if settings.SELENIUM_HEADLESS is True:
            options.add_argument('headless')
        options.add_argument("silent")
        options.add_experimental_option('w3c', False)

        if settings.DOCKER_SELENIUM_HOST:
            capabilities = options.to_capabilities()
            return webdriver.Remote(settings.DOCKER_SELENIUM_HOST,
                                    desired_capabilities=capabilities)
        return webdriver.Chrome(chrome_options=options)

    @classmethod
    def setUpClass(cls):
        super(BaseSeleniumTest, cls).setUpClass()

        if 'SELENIUM_DEBUG' in os.environ:
            cls.screenshot = True
        else:
            cls.screenshot = False

        # Set host to externally accessible web server address
        cls.host = socket.gethostbyname(socket.gethostname())

    def setUp(self):
        self.reset_browser()
        self._update_index()

    def reset_browser(self):
        try:
            self.browser.quit()
        except AttributeError:
            # it's ok we forgive you http://stackoverflow.com/a/610923
            pass
        finally:
            self.browser = self._create_browser()

        self.browser.implicitly_wait(15)

    def tearDown(self):
        if self.screenshot:
            filename = type(self).__name__ + '.png'
            print('\nSaving screenshot: %s' % (filename,))
            self.browser.save_screenshot('/tmp/' + filename)
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
    def wait_for_page_load(self, timeout=30):
        old_page = self.browser.find_element_by_tag_name('html')
        yield
        WebDriverWait(self.browser, timeout).until(staleness_of(old_page))

    def click_link_for_new_page(self, link_text, timeout=30):
        with self.wait_for_page_load(timeout=timeout):
            self.browser.find_element_by_link_text(link_text).click()

    def attempt_sign_in(self, username, password):
        self.click_link_for_new_page('Sign in / Register')
        self.assertIn('Sign In', self.browser.title)
        self.browser.find_element_by_id('username').send_keys(username)
        self.browser.find_element_by_id('password').send_keys(password + '\n')
        self.assertTrue(self.extract_result_count_from_serp() > 0)

    def get_url_and_wait(self, url, timeout=30):
        self.browser.get(url)
        wait = WebDriverWait(self.browser, timeout)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, 'html')))

    def extract_result_count_from_serp(self):
        results = self.browser.find_element_by_id('result-count').text.strip()
        try:
            count = long(results.split(' ')[0].replace(',', ''))
        except (IndexError, ValueError):
            self.fail('Cannot extract result count from SERP.')
        return count

    @staticmethod
    def _update_index():
        # For now, until some model/api issues are worked out for Audio
        # objects, we'll avoid using the cl_update_index command and do
        # this the hard way using tasks
        opinion_keys = Opinion.objects.values_list('pk', flat=True)
        add_items_to_solr(opinion_keys, 'search.Opinion', force_commit=True)
        audio_keys = Audio.objects.values_list('pk', flat=True)
        add_items_to_solr(audio_keys, 'audio.Audio', force_commit=True)

    @staticmethod
    def _teardown_test_solr():
        """Empty out the test cores that we use"""
        conns = [settings.SOLR_OPINION_TEST_URL,
                 settings.SOLR_AUDIO_TEST_URL]
        for conn in conns:
            si = scorched.SolrInterface(conn, mode='rw')
            si.delete_all()
            si.commit()
