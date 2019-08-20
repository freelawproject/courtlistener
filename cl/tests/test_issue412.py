# pylint: disable=C0103
"""
Test Issue 412: Add admin-visible notice to various pages showing if they are
blocked from search engines
"""
from django.urls import reverse
from timeout_decorator import timeout_decorator

from cl.search.models import Docket
from cl.tests.base import BaseSeleniumTest, SELENIUM_TIMEOUT

BLOCKED_MSG = 'Blocked'


class OpinionBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Opinions are blocked from Search Engines
    """
    fixtures = ['test_court.json', 'authtest_data.json', 'judge_judy.json',
                'opinions-issue-412.json', 'audio-issue-412.json']

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_blocked_opinion(self):
        """ For a blocked Opinion, an Admin should see indication. """
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('admin', 'password')

        # Then she loads up a blocked case
        self.browser.get('%s%s' % (self.live_server_url,
                                   reverse('view_case', args=('11', 'asdf'))))

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertIn(BLOCKED_MSG, sidebar.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_non_admin_viewing_blocked_opinion(self):
        """ For a blocked Opinion, a Non-admin should see NO indication. """
        # Pandora (not an Admin) logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('pandora', 'password')

        # Then she loads up a blocked case
        self.browser.get('%s%s' % (self.live_server_url,
                                   reverse('view_case', args=('11', 'asdf'))))

        # She does NOT see a widget telling her the page is blocked
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertNotIn(BLOCKED_MSG, sidebar.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_not_blocked_opinion(self):
        """ For a non-blocked Opinion, there should be no indication """
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('admin', 'password')

        # Then she loads up a case that's not blocked
        self.browser.get('%s%s' % (self.live_server_url,
                                   reverse('view_case', args=('10', 'asdf'))))

        # She does NOT see a widget telling her the page is blocked
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertNotIn(BLOCKED_MSG, sidebar.text)


class DocketBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Dockets are blocked from Search Engines
    """
    fixtures = ['test_court.json', 'authtest_data.json', 'judge_judy.json',
                'opinions-issue-412.json', 'audio-issue-412.json']

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_blocked_docket(self):
        """ For a blocked Dockets, an Admin should see indication. """
        # Admin navigates to CL and logs in
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('admin', 'password')

        # Pulls up a page for a Docket that is blocked to search engines
        docket = Docket.objects.get(pk=11)
        self.browser.get(
            '%s%s' % (self.live_server_url, docket.get_absolute_url(),)
        )

        # And sees a badge that lets her know it's blocked
        self.assertIn(BLOCKED_MSG, self.browser.page_source)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_non_admin_viewing_blocked_docket(self):
        """ For a blocked Docket, a Non-admin should see NO indication. """
        # Pandora navigates to CL and logs in
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('pandora', 'password')

        # Pulls up a page for a Docket that is blocked to search engines
        docket = Docket.objects.get(pk=11)
        self.browser.get(
            '%s%s' % (self.live_server_url, docket.get_absolute_url(),)
        )

        # And does not see a badge indicating that it's blocked.
        btns = self.browser.find_elements_by_css_selector('.content .btn.btn-danger')
        expected_btn_count = 1
        self.assertEqual(
            len(btns),
            expected_btn_count,
            msg="Found button indicating the item is blocked, but user should "
                "not have this access."
        )

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_not_blocked_docket(self):
        """ For a non-blocked Docket, there should be no indication. """
        # Admin navigates to CL and logs in
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('admin', 'password')

        # Pulls up a page for a Docket that is not blocked to search engines
        docket = Docket.objects.get(pk=10)
        self.browser.get(
            '%s%s' % (self.live_server_url, docket.get_absolute_url(),)
        )

        # And does not see a badge that lets her know it's blocked
        btn = self.browser.find_element_by_css_selector('.btn.btn-success')
        self.assertNotIn(BLOCKED_MSG, btn.text)


class AudioBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Audio pages are blocked from Search Engines
    """
    fixtures = ['test_court.json', 'authtest_data.json', 'judge_judy.json',
                'opinions-issue-412.json', 'audio-issue-412.json']

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_blocked_audio_page(self):
        """ For a blocked Audio pages, an Admin should see indication. """
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('admin', 'password')

        # She selects Oral Arguments to toggle the results to audio
        self.browser.find_element_by_css_selector('#navbar-oa a').click()

        # She lands on the advanced search screen for OA, and does a wildcard
        # search.
        searchbox = self.browser.find_element_by_id('id_q')
        searchbox.send_keys('\n')

        # The SERP updates and she selects the one she knows is blocked
        blocked_argument = self.browser.find_element_by_link_text(
            'Blocked Oral Argument (Test 2015)'
        )
        blocked_argument.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertIn(BLOCKED_MSG, sidebar.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_non_admin_viewing_blocked_audio_page(self):
        """ For a blocked Audio pages, a Non-admin should see NO indication. """
        # Pandora logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('pandora', 'password')

        # She selects Oral Arguments to toggle the results to audio
        self.browser.find_element_by_css_selector('#navbar-oa a').click()

        # She lands on the advanced search screen for OA, and does a wildcard
        # search.
        searchbox = self.browser.find_element_by_id('id_q')
        searchbox.send_keys('\n')

        # The SERP updates and she selects the one she knows is blocked
        blocked_argument = self.browser.find_element_by_link_text(
            'Blocked Oral Argument (Test 2015)'
        )
        blocked_argument.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertNotIn(BLOCKED_MSG, sidebar.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_admin_viewing_not_blocked_audio_page(self):
        """ For a non-blocked Audio pages, there should be no indication """
        # Admin logs into CL using her admin account
        self.browser.get(self.live_server_url)
        self.attempt_sign_in('admin', 'password')

        # She selects Oral Arguments to toggle the results to audio
        self.browser.find_element_by_css_selector('#navbar-oa a').click()

        # She lands on the advanced search screen for OA, and does a wildcard
        # search.
        searchbox = self.browser.find_element_by_id('id_q')
        searchbox.send_keys('\n')

        # The SERP updates and she selects the one she knows is blocked
        blocked_argument = self.browser.find_element_by_link_text(
            'Not Blocked Oral Argument (Test 2015)'
        )
        blocked_argument.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertNotIn(BLOCKED_MSG, sidebar.text)
