# coding=utf-8
"""
Tests for visual aspects of CourtListener's responsive design
"""
from cl.tests.base import BaseSeleniumTest, DESKTOP_WINDOW, MOBILE_WINDOW
from unittest import skip


class DesktopLayoutTest(BaseSeleniumTest):
    """Test graphic layout and rendering of key UI elements of CL"""

    def setUp(self):
        super(DesktopLayoutTest, self).setUp()
        self.browser.set_window_size(DESKTOP_WINDOW[0], DESKTOP_WINDOW[1])

    @skip('finish the test')
    def test_desktop_home_page_aesthetics(self):
        self.browser.get(self.server_url)

        # search box should be centered
        self.fail('finish test')


class MobileLayoutTest(BaseSeleniumTest):
    """
    Test graphic layout and rendering of key UI elements of CL on mobile
    devices
    """

    def setUp(self):
        super(MobileLayoutTest, self).setUp()
        self.browser.set_window_size(MOBILE_WINDOW[0], MOBILE_WINDOW[1])

    @skip('finish the test')
    def test_mobile_home_page_aesthetics(self):
        self.browser.get(self.server_url)

        # search box should be centered
        self.fail('finish test')
