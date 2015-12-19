# coding=utf-8
"""
Functional testing of courtlistener
"""
from cl.tests.base import BaseSeleniumTest

class UserFavoritesTest(BaseSeleniumTest):

    fixtures = ['test_court.json', 'authtest_data.json',
        'judge_judy.json', 'test_objects_search.json', 'favorites.json']

    def test_anonymous_user_is_prompted_when_favoriting_an_opinion(self):
        # Dora needs to do some research, so she fires up CL and performs
        # an initial query on her subject: Lissner
        self.browser.get(self.server_url)
        search_box = self.browser.find_element_by_id('id_q')
        search_box.send_keys('lissner\n')

        # She looks over the results and sees one in particular possibly of
        # interest so she clicks on the title
        articles = self.browser.find_elements_by_tag_name('article')
        self.assertTrue(len(articles) > 1, 'Should have more than 1 result')

        title_anchor = articles[1].find_elements_by_tag_name('a')[0]
        self.assertNotEqual(title_anchor.text.strip(), '')
        title_anchor.click()

        # On the detail page she now sees it might be useful later, so she
        # clicks on the little star next to the result result title
        self.assertIn(
            'Back to Search Results',
            self.browser.find_element_by_tag_name('body').text
        )

        star = self.browser.find_element_by_id('favorites-star')
        self.assertEqual(
            star.get_attribute('title').strip(),
            'Save this record as a favorite in your profile'
        )
        star.click()

        # Oops! She's not signed in and she sees a prompt telling her as such

        # Clicking it brings her to the sign in page

        # She logs in

        # And is brought back to that item!

        # Clicking the star now brings up the "Save Favorite" dialog. Nice!

        self.fail('finish test')

    def test_logged_in_user_can_save_favorite(self):
        # Dora goes to CL, logs in, and does a search on her topic of interest

        # Drilling into the result she's interested brings her to the details

        # She has used CL before and knows to click the star to favorite it

        # She is prompted to "Save Favorite" and gives it a title and a
        # description before clicking Save

        # She now sees the star is full on yellow implying it's a fave!

        # She closes her browser and goes to the gym for a bit since it's
        # always leg day amiright

        # When she returns, she signs back into CL and wants to pull up
        # that favorite again, so she goes to Favorites under the Profile menu

        # The case is right there with the same name and notes she gave it!

        # Clicking the name of the favorite brings her right back to the details

        self.fail('finish test')

    def test_user_can_change_favorites(self):
        # Dora already has some favorites and she logs in and pulls them up

        # She sees an edit link next to one of them and clicks it

        # Greeted with an "Edit This Favorite" dialog, she fixes a typo in
        # the name and notes fields

        # She clicks Save

        # And notices the change on the page immediately

        # Skeptical, she hits refresh to be sure

        self.fail('finish test')
