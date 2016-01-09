# pylint: disable=C0103
"""
Test Issue 412: Add admin-visible notice to various pages showing if they are
blocked from search engines
"""
from cl.tests.base import BaseSeleniumTest
from cl.search.models import OpinionCluster, Docket, Court


class OpinionBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Opinions are blocked from Search Engines
    """

    fixtures = ['test_court.json', 'authtest_data.json', 'judge_judy.json',
        'opinions-issue-412.json']

    def test_admin_viewing_blocked_opinion(self):
        """ For a blocked Opinion, an Admin should see indication. """
        # Admin logs into CL using her admin account
        self.browser.get(self.server_url)
        self.attempt_sign_in('admin', 'password')

        # She navigates to a particular Opinion page she knows has been blocked
        # from indexing by Search Engines
        oc = OpinionCluster.objects.get(pk=11)
        self.browser.get(oc.get_absolute_url())
        self.assert_text_in_body(oc.case_name)

        # She notices a widget letting her know it's blocked by search engines
        self.browser.find_element_by_css_selector('.blocked-search-engines')

    def test_non_admin_viewing_blocked_opinion(self):
        """ For a blocked Opinion, a Non-admin should see NO indication. """
        self.fail('Finish test_non_admin_viewing_blocked_opinion')

    def test_admin_viewing_not_blocked_opinion(self):
        """ For a non-blocked Opinion, there should be no indication """
        self.fail('test_admin_viewing_not_blocked_opinion')


class DocketBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Dockets are blocked from Search Engines
    """

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

    def test_admin_viewing_blocked_audio_page(self):
        """ For a blocked Audio pages, an Admin should see indication. """
        self.fail('Finish test_admin_viewing_blocked_opinion')

    def test_non_admin_viewing_blocked_audio_page(self):
        """ For a blocked Audio pages, a Non-admin should see NO indication. """
        self.fail('Finish test_non_admin_viewing_blocked_opinion')

    def test_admin_viewing_not_blocked_audio_page(self):
        """ For a non-blocked Audio pages, there should be no indication """
        self.fail('test_admin_viewing_not_blocked_opinion')
