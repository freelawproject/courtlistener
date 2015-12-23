# coding=utf-8
"""
Functional testing of courtlistener
"""
from cl.tests.base import BaseSeleniumTest
from django.conf import settings
from unittest import skip


class OpinionSearchFunctionalTest(BaseSeleniumTest):
    """
    Test some of the primary search functionality of CL: searching opinions.
    These tests should exercise all aspects of using the search box and SERP.
    """
    fixtures = ['test_court.json', 'authtest_data.json',
        'judge_judy.json', 'test_objects_search.json',
        'functest_opinions.json', 'test_objects_audio.json']

    def _perform_wildcard_search(self):
        searchbox = self.browser.find_element_by_id('id_q')
        searchbox.send_keys('\n')
        result_count = self.browser.find_element_by_id('result-count')
        self.assertIn('Results', result_count.text)

    def test_toggle_to_oral_args_search_results(self):
        # Dora navigates to the global SERP from the homepage
        self.browser.get(self.server_url)
        self._perform_wildcard_search()
        self.extract_result_count_from_serp()

        # Dora sees she has Opinion results, but wants Oral Arguments
        self.assertTrue(self.extract_result_count_from_serp() > 0)
        label = self.browser.\
            find_element_by_css_selector('label[for="id_type_0"]')
        self.assertEqual('Opinions', label.text.strip())
        self.assertIn('selected', label.get_attribute('class'))
        self.assert_text_in_body('Date Filed')
        self.assert_text_not_in_body('Date Argued')

        # She clicks on Oral Arguments
        self.browser \
            .find_element_by_css_selector('label[for="id_type_1"]') \
            .click()

        # And notices her result set is now different
        oa_label = self.browser. \
            find_element_by_css_selector('label[for="id_type_1"]')
        self.assertIn('selected', oa_label.get_attribute('class'))
        self.assert_text_in_body('Date Argued')
        self.assert_text_not_in_body('Date Filed')

    def test_search_and_facet_docket_numbers(self):
        # Dora goes to CL and performs an initial wildcard Search
        self.browser.get(self.server_url)
        self._perform_wildcard_search()
        initial_count = self.extract_result_count_from_serp()

        # Seeing a result that has a docket number displayed, she wants
        # to find all similar opinions with the same or similar docket
        # number
        search_results = self.browser.find_element_by_id('search-results')
        self.assertIn('Docket Number:', search_results.text)

        # She types part of the docket number into the docket number
        # filter on the left and hits enter
        text_box = self.browser.find_element_by_id('id_docket_number')
        text_box.send_keys('1337\n')

        # The SERP refreshes and she sees resuls that
        # only contain fragments of the docker number she entered
        new_count = self.extract_result_count_from_serp()
        self.assertTrue(new_count < initial_count)

        search_results = self.browser.find_element_by_id('search-results')
        for result in search_results.find_elements_by_tag_name('article'):
            self.assertIn('1337', result.text)

    def test_opinion_search_result_detail_page(self):
        # Dora navitages to CL and does a simple wild card search
        self.browser.get(self.server_url)
        self.browser.find_element_by_id('id_q').send_keys('voutila\n')

        # Seeing an Opinion immediately on the first page of results, she
        # wants more details so she clicks the title and drills into the result
        articles = self.browser.find_elements_by_tag_name('article')
        articles[0].find_elements_by_tag_name('a')[0].click()

        # She is brought to the detail page for the results
        self.assertNotIn('Search Results', self.browser.title)
        self.assert_text_in_body('Back to Search Results')
        article_text = self.browser.find_element_by_tag_name('article').text

        # and she can see lots of detail! This includes things like:
        # The name of the jurisdiction/court,
        # the status of the Opinion, any citations, the docket number,
        # the Judges, and a unique fingerpring ID
        meta_data = self.browser.\
            find_elements_by_css_selector('.meta-data-header')
        headers = [u'Filed:', u'Precedential Status:', u'Citations:',
                   u'Docket Number:', u'Judges:', u'Nature of suit:']
        for header in headers:
            self.assertIn(header, [meta.text for meta in meta_data])

        # The complete body of the opinion is also displayed for her to
        # read on the page
        self.assertNotEqual(
            self.browser.find_element_by_id('opinion-content').text.strip(),
            ''
        )

        # She wants to dig a big deeper into the influence of this Opinion,
        # so she's able to see links to the first five citations on the left
        # and a link to the full list
        cited_by = self.browser.find_element_by_id('cited-by')
        self.assertIn('Cited By', cited_by.find_element_by_tag_name('h3').text)
        citations = cited_by.find_elements_by_tag_name('li')
        self.assertTrue(len(citations) > 0 and len(citations) < 6)

        # She clicks the "Full List of Citations" link and is brought to
        # a page with all the citations shown as links
        full_list = cited_by.\
            find_element_by_link_text('Full List of Cited Opinions')
        full_list.click()

        # She notices their paginated if there are too many and is given the
        # option to page through them.
        self.assertIn('Opinions Citing', self.browser.title)
        self.assert_text_not_in_body('Prev.')
        citations = self.browser.\
            find_elements_by_css_selector('li.citing-opinion')
        self.assertTrue(len(citations) > 0)

        # She's just been glossing through things and now she wants to
        # go back to the result. Seeing a convenient link Back to Document,
        # she clicks it and is taken back to the result page
        self.browser.find_element_by_link_text('Back to Document').click()
        self.assertNotIn('Opinions Citing', self.browser.title)
        self.assertEqual(
            self.browser.find_element_by_tag_name('article').text,
            article_text
        )
        # She now wants to see details on the list of Opinions cited within
        # this particular opinion. She notices an abbreviated list on the left,
        # and can click into a Full Table of Authorities. (She does so.)
        authorities = self.browser.find_element_by_id('authorities')
        self.assertIn(
            'Authorities',
            authorities.find_element_by_tag_name('h3').text
        )
        authority_links = authorities.find_elements_by_tag_name('li')
        self.assertTrue(len(authority_links) > 0 and len(authority_links < 6))
        authorities\
            .find_element_by_link_text('Full Table of Authorities')\
            .click()
        self.assertIn('Table of Authorities', self.browser.title)

        # Like before, she's just curious of the list and clicks Back to
        # Document.
        self.browser.find_element_by_link_text('Back to Document').click()

        # And she's back at the Opinion in question and pretty happy about that
        self.assertNotIn('Table of Authorities', self.browser.title)
        self.assertEqual(
            self.browser.find_element_by_tag_name('article').text,
            article_text
        )

    def test_search_and_add_precedential_results(self):
        # Dora navigates to CL and just hits Search to just start with
        # a global result set
        self.browser.get(self.server_url)
        self._perform_wildcard_search()
        first_count = self.extract_result_count_from_serp()

        # She notices only Precedential results are being displayed
        prec = self.browser.find_element_by_id('id_stat_Precedential')
        non_prec = self.browser.find_element_by_id('id_stat_Non-Precedential')
        self.assertEqual(prec.get_attribute('checked'), u'true')
        self.assertIsNone(non_prec.get_attribute('checked'))
        prec_count = self.browser.find_element_by_css_selector(
            'label[for="id_stat_Precedential"]'
        )
        non_prec_count = self.browser.find_element_by_css_selector(
            'label[for="id_stat_Non-Precedential"]'
        )
        self.assertNotIn('(0)', prec_count.text)
        self.assertNotIn('(0)', non_prec_count.text)

        # Even though she notices all jurisdictions were included in her search
        self.assert_text_in_body('All Jurisdictions Selected')

        # But she also notices the option to select and include
        # non_precedential results. She checks the box.
        non_prec.click()

        # Nothing happens yet.
        ## TODO: this is hacky for now...just make sure result count is same
        self.assertEqual(first_count, self.extract_result_count_from_serp())

        # She goes ahead and clicks the Search button again to resubmit
        self.browser.find_element_by_id('search-button').click()

        # She didn't change the query, so the search box should still look
        # the same (which is blank)
        self.assertEqual(
            self.browser.find_element_by_id('id_q').get_attribute('value'),
            u''
        )

        # And now she notices her result set increases thanks to adding in
        # those other opinion types!
        second_count = self.extract_result_count_from_serp()
        self.assertTrue(second_count > first_count)

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
