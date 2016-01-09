# pylint: disable=C0103
"""
Test Issue 412: Add admin-visible notice to various pages showing if they are
blocked from search engines
"""
from selenium.common.exceptions import NoSuchElementException
from cl.tests.base import BaseSeleniumTest
from cl.search.models import Opinion, Docket


class OpinionBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Opinions are blocked from Search Engines
    """
    fixtures = ['test_court.json', 'authtest_data.json', 'judge_judy.json',
                'opinions-issue-412.json', 'audio-issue-412.json']

    def test_admin_viewing_blocked_opinion(self):
        """ For a blocked Opinion, an Admin should see indication. """
        # Admin logs into CL using her admin account
        self.browser.get(self.server_url)
        self.attempt_sign_in('admin', 'password')

        # She ends up on the SERP page and clicks the link for an Opinion
        # she knows is blocked
        blocked_opinion = self.browser.find_element_by_link_text(
            'Blocked Opinion (Test 2015)'
        )
        blocked_opinion.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertIn('Blocked from Search', sidebar.text)
        self.assertNotIn('Available via Search', sidebar.text)

    def test_non_admin_viewing_blocked_opinion(self):
        """ For a blocked Opinion, a Non-admin should see NO indication. """
        # Pandora (not an Admin) logs into CL using her admin account
        self.browser.get(self.server_url)
        self.attempt_sign_in('pandora', 'password')

        # She ends up on the SERP page and clicks the link for an Opinion
        # she knows is blocked
        blocked_opinion = self.browser.find_element_by_link_text(
            'Blocked Opinion (Test 2015)'
        )
        blocked_opinion.click()

        # She does NOT see a widget telling her the page is blocked
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertNotIn('Blocked from Search', sidebar.text)
        self.assertIn('Available via Search', sidebar.text)

    def test_admin_viewing_not_blocked_opinion(self):
        """ For a non-blocked Opinion, there should be no indication """
        # Admin logs into CL using her admin account
        self.browser.get(self.server_url)
        self.attempt_sign_in('admin', 'password')

        # She ends up on the SERP page and clicks the link for an Opinion
        # she knows is definitely NOT blocked
        blocked_opinion = self.browser.find_element_by_link_text(
            'Not Blocked Opinion (Test 2015)'
        )
        blocked_opinion.click()

        # She does NOT see a widget telling her the page is blocked
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertNotIn('Blocked from Search', sidebar.text)
        self.assertIn('Available via Search', sidebar.text)
        
class DocketBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Dockets are blocked from Search Engines
    """
    fixtures = ['test_court.json', 'authtest_data.json', 'judge_judy.json',
                'opinions-issue-412.json', 'audio-issue-412.json']

    def test_admin_viewing_blocked_docket(self):
        """ For a blocked Dockets, an Admin should see indication. """
        self.fail('Finish test_admin_viewing_blocked_docket')

    def test_non_admin_viewing_blocked_docket(self):
        """ For a blocked Dockets, a Non-admin should see NO indication. """
        self.fail('Finish test_non_admin_viewing_blocked_docket')

    def test_admin_viewing_not_blocked_docket(self):
        """ For a non-blocked Dockets, there should be no indication """
        self.fail('test_admin_viewing_not_blocked_docket')


class AudioBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Audio pages are blocked from Search Engines
    """
    fixtures = ['test_court.json', 'authtest_data.json', 'judge_judy.json',
                'opinions-issue-412.json', 'audio-issue-412.json']

    def test_admin_viewing_blocked_audio_page(self):
        """ For a blocked Audio pages, an Admin should see indication. """
        # Admin logs into CL using her admin account
        self.browser.get(self.server_url)
        self.attempt_sign_in('admin', 'password')

        # She selects Oral Arguments to toggle the results to audio
        self.browser \
            .find_element_by_css_selector('label[for="id_type_1"]') \
            .click()

        # The SERP updates and she selects the one she knows is blocked
        blocked_argument = self.browser.find_element_by_link_text(
            'Blocked Oral Argument (Test 2015)'
        )
        blocked_argument.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertIn('Blocked from Search', sidebar.text)

    def test_non_admin_viewing_blocked_audio_page(self):
        """ For a blocked Audio pages, a Non-admin should see NO indication. """
        # Pandora logs into CL using her admin account
        self.browser.get(self.server_url)
        self.attempt_sign_in('pandora', 'password')

        # She selects Oral Arguments to toggle the results to audio
        self.browser \
            .find_element_by_css_selector('label[for="id_type_1"]') \
            .click()

        # The SERP updates and she selects the one she knows is blocked
        blocked_argument = self.browser.find_element_by_link_text(
            'Blocked Oral Argument (Test 2015)'
        )
        blocked_argument.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertNotIn('Blocked from Search', sidebar.text)

    def test_admin_viewing_not_blocked_audio_page(self):
        """ For a non-blocked Audio pages, there should be no indication """
        # Admin logs into CL using her admin account
        self.browser.get(self.server_url)
        self.attempt_sign_in('admin', 'password')

        # She selects Oral Arguments to toggle the results to audio
        self.browser \
            .find_element_by_css_selector('label[for="id_type_1"]') \
            .click()

        # The SERP updates and she selects the one she knows is blocked
        blocked_argument = self.browser.find_element_by_link_text(
            'Not Blocked Oral Argument (Test 2015)'
        )
        blocked_argument.click()

        # She notices a widget letting her know it's blocked by search engines
        sidebar = self.browser.find_element_by_id('sidebar')
        self.assertNotIn('Blocked from Search', sidebar.text)
