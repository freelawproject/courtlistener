# coding=utf-8
"""
Tests for visual aspects of CourtListener's responsive design
"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from timeout_decorator import timeout_decorator

from cl.tests.base import BaseSeleniumTest, DESKTOP_WINDOW, MOBILE_WINDOW, \
    SELENIUM_TIMEOUT


class LayoutTest(BaseSeleniumTest):
    """Test non-device-specific layout features."""

    fixtures = ['test_court.json', 'authtest_data.json',
                'judge_judy.json', 'test_objects_search.json',
                'functest_opinions.json', 'test_objects_audio.json']

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_general_homepage_layout(self):
        """
        Tests the general layout of things like the ordering of the Search,
        Latest Opinion/Oral Arguments, etc. sections as well as their
        existance and population. Should be independent of device.
        """
        self.browser.get(self.server_url)

        rows = self.browser.find_elements_by_css_selector('#homepage > .row')

        # Order of collapsing should follow:
        # - Search box
        self.assertIn('Search', rows[0].text)

        # - Advanced Search link
        self.assertIn('Advanced Search', rows[1].text)
        rows[1].find_element_by_link_text('Advanced Search')

        # - About
        # -- About CourtListener
        # -- About Free Law Project
        self.assertIn('About CourtListener', rows[2].text)
        self.assertIn(
            'CourtListener is a free legal research website',
            rows[2].text
        )
        self.assertIn('About Free Law Project', rows[2].text)
        self.assertIn(
            'Free Law Project seeks to provide free access to primary legal',
            rows[2].text
        )
        rows[2].find_element_by_link_text('Free Law Project')

        # - Latest
        # -- Latest Opinions
        self.assertIn('Latest Opinions', rows[3].text)
        # --- From 1 to 5 Opinions
        opinions = rows[3].find_elements_by_css_selector('div.col-sm-6')[0]
        self.assertAlmostEqual(
            len(opinions.find_elements_by_tag_name('article')),
            3,
            delta=2
        )
        # --- See Recent Opinions button
        opinions.find_element_by_link_text('See Recent Opinions')

        # -- Latest Oral Arguments
        self.assertIn('Latest Oral Arguments', rows[3].text)
        # --- From 1 to 5 Arguments
        oral_args = rows[3].find_elements_by_css_selector('div.col-sm-6')[1]
        self.assertAlmostEqual(
            len(oral_args.find_elements_by_tag_name('article')),
            3,
            delta=2
        )
        # --- See Recent Oral Arguments button
        oral_args.find_element_by_link_text('See Recent Oral Arguments')

        # - The Numbers
        self.assertIn('The Numbers', rows[4].text)


class DesktopLayoutTest(BaseSeleniumTest):
    """
    Test graphic layout/rendering/behavior of the UI at desktop resolution
    """

    def setUp(self):
        super(DesktopLayoutTest, self).setUp()
        self.reset_browser(height=DESKTOP_WINDOW[0], width=DESKTOP_WINDOW[1])

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_desktop_home_page_aesthetics(self):
        self.browser.get(self.server_url)

        # At desktop-level resolution, the menu should be fully visible by
        # default and not start collapsed like in mobile
        menu = self.browser.find_element_by_css_selector('.nav')
        self.assertTrue(menu.is_displayed())

        # search box is centered and roughly 400px at this resolution
        searchbox = self.browser.find_element_by_id('id_q')
        search_button = self.browser.find_element_by_id('search-button')
        search_width = (searchbox.size['width'] +
                        search_button.size['width'])
        self.assertAlmostEqual(
            searchbox.location['x'] + (search_width / 2),
            DESKTOP_WINDOW[0] / 3,
            delta=50
        )
        self.assertAlmostEqual(
            searchbox.size['width'],
            400,
            delta=15
        )


class MobileLayoutTest(BaseSeleniumTest):
    """
    Test graphic layout and rendering of key UI elements of CL on mobile
    devices (small enough so the responsive design kicks in)
    """

    fixtures = ['test_court.json', 'authtest_data.json',
                'judge_judy.json', 'test_objects_search.json',
                'functest_opinions.json', 'test_objects_audio.json']

    def setUp(self):
        super(MobileLayoutTest, self).setUp()
        self.reset_browser(height=MOBILE_WINDOW[0], width=MOBILE_WINDOW[1])

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_mobile_home_page_aesthetics(self):
        self.browser.get(self.server_url)

        # Basic intro text is displayed
        self.assert_text_in_body(
            'Search millions of opinions by case name, topic, or citation.'
        )

        # on mobile, the navbar should start collapsed into a hamburger-esque
        # icon in the upper right
        navbar_header = (self.browser
                         .find_element_by_css_selector('.navbar-header'))
        navbtn = navbar_header.find_element_by_tag_name('button')
        self.assertIn('collapsed', navbtn.get_attribute('class'))
        self.assertAlmostEqual(
            navbtn.location['x'] + navbtn.size['width'] + 30,
            MOBILE_WINDOW[0] - 100,
            delta=85
        )

        # clicking the button displays and then hides the menu
        menu = self.browser.find_element_by_css_selector('.nav')
        self.assertFalse(menu.is_displayed())
        navbtn.click()
        WebDriverWait(self.browser, 5).until(EC.visibility_of(menu))
        self.assertTrue(menu.is_displayed())

        # and the menu is width of the display
        self.assertAlmostEqual(
            menu.size['width'],
            MOBILE_WINDOW[0] - 100,
            delta=100
        )

        # and the menu hides when the button is clicked
        # TODO: figure out why selenium does't like this anymore!
        # navbtn.click()
        # WebDriverWait(self.browser, 10).until_not(EC.visibility_of(menu))
        # self.assertFalse(menu.is_displayed())

        # search box should always be centered
        searchbox = self.browser.find_element_by_id('id_q')
        search_button = self.browser.find_element_by_id('search-button')
        search_width = (searchbox.size['width'] +
                        search_button.size['width'])

        self.assertAlmostEqual(
            searchbox.location['x'] + search_width / 2,
            MOBILE_WINDOW[0] / 2,
            delta=100
        )
        # and the search box should be ~250px wide in mobile layout
        self.assertAlmostEqual(
            searchbox.size['width'],
            250,
            delta=5
        )
