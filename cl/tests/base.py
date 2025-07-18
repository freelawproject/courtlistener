"""
Base class(es) for functional testing CourtListener using Selenium and PhantomJS
"""

import os
import socket
from contextlib import contextmanager

from django.conf import settings
from django.core.management import call_command
from django.test.utils import override_settings, tag
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.expected_conditions import staleness_of
from selenium.webdriver.support.ui import WebDriverWait
from timeout_decorator import TimeoutError

from cl.lib.decorators import retry
from cl.lib.test_helpers import SerializeLockFileTestMixin
from cl.search.models import SEARCH_TYPES
from cl.tests.cases import ESIndexTestCase, StaticLiveServerTestCase

SELENIUM_TIMEOUT = 120
if "SELENIUM_TIMEOUT" in os.environ:
    try:
        SELENIUM_TIMEOUT = int(os.environ["SELENIUM_TIMEOUT"])
    except ValueError:
        pass


@tag("selenium")
@override_settings(
    ALLOWED_HOSTS=["*"],
)
class BaseSeleniumTest(
    SerializeLockFileTestMixin, StaticLiveServerTestCase, ESIndexTestCase
):
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

        # Workaround for
        # https://bugs.chromium.org/p/chromium/issues/detail?id=1033941
        options.add_argument(
            "--disable-features=AvoidFlashBetweenNavigation,PaintHolding"
        )

        if settings.DOCKER_SELENIUM_HOST:
            return webdriver.Remote(
                settings.DOCKER_SELENIUM_HOST,
                options=options,
                keep_alive=True,
            )
        return webdriver.Chrome(options=options, keep_alive=True)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.screenshot = "SELENIUM_DEBUG" in os.environ

        # Set host to externally accessible web server address
        cls.host = socket.gethostbyname(socket.gethostname())

        cls.browser = cls._create_browser()
        cls.browser.implicitly_wait(5)

    def setUp(self) -> None:
        super().setUp()
        self.reset_browser()
        self.rebuild_index("audio.Audio")
        self.delete_index("search.OpinionCluster")
        self.create_index("search.OpinionCluster")
        self._update_index()

    def reset_browser(self) -> None:
        self.browser.delete_all_cookies()

    def tearDown(self) -> None:
        if self.screenshot:
            filename = (
                f"{type(self).__name__}-{self._testMethodName}-selenium.png"
            )
            print(f"\nSaving screenshot in docker image at: /tmp/{filename}")
            self.browser.save_screenshot(f"/tmp/{filename}")
        super().tearDown()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.quit()
        super().tearDownClass()

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

    # See https://www.obeythetestinggoat.com/how-to-get-selenium-to-wait-for-page-load-after-a-click.html
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
        # Index Opinions into ES.
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )
