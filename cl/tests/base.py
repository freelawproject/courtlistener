"""
Base class(es) for functional testing CourtListener using Selenium and PhantomJS
"""
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium import webdriver
import sys

DESKTOP_WINDOW = (1024, 768)
MOBILE_WINDOW = (500, 600)

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

    def tearDown(self):
        if self.screenshot:
            print '\nSaving screenshot...'
            self.browser.save_screenshot(type(self).__name__ + '.png')
        self.browser.quit()


    def assert_text_in_body(self, text):
        self.assertIn(text, self.browser.find_element_by_tag_name('body').text)
