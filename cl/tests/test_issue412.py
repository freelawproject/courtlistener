# pylint: disable=C0103
"""
Test Issue 412: Add admin-visible notice to various pages showing if they are
blocked from search engines
"""

from datetime import date

from django.contrib.auth.hashers import make_password
from django.urls import reverse
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from timeout_decorator import timeout_decorator

from cl.audio.factories import AudioFactory
from cl.search.factories import (
    CourtFactory,
    OpinionClusterWithParentsFactory,
    OpinionWithParentsFactory,
)
from cl.search.models import PRECEDENTIAL_STATUS, Docket
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.users.factories import UserProfileWithParentsFactory

BLOCKED_MSG = "Blocked"


class Base412Test(BaseSeleniumTest):
    def setUp(self) -> None:
        test_court = CourtFactory.create(
            id="test",
            position=0.0,
            citation_string="Test",
            short_name="Testing Supreme Court",
            full_name="Testing Supreme Court",
            in_use=True,
            url="https://www.courtlistener.com/",
            jurisdiction="F",
            has_opinion_scraper=True,
            has_oral_argument_scraper=False,
        )

        unblocked_cluster = OpinionClusterWithParentsFactory.create(
            pk=10,
            docket__pk=10,
            docket__court=test_court,
            docket__docket_number="1337-np",
            docket__case_name="Not Blocked Docket",
            docket__case_name_full="full name for Not Blocked Docket",
            docket__case_name_short="short name for Not Blocked Docket",
            docket__blocked=False,
            docket__source=Docket.DEFAULT,
            docket__date_argued=date(2015, 8, 15),
            case_name="Not Blocked Opinion",
            case_name_full="Reference to Voutila v. Bonvini",
            case_name_short="short name for Not Blocked Opinion",
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            blocked=False,
        )
        OpinionWithParentsFactory.create(
            cluster=unblocked_cluster,
            plain_text="This is a not blocked opinion.",
        )

        blocked_cluster = OpinionClusterWithParentsFactory.create(
            pk=11,
            docket__pk=11,
            docket__court=test_court,
            docket__docket_number="blocked-docket-number",
            docket__case_name="Blocked Docket",
            docket__case_name_full="Blocked Docket full name",
            docket__case_name_short="short name for Blocked Docket",
            docket__blocked=True,
            docket__date_blocked=date(2015, 8, 15),
            docket__source=Docket.DEFAULT,
            docket__date_argued=date(2015, 8, 15),
            case_name="Blocked Opinion",
            case_name_full="Blocked Opinion full name",
            case_name_short="Case name in short for Blocked Opinion",
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            blocked=True,
            date_blocked=date(2015, 8, 15),
        )
        OpinionWithParentsFactory.create(
            cluster=blocked_cluster,
            plain_text="This is a blocked opinion.",
        )

        AudioFactory.create(
            pk=1,
            docket=unblocked_cluster.docket,
            case_name="Not Blocked Oral Argument",
            case_name_full="Not Blocked Oral Argument",
            case_name_short="Not Blocked Oral Argument",
            local_path_mp3="test/audio/2.mp3",
            local_path_original_file="mp3/2015/08/15/sec_v._frank_j._custable_jr._cl.mp3",
            processing_complete=True,
            duration=15,
            blocked=False,
        )
        AudioFactory.create(
            pk=2,
            docket=unblocked_cluster.docket,
            case_name="Blocked Oral Argument",
            case_name_full="Blocked Oral Argument",
            case_name_short="Blocked Oral Argument",
            local_path_mp3="test/audio/2.mp3",
            local_path_original_file="mp3/2015/07/08/jose_a._dominguez_v._loretta_e._lynch.mp3",
            processing_complete=True,
            duration=837,
            blocked=True,
            date_blocked=date(2015, 8, 8),
        )

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

    def attempt_sign_in(self, username: str, password: str) -> None:
        self.get_url_and_wait(f"{self.live_server_url}{reverse('sign-in')}")
        self.browser.find_element(By.ID, "username").send_keys(username)
        self.browser.find_element(By.ID, "password").send_keys(password)
        self.browser.find_element(By.ID, "password").submit()
        WebDriverWait(self.browser, 10).until(
            EC.presence_of_element_located((By.ID, "logout-form"))
        )


class OpinionBlockedFromSearchEnginesTest(Base412Test):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Opinions are blocked from Search Engines
    """

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
        self.assertNotIn("Admin", sidebar.text)
        results = self.browser.find_elements(By.CSS_SELECTOR, "div.btn-danger")
        self.assertEqual(len(results), 0)

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
        self.assertIn("Admin", sidebar.text)
        results = self.browser.find_elements(By.CSS_SELECTOR, "div.btn-danger")
        self.assertEqual(len(results), 0)


class DocketBlockedFromSearchEnginesTest(Base412Test):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Dockets are blocked from Search Engines
    """

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
            msg=f"Found {actual_btn_count} button(s), but expected {expected_btn_count}. Does the user have "
            "access to the blocked button they shouldn't or maybe the "
            "page crashed?",
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

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_blocked_audio_page(self) -> None:
        """For a blocked Audio pages, an Admin should see indication."""
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("admin", "password")

        # She selects the oral arguments dropdown
        self.browser.find_element(By.CSS_SELECTOR, "#navbar-oa a").click()

        # And selects the search oral arguments link
        self.browser.find_element(
            By.LINK_TEXT, "Search Oral Arguments"
        ).click()

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

        # She selects the oral arguments dropdown
        self.browser.find_element(By.CSS_SELECTOR, "#navbar-oa a").click()

        # And selects the search oral arguments link
        self.browser.find_element(
            By.LINK_TEXT, "Search Oral Arguments"
        ).click()

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

        # She selects the oral arguments dropdown
        self.browser.find_element(By.CSS_SELECTOR, "#navbar-oa a").click()

        # And selects the search oral arguments link
        self.browser.find_element(
            By.LINK_TEXT, "Search Oral Arguments"
        ).click()

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
