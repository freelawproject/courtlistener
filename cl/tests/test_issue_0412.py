# pylint: disable=C0103
"""
Test Issue 412: Add admin-visible notice to various pages showing if they are
blocked from search engines
"""
from cl.tests.base import BaseSeleniumTest


class OpinionBlockedFromSearchEnginesTest(BaseSeleniumTest):
    """
    Tests for validating UX elements of showing or not showing visual
    indications of whether Opinions are blocked from Search Engines
    """

    def test_admin_viewing_blocked_opinion(self):
        """ For a blocked Opinion, an Admin should see indication. """
        self.fail('Finish test_admin_viewing_blocked_opinion')

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
