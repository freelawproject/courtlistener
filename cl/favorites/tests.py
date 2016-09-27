import time

from django.core.urlresolvers import reverse
from django.test import Client, TestCase
from selenium import webdriver
from timeout_decorator import timeout_decorator

from cl.favorites.models import Favorite
from cl.tests.base import BaseSeleniumTest, DESKTOP_WINDOW


class FavoriteTest(TestCase):
    fixtures = ['authtest_data.json', 'test_objects_search.json',
                'judge_judy.json', 'test_objects_audio.json']

    def setUp(self):
        # Set up some handy variables
        self.client = Client()
        self.fave_cluster_params = {
            'cluster_id': 1,
            'name': 'foo',
            'notes': 'testing notes',
        }
        self.fave_audio_params = {
            'audio_id': 1,
            'name': 'foo',
            'notes': 'testing notes',
        }

    def test_create_fave(self):
        """Can we create a fave by sending a post?"""
        self.client.login(username='pandora', password='password')
        for params in [self.fave_cluster_params, self.fave_audio_params]:
            r = self.client.post(
                reverse('save_or_update_favorite'),
                params,
                follow=True,
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
            self.assertEqual(r.status_code, 200)
            self.assertIn('It worked', r.content)

        # And can we delete them?
        for params in [self.fave_cluster_params, self.fave_audio_params]:
            r = self.client.post(
                reverse('delete_favorite'),
                params,
                follow=True,
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn('It worked', r.content)
        self.client.logout()


class UserFavoritesTest(BaseSeleniumTest):
    """
    Functionally test all aspects of favoriting Opinions and Oral Arguments
    including CRUD related operations of a user's favorites.
    """

    fixtures = ['test_court.json', 'authtest_data.json', 'judge_judy.json',
                'test_objects_search.json', 'favorites.json']

    @timeout_decorator.timeout(45)
    def test_anonymous_user_is_prompted_when_favoriting_an_opinion(self):
        # Clean up favorites to start
        Favorite.objects.all().delete()

        # Dora needs to do some research, so she fires up CL and performs
        # an initial query on her subject: Lissner
        self.browser.get(self.server_url)
        search_box = self.browser.find_element_by_id('id_q')
        search_box.send_keys('lissner\n')

        # She looks over the results and sees one in particular possibly of
        # interest so she clicks on the title
        articles = self.browser.find_elements_by_tag_name('article')
        self.assertTrue(len(articles) == 1, 'Should have 1 result')

        title_anchor = articles[0].find_elements_by_tag_name('a')[0]
        self.assertNotEqual(title_anchor.text.strip(), '')
        title_anchor.click()

        # On the detail page she now sees it might be useful later, so she
        # clicks on the little star next to the result result title
        self.assert_text_in_body('Back to Search Results')
        title = self.browser.find_element_by_css_selector('article h2').text
        star = self.browser.find_element_by_id('favorites-star')
        self.assertEqual(
                star.get_attribute('title').strip(),
                'Save this record as a favorite in your profile'
        )
        star.click()

        # Oops! She's not signed in and she sees a prompt telling her as such
        link = self.browser.find_element_by_css_selector('#modal-logged-out a')
        self.assertIn('Sign in or register to save a favorite', link.text)
        link.click()

        # Clicking it brings her to the sign in page
        self.assert_text_in_body('Sign in')
        self.assert_text_in_body('Username')
        self.assert_text_in_body('Password')

        # She logs in
        self.browser.find_element_by_id('username').send_keys('pandora')
        self.browser.find_element_by_id('password').send_keys('password\n')

        # And is brought back to that item!
        self.assert_text_in_body(title.strip())

        # Clicking the star now brings up the "Save Favorite" dialog. Nice!
        star = self.browser.find_element_by_id('favorites-star')
        star.click()

        self.browser.find_element_by_id('modal-save-favorite')
        modal_title = self.browser.find_element_by_id('save-favorite-title')
        self.assertIn('Save Favorite', modal_title.text)

    @timeout_decorator.timeout(45)
    def test_logged_in_user_can_save_favorite(self):
        # Meta: assure no Faves even if part of fixtures
        Favorite.objects.all().delete()

        # Dora goes to CL, logs in, and does a search on her topic of interest
        self.browser.get(self.server_url)
        self.attempt_sign_in('pandora', 'password')

        search_box = self.browser.find_element_by_id('id_q')
        search_box.send_keys('lissner\n')

        # Drilling into the result she's interested brings her to the details
        # TODO: Candidate for refactor
        articles = self.browser.find_elements_by_tag_name('article')
        title_anchor = articles[0].find_elements_by_tag_name('a')[0]
        search_title = title_anchor.text.strip()
        self.assertNotEqual(search_title, '')
        title_anchor.click()

        # She has used CL before and knows to click the star to favorite it
        self.assert_text_in_body('Back to Search Results')
        star = self.browser.find_element_by_id('favorites-star')
        self.assertEqual(
                star.get_attribute('title').strip(),
                'Save this record as a favorite in your profile'
        )
        self.assertIn('gray', star.get_attribute('class'))
        self.assertNotIn('gold', star.get_attribute('class'))
        star.click()

        # She is prompted to "Save Favorite". She notices the title is already
        # populated with the original title from the search and there's an
        # empty notes field for her to add whatever she wants. She adds a note
        # to help her remember what was interesting about this result.
        title = self.browser.find_element_by_id('save-favorite-title')
        self.assertIn('Save Favorite', title.text.strip())

        name_field = self.browser.find_element_by_id('save-favorite-name-field')
        short_title = name_field.get_attribute('value')
        self.assertIn(short_title, search_title)
        notes = self.browser.find_element_by_id('save-favorite-notes-field')
        notes.send_keys('Hey, Dora. Remember something important!')

        # She clicks 'Save'
        self.browser.find_element_by_id('saveFavorite').click()

        # She now sees the star is full on yellow implying it's a fave!
        time.sleep(1)  # Selenium is sometimes faster than JS.
        star = self.browser.find_element_by_id('favorites-star')
        self.assertIn('gold', star.get_attribute('class'))
        self.assertNotIn('gray', star.get_attribute('class'))

        # She closes her browser and goes to the gym for a bit since it's
        # always leg day amiright
        self.resetBrowser()
        self.browser.set_window_size(*DESKTOP_WINDOW)

        # When she returns, she signs back into CL and wants to pull up
        # that favorite again, so she goes to Favorites under the Profile menu
        self.browser.get(self.server_url)
        self.attempt_sign_in('pandora', 'password')

        # TODO: Refactor. Same code used in
        #       test_basic_homepage_search_and_signin_and_signout
        profile_dropdown = self.browser. \
            find_elements_by_css_selector('a.dropdown-toggle')[0]
        self.assertEqual(profile_dropdown.text.strip(), u'Profile')

        dropdown_menu = self.browser. \
            find_element_by_css_selector('ul.dropdown-menu')
        self.assertIsNone(dropdown_menu.get_attribute('display'))

        profile_dropdown.click()

        favorites = self.browser.find_element_by_link_text('Favorites')
        favorites.click()

        # The case is right there with the same name and notes she gave it!
        # There are columns that show the names and notes of her favorites
        # Along with options to Edit or Delete each favorite!
        self.assertIn('Favorites', self.browser.title)
        table = self.browser.find_element_by_css_selector('.settings-table')
        table_header = table.find_element_by_tag_name('thead')
        [
            self.assertIn(heading, table_header.text)
            for heading in ('Name', 'Notes')
            ]

        already_found = False
        for tr in table.find_elements_by_tag_name('tr'):
            if short_title in tr.text:
                if already_found:
                    self.fail('Title appears twice!')
                else:
                    self.assertIn(
                            'Hey, Dora. Remember something important!',
                            tr.text
                    )
                    self.assertIn('Edit / Delete', tr.text)
                    already_found = True

        # Clicking the name of the favorite brings her right back to the details
        link = table.find_element_by_link_text(short_title)
        link.click()

        self.assertIn(short_title, self.browser.title)
        self.assert_text_in_body(short_title)
        self.assert_text_in_body('Back to Home Page')

    @timeout_decorator.timeout(45)
    def test_user_can_change_favorites(self):
        # Dora already has some favorites and she logs in and pulls them up
        self.browser.get(self.server_url)
        self.attempt_sign_in('pandora', 'password')

        profile_dropdown = self.browser. \
            find_elements_by_css_selector('a.dropdown-toggle')[0]
        self.assertEqual(profile_dropdown.text.strip(), u'Profile')

        dropdown_menu = self.browser. \
            find_element_by_css_selector('ul.dropdown-menu')
        self.assertIsNone(dropdown_menu.get_attribute('display'))

        profile_dropdown.click()

        favorites = self.browser.find_element_by_link_text('Favorites')
        favorites.click()

        # She sees an edit link next to one of them and clicks it
        self.assertIn('Favorites', self.browser.title)
        self.assert_text_in_body('Totes my Notes 2')  # in favorites.json
        edit_link = self.browser.find_element_by_link_text('Edit / Delete')
        edit_link.click()

        # Greeted with an "Edit This Favorite" dialog, she fixes a typo in
        # the name and notes fields
        modal = self.browser.find_element_by_id('modal-save-favorite')
        self.assertIn('Edit This Favorite', modal.text)
        name = modal.find_element_by_id('save-favorite-name-field')
        notes = modal.find_element_by_id('save-favorite-notes-field')
        # -- via favorites.json[pk=1]
        self.assertEqual(
                name.get_attribute('value'),
                'Formerly known as \"case name cluster 3\"'
        )
        self.assertEqual(
                notes.get_attribute('value'),
                'Totes my Notes 2'
        )

        name.clear()
        name.send_keys('Renamed Favorite')
        notes.clear()
        notes.send_keys('Modified Notes')

        # She clicks Save
        button = modal.find_element_by_id('saveFavorite')
        self.assertIn('Save', button.text)
        button.click()

        # And notices the change on the page immediately
        time.sleep(0.5)  # Selenium is too fast.
        self.assertIn('Favorites', self.browser.title)
        self.assert_text_in_body('Renamed Favorite')
        self.assert_text_in_body('Modified Notes')
        self.assert_text_not_in_body('case name cluster 3')
        self.assert_text_not_in_body('Totes my Notes 2')

        # Skeptical, she hits refresh to be sure
        self.browser.refresh()
        self.assert_text_in_body('Renamed Favorite')
        self.assert_text_in_body('Modified Notes')
