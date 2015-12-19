# coding=utf-8
"""
Functional testing of courtlistener
"""
from cl.tests.base import BaseSeleniumTest
from django.conf import settings

class OpinionSearchFunctionalTest(BaseSeleniumTest):

    fixtures = ['test_court.json', 'judge_judy.json',
                'test_objects_search.json', 'test_objects_audio.json',
                'authtest_data.json']

    def _navigate_to_wildcard_results(self):
        self.fail('Finish the test.')

    def test_toggle_to_oral_args_search_results(self):
        # Dora navigates to the global SERP from the homepage
        self._navigate_to_wildcard_results()

        # Dora sees she has Opinion results, but wants Oral Arguments

        # She clicks on Oral Arguments

        # And notices her result set is now different

    def test_search_and_facet_docket_numbers(self):
        self.fail('finish the test!')

    def test_search_result_detail_page(self):
        self.fail('finish the test')

    def test_search_and_add_precedential_results(self):
        # Dora navigates to CL and just hits Search to just start with
        # a global result set
        self._navigate_to_wildcard_results()

        # She notices only Precedential results are being displayed

        # Even though she notices all jurisdictions were included in her search

        # But she also notices the option to select and include
        # Non-Precedential results. She checks the box.

        # Nothing happens yet.

        # She goes ahead and clicks the Search button again to resubmit

        # And now she notices her result set increases thanks to adding in
        # those other opinion types!
        self.fail('Finish the test!')

    def test_basic_homepage_search_and_signin_and_signout(self):

        # Dora navigates to the CL website.
        self.browser.get(self.server_url)

        # At a glance, Dora can see the Latest Opinions, Latest Oral Arguments,
        # the searchbox (obviously important), and a place to sign in
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertIn('Latest Opinions', page_text)
        self.assertIn('Latest Oral Arguments', page_text)

        search_box = self.browser.find_element_by_id('id_q')
        search_button = self.browser.find_element_by_id('search-button')
        self.assertIn('Search', search_button.text)

        self.assertIn('Sign in / Register', page_text)

        # Dora remembers this Lissner guy and wonders if he's been involved
        # in any litigation. She types his name into the search box and hits
        # Enter
        search_box.send_keys('lissner\n')

        # The browser brings her to a search engine result page with some
        # results. She notices her query is still in the searchbox and
        # has the ability to refine via facets
        result_count = self.browser.find_element_by_id('result-count')
        self.assertIn('Results', result_count.text)
        search_box = self.browser.find_element_by_id('id_q')
        self.assertEqual('lissner', search_box.get_attribute('value'))

        facet_sidebar = self.browser.\
            find_element_by_id('sidebar-facet-placeholder')
        self.assertIn('Precedential Status', facet_sidebar.text)

        # Wanting to keep an eye on this Lissner guy, she decides to sign-in
        # and so she can create an alert
        sign_in = self.browser.find_element_by_link_text('Sign in / Register')
        sign_in.click()

        # she providers her usename and password to sign in
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertIn('Sign In', page_text)
        self.assertIn('Username', page_text)
        self.assertIn('Password', page_text)
        btn = self.browser.find_element_by_css_selector('button[type="submit"]')
        self.assertEqual('Sign In', btn.text)

        self.browser.find_element_by_id('username').send_keys('pandora')
        self.browser.find_element_by_id('password').send_keys('password')
        btn.click()

        # upon redirect, she's brought back to her original search results
        # for 'lissner'
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertNotIn(
            'Please enter a correct username and password.',
            page_text
        )
        search_box = self.browser.find_element_by_id('id_q')
        self.assertEqual('lissner', search_box.get_attribute('value'))

        # She now sees the form for creating an alert
        self.assertIn('Create an Alert', page_text)
        self.assertIn('Give the alert a name', page_text)
        self.assertIn('How often should we notify you?', page_text)
        self.browser.find_element_by_id('id_name')
        self.browser.find_element_by_id('id_rate')
        btn = self.browser.find_element_by_id('alertSave')
        self.assertEqual('Create Alert', btn.text)

        # But she decides to wait until another time. Instead she decides she
        # will log out. She notices a Profile link dropdown in the top of the
        # page, clicks it, and selects Sign out
        profile_dropdown = self.browser.\
            find_element_by_css_selector('a.dropdown-toggle')
        self.assertEqual(profile_dropdown.text.strip(), u'Profile')

        dropdown_menu = self.browser.\
            find_element_by_css_selector('ul.dropdown-menu')
        self.assertIsNone(dropdown_menu.get_attribute('display'))

        profile_dropdown.click()

        sign_out = self.browser.find_element_by_link_text('Sign out')
        sign_out.click()

        # She receives a sign out confirmation with links back to the homepage,
        # the block, and an option to sign back in.
        page_text = self.browser.find_element_by_tag_name('body').text
        self.assertIn('You Have Successfully Signed Out', page_text)
        links = self.browser.find_elements_by_tag_name('a')
        self.assertIn('Go to the homepage', [link.text for link in links])
        self.assertIn('Read our blog', [link.text for link in links])

        bootstrap_btns = self.browser.find_elements_by_css_selector('a.btn')
        self.assertIn('Sign Back In', [btn.text for btn in bootstrap_btns])
