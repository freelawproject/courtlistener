# pylint: disable=C0103
"""
Test Issue 412: Add admin-visible notice to various pages showing if they are
blocked from search engines
"""
from django.contrib.auth.hashers import make_password
from django.urls import reverse
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.search.models import Docket
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import ESIndexTestCase
from cl.users.factories import UserProfileWithParentsFactory

BLOCKED_MSG = "Blocked"


class Base412Test(ESIndexTestCase, BaseSeleniumTest):
    def setUp(self) -> None:
        UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )
        # Do this in two steps to avoid triggering profile creation signal
        admin = UserProfileWithParentsFactory.create(
            user__username="admin",
            user__password=make_password("password"),
        )
        admin.user.is_superuser = True
        admin.user.is_staff = True
        admin.user.save()
        super().setUp()


class OpinionBlockedFromSearchEnginesTest(Base412Test):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Opinions are blocked from Search Engines
    """

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "opinions-issue-412.json",
        "audio-issue-412.json",
    ]

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_blocked_opinion(self) -> None:
        """For a blocked Opinion, an Admin should see indication."""
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("admin", "password")

        # Then she loads up a blocked case
        self.browser.get(
            f"{self.live_server_url}{reverse('view_case', args=('11', 'asdf'))}"
        )

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element(By.ID, "sidebar")
        self.assertIn(BLOCKED_MSG, sidebar.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_non_admin_viewing_blocked_opinion(self) -> None:
        """For a blocked Opinion, a Non-admin should see NO indication."""
        # Pandora (not an Admin) logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        # Then she loads up a blocked case
        self.browser.get(
            f"{self.live_server_url}{reverse('view_case', args=('11', 'asdf'))}"
        )

        # She does NOT see a widget telling her the page is blocked
        sidebar = self.browser.find_element(By.ID, "sidebar")
        self.assertNotIn(BLOCKED_MSG, sidebar.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_not_blocked_opinion(self) -> None:
        """For a non-blocked Opinion, there should be no indication"""
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("admin", "password")

        # Then she loads up a case that's not blocked
        self.browser.get(
            f"{self.live_server_url}{reverse('view_case', args=('10', 'asdf'))}"
        )

        # She does NOT see a widget telling her the page is blocked
        sidebar = self.browser.find_element(By.ID, "sidebar")
        self.assertNotIn(BLOCKED_MSG, sidebar.text)


class DocketBlockedFromSearchEnginesTest(Base412Test):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Dockets are blocked from Search Engines
    """

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "opinions-issue-412.json",
        "audio-issue-412.json",
    ]

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_blocked_docket(self) -> None:
        """For a blocked Dockets, an Admin should see indication."""
        # Admin navigates to CL and logs in
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("admin", "password")

        # Pulls up a page for a Docket that is blocked to search engines
        docket = Docket.objects.get(pk=11)
        self.browser.get(f"{self.live_server_url}{docket.get_absolute_url()}")

        # And sees a badge that lets her know it's blocked
        self.assertIn(BLOCKED_MSG, self.browser.page_source)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_non_admin_viewing_blocked_docket(self) -> None:
        """For a blocked Docket, a Non-admin should see NO indication."""
        # Pandora navigates to CL and logs in
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        # Pulls up a page for a Docket that is blocked to search engines
        docket = Docket.objects.get(pk=11)
        self.browser.get(f"{self.live_server_url}{docket.get_absolute_url()}")

        # And does not see a badge indicating that it's blocked.
        btns = self.browser.find_elements(
            By.CSS_SELECTOR, ".content .btn.btn-danger"
        )
        expected_btn_count = 1
        actual_btn_count = len(btns)
        self.assertEqual(
            actual_btn_count,
            expected_btn_count,
            msg="Found %s button(s), but expected %s. Does the user have "
            "access to the blocked button they shouldn't or maybe the "
            "page crashed?" % (actual_btn_count, expected_btn_count),
        )

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_not_blocked_docket(self) -> None:
        """For a non-blocked Docket, there should be no indication."""
        # Admin navigates to CL and logs in
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("admin", "password")

        # Pulls up a page for a Docket that is not blocked to search engines
        docket = Docket.objects.get(pk=10)
        self.browser.get(f"{self.live_server_url}{docket.get_absolute_url()}")

        # And does not see a badge that lets her know it's blocked
        btn = self.browser.find_element(By.CSS_SELECTOR, ".btn.btn-success")
        self.assertNotIn(BLOCKED_MSG, btn.text)


class AudioBlockedFromSearchEnginesTest(Base412Test):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Audio pages are blocked from Search Engines
    """

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "opinions-issue-412.json",
        "audio-issue-412.json",
    ]

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_blocked_audio_page(self) -> None:
        """For a blocked Audio pages, an Admin should see indication."""
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("admin", "password")

        # She selects Oral Arguments to toggle the results to audio
        self.browser.find_element(By.CSS_SELECTOR, "#navbar-oa a").click()

        # She lands on the advanced search screen for OA, and does a wildcard
        # search.
        searchbox = self.browser.find_element(By.ID, "id_q")
        searchbox.submit()

        # The SERP updates and she selects the one she knows is blocked
        blocked_argument = self.browser.find_element(
            By.LINK_TEXT, "Blocked Oral Argument (Test 2015)"
        )
        blocked_argument.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element(By.ID, "sidebar")
        self.assertIn(BLOCKED_MSG, sidebar.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_non_admin_viewing_blocked_audio_page(self) -> None:
        """For a blocked Audio pages, a Non-admin should see NO indication."""
        # Pandora logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        # She selects Oral Arguments to toggle the results to audio
        self.browser.find_element(By.CSS_SELECTOR, "#navbar-oa a").click()

        # She lands on the advanced search screen for OA, and does a wildcard
        # search.
        searchbox = self.browser.find_element(By.ID, "id_q")
        searchbox.submit()

        # The SERP updates and she selects the one she knows is blocked
        self.click_link_for_new_page("Blocked Oral Argument (Test 2015)")

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element(By.ID, "sidebar")
        self.assertNotIn(BLOCKED_MSG, sidebar.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_not_blocked_audio_page(self) -> None:
        """For a non-blocked Audio pages, there should be no indication"""
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("admin", "password")

        # She selects Oral Arguments to toggle the results to audio
        self.browser.find_element(By.CSS_SELECTOR, "#navbar-oa a").click()

        # She lands on the advanced search screen for OA, and does a wildcard
        # search.
        searchbox = self.browser.find_element(By.ID, "id_q")
        searchbox.submit()

        # The SERP updates and she selects the one she knows is blocked
        blocked_argument = self.browser.find_element(
            By.LINK_TEXT, "Not Blocked Oral Argument (Test 2015)"
        )
        blocked_argument.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element(By.ID, "sidebar")
        self.assertNotIn(BLOCKED_MSG, sidebar.text)
