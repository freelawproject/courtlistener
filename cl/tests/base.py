"""
Base class(es) for functional testing CourtListener using Selenium and PhantomJS
"""
import os
import socket
from contextlib import contextmanager

import scorched
from django.conf import settings
from django.test.utils import override_settings, tag
from requests import Session
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.expected_conditions import staleness_of
from selenium.webdriver.support.ui import WebDriverWait
from timeout_decorator import TimeoutError

from cl.audio.models import Audio
from cl.lib.decorators import retry
from cl.lib.test_helpers import SerializeSolrTestMixin
from cl.search.models import Opinion
from cl.search.tasks import add_items_to_solr
from cl.tests.cases import StaticLiveServerTestCase

SELENIUM_TIMEOUT = 120
if "SELENIUM_TIMEOUT" in os.environ:
    try:
        SELENIUM_TIMEOUT = int(os.environ["SELENIUM_TIMEOUT"])
    except ValueError:
        pass


@tag("selenium")
@override_settings(
    SOLR_OPINION_URL=settings.SOLR_OPINION_TEST_URL,
    SOLR_AUDIO_URL=settings.SOLR_AUDIO_TEST_URL,
    SOLR_URLS=settings.SOLR_TEST_URLS,
    ALLOWED_HOSTS=["*"],
)
class BaseSeleniumTest(SerializeSolrTestMixin, StaticLiveServerTestCase):
    """Base class for Selenium Tests. Sets up a few attributes:
      * browser - instance of Selenium WebDriver
      * screenshot - boolean for if the test should save a final screenshot
      * Also sets window size to default of 1024x768.
      * Binds the host to 0.0.0.0 to allow external access.

    See this URL for notes: https://marcgibbons.com/post/selenium-in-docker/
    """

    host = "0.0.0.0"

    @staticmethod
    def _create_browser() -> webdriver.Chrome:
        options = webdriver.ChromeOptions()
        if settings.SELENIUM_HEADLESS is True:
            options.add_argument("headless")
        options.add_argument("silent")
        options.add_experimental_option("w3c", False)

        # Workaround for
        # https://bugs.chromium.org/p/chromium/issues/detail?id=1033941
        options.add_argument(
            "--disable-features=AvoidFlashBetweenNavigation,PaintHolding"
        )

        if settings.DOCKER_SELENIUM_HOST:
            capabilities = options.to_capabilities()
            return webdriver.Remote(
                settings.DOCKER_SELENIUM_HOST,
                desired_capabilities=capabilities,
                keep_alive=True,
            )
        return webdriver.Chrome(chrome_options=options, keep_alive=True)

    @classmethod
    def setUpClass(cls) -> None:
        super(BaseSeleniumTest, cls).setUpClass()

        if "SELENIUM_DEBUG" in os.environ:
            cls.screenshot = True
        else:
            cls.screenshot = False

        # Set host to externally accessible web server address
        cls.host = socket.gethostbyname(socket.gethostname())

        cls.browser = cls._create_browser()
        cls.browser.implicitly_wait(5)

    def setUp(self) -> None:
        self.reset_browser()
        self._update_index()

    def reset_browser(self) -> None:
        self.browser.delete_all_cookies()

    def tearDown(self) -> None:
        if self.screenshot:
            filename = f"{type(self).__name__}-selenium.png"
            print(f"\nSaving screenshot in docker image at: /tmp/{filename}")
            self.browser.save_screenshot(f"/tmp/{filename}")
        self._teardown_test_solr()

    @classmethod
    def tearDownClass(cls) -> None:
        super(BaseSeleniumTest, cls).tearDownClass()

        cls.browser.quit()

    @retry(AssertionError, tries=3, delay=0.25, backoff=1)
    def assert_text_in_node(self, text: str, tag_name: str) -> None:
        """Is the text in a given node?

        :param text: The text you want to look for
        :param tag_name: The node in the HTML you want to check
        :raises: AssertionError if the text cannot be found
        :returns None
        """
        node = self.browser.find_element(By.TAG_NAME, tag_name)
        self.assertIn(text, node.text)

    @retry(AssertionError, tries=3, delay=0.25, backoff=1)
    def assert_text_not_in_node(self, text: str, tag_name: str) -> None:
        """Assert that text is not in a node by name

        :param text: The text you want not to appear
        :param tag_name: The node in your HTML you want to check
        :raises: AssertionError if the text is NOT in the node
        :return: None
        """
        node = self.browser.find_element(By.TAG_NAME, tag_name)
        self.assertNotIn(text, node.text)

    @retry(AssertionError, tries=3, delay=0.25, backoff=1)
    def assert_text_in_node_by_id(self, text: str, tag_id: str) -> None:
        """Is the text in a node selected by ID?

        :param text: The text you want to look for
        :param tag_id: The ID of the node in the HTML you want to check
        :raises: AssertionError if the text cannot be found
        :returns None
        """
        node = self.browser.find_element(By.ID, tag_id)
        self.assertIn(text, node.text)

    @retry(NoSuchElementException, tries=3, delay=0.25, backoff=1)
    def find_element_by_id(self, node: WebElement, id_):
        """Find an element by its ID.

        This only exists to add the retry functionality, without which, things
        break, likely due to timing errors.

        :param node: The node under which we search for the element.
        :param id_: The ID of the element to find.
        :return: The element found.
        """
        return node.find_element(By.ID, id_)

    # See http://www.obeythetestinggoat.com/how-to-get-selenium-to-wait-for-page-load-after-a-click.html
    @contextmanager
    def wait_for_page_load(self, timeout: int = SELENIUM_TIMEOUT):
        old_page = self.browser.find_element(By.TAG_NAME, "html")
        yield
        WebDriverWait(self.browser, timeout).until(staleness_of(old_page))

    @retry(TimeoutError, tries=3, delay=0.25, backoff=1)
    def click_link_for_new_page(
        self,
        link_text: str,
        timeout: int = SELENIUM_TIMEOUT,
    ) -> None:
        with self.wait_for_page_load(timeout=timeout):
            self.browser.find_element(By.LINK_TEXT, link_text).click()

    def attempt_sign_in(self, username: str, password: str) -> None:
        self.click_link_for_new_page("Sign in / Register")
        self.assertIn("Sign In", self.browser.title)
        self.browser.find_element(By.ID, "username").send_keys(username)
        self.browser.find_element(By.ID, "password").send_keys(password)
        self.browser.find_element(By.ID, "password").submit()

    def get_url_and_wait(
        self,
        url: str,
        timeout: int = SELENIUM_TIMEOUT,
    ) -> None:
        self.browser.get(url)
        wait = WebDriverWait(self.browser, timeout)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "html")))

    def extract_result_count_from_serp(self) -> int:
        results = self.browser.find_element(By.ID, "result-count").text.strip()
        try:
            count = int(results.split(" ")[0].replace(",", ""))
        except (IndexError, ValueError):
            self.fail("Cannot extract result count from SERP.")
        return count

    @staticmethod
    def _update_index() -> None:
        # For now, until some model/api issues are worked out for Audio
        # objects, we'll avoid using the cl_update_index command and do
        # this the hard way using tasks
        opinion_keys = Opinion.objects.values_list("pk", flat=True)
        add_items_to_solr(opinion_keys, "search.Opinion", force_commit=True)
        audio_keys = Audio.objects.values_list("pk", flat=True)
        add_items_to_solr(audio_keys, "audio.Audio", force_commit=True)

    @staticmethod
    def _teardown_test_solr() -> None:
        """Empty out the test cores that we use"""
        conns = [settings.SOLR_OPINION_TEST_URL, settings.SOLR_AUDIO_TEST_URL]
        for conn in conns:
            with Session() as session:
                si = scorched.SolrInterface(
                    conn, http_connection=session, mode="rw"
                )
                si.delete_all()
                si.commit()
