# coding=utf-8
"""
Tests for visual aspects of CourtListener's responsive design
"""
from cl.tests.base import BaseSeleniumTest, DESKTOP_WINDOW, MOBILE_WINDOW
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class LayoutTest(BaseSeleniumTest):
    """Test non-device-specific layout features."""

    fixtures = ['test_court.json', 'authtest_data.json',
                'judge_judy.json', 'test_objects_search.json',
                'functest_opinions.json', 'test_objects_audio.json']

    def test_general_homepage_layout(self):
        """
        Tests the general layout of things like the ordering of the Search,
        Latest Opinion/Oral Arguments, etc. sections as well as their
        existance and population. Should be independent of device.
        """
        self.browser.get(self.server_url)

        # homepage = self.browser.find_element_by_id('homepage')
        rows = self.browser.find_elements_by_css_selector('#homepage > .row')

        # Order of collapsing should follow:
        # - Search box
        self.assertIn('Search', rows[0].text)

        # rows[1] is a hidden row at the moment for the jurisdiction modal

        # - Advanced Search link
        self.assertIn('Advanced Search', rows[2].text)
        rows[2].find_element_by_link_text('Advanced Search')

        # - About
        # -- About CourtListener
        # -- About Free Law Project
        self.assertIn('About CourtListener', rows[3].text)
        self.assertIn(
            'CourtListener is a free legal research website',
            rows[3].text
        )
        self.assertIn('About Free Law Project', rows[3].text)
        self.assertIn(
            'Free Law Project seeks to provide free access to primary legal',
            rows[3].text
        )
        rows[3].find_element_by_link_text('Free Law Project')

        # - Latest
        # -- Latest Opinions
        self.assertIn('Latest Opinions', rows[4].text)
        # --- From 1 to 5 Opinions
        opinions = rows[4].find_elements_by_css_selector('div.col-sm-6')[0]
        self.assertAlmostEqual(
            len(opinions.find_elements_by_tag_name('article')),
            3,
            delta=2
        )
        # --- See Recent Opinions button
        opinions.find_element_by_link_text('See Recent Opinions')

        # -- Latest Oral Arguments
        self.assertIn('Latest Oral Arguments', rows[4].text)
        # --- From 1 to 5 Arguments
        oral_args = rows[4].find_elements_by_css_selector('div.col-sm-6')[1]
        self.assertAlmostEqual(
            len(oral_args.find_elements_by_tag_name('article')),
            3,
            delta=2
        )
        # --- See Recent Oral Arguments button
        oral_args.find_element_by_link_text('See Recent Oral Arguments')

        # - The Numbers
        self.assertIn('The Numbers', rows[5].text)


class DesktopLayoutTest(BaseSeleniumTest):
    """
    Test graphic layout/rendering/behavior of the UI at desktop resolution
    """

    def setUp(self):
        super(DesktopLayoutTest, self).setUp()
        self.browser.set_window_size(DESKTOP_WINDOW[0], DESKTOP_WINDOW[1])

    def test_desktop_home_page_aesthetics(self):
        self.browser.get(self.server_url)

        # At desktop-level resolution, the menu should be fully visible by
        # default and not start collapsed like in mobile
        menu = self.browser.find_element_by_css_selector('.nav')
        self.assertTrue(menu.is_displayed())

        # search box is centered and roughly 600px
        searchbox = self.browser.find_element_by_id('id_q')
        search_button = self.browser.find_element_by_id('search-button')
        juri_select = self.browser.find_element_by_css_selector(
            'div[data-content="Select Jurisdictions"]'
        )
        search_width = (searchbox.size['width'] +
                        search_button.size['width'] +
                        juri_select.size['width'])
        self.assertAlmostEqual(
            searchbox.location['x'] + search_width / 2,
            DESKTOP_WINDOW[0] / 2,
            delta=10
        )
        self.assertAlmostEqual(
            searchbox.size['width'],
            600,
            delta=5
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
        self.browser.set_window_size(MOBILE_WINDOW[0], MOBILE_WINDOW[1])

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
            navbtn.location['x'] + navbtn.size['width'] + 10,
            MOBILE_WINDOW[0],
            delta=10
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
            MOBILE_WINDOW[0],
            delta=5
        )

        # and the menu hides when the button is clicked
        navbtn.click()
        WebDriverWait(self.browser, 5).until_not(EC.visibility_of(menu))
        self.assertFalse(menu.is_displayed())

        # search box should always be centered
        searchbox = self.browser.find_element_by_id('id_q')
        search_button = self.browser.find_element_by_id('search-button')
        juri_select = self.browser.find_element_by_css_selector(
            'div[data-content="Select Jurisdictions"]'
        )
        search_width = (searchbox.size['width'] +
                        search_button.size['width'] +
                        juri_select.size['width'])

        self.assertAlmostEqual(
            searchbox.location['x'] + search_width / 2,
            MOBILE_WINDOW[0] / 2,
            delta=10
        )
        # and the search box should be ~250px wide in mobile layout
        self.assertAlmostEqual(
            searchbox.size['width'],
            250,
            delta=5
        )
