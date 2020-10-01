import time

from django.urls import reverse
from django.test import Client, TestCase
from rest_framework.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_200_OK,
)
from rest_framework.test import APITestCase
from timeout_decorator import timeout_decorator

from cl.favorites.models import Favorite, DocketTag, UserTag
from cl.search.views import get_homepage_stats
from cl.tests.base import BaseSeleniumTest, SELENIUM_TIMEOUT
from cl.tests.utils import make_client


class FavoriteTest(TestCase):
    fixtures = [
        "test_court.json",
        "authtest_data.json",
        "test_objects_search.json",
        "judge_judy.json",
        "test_objects_audio.json",
    ]

    def setUp(self):
        # Set up some handy variables
        self.client = Client()
        self.fave_cluster_params = {
            "cluster_id": 1,
            "name": "foo",
            "notes": "testing notes",
        }
        self.fave_audio_params = {
            "audio_id": 1,
            "name": "foo",
            "notes": "testing notes",
        }

    def test_create_fave(self):
        """Can we create a fave by sending a post?"""
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        for params in [self.fave_cluster_params, self.fave_audio_params]:
            r = self.client.post(
                reverse("save_or_update_favorite"),
                params,
                follow=True,
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(r.status_code, 200)
            self.assertIn("It worked", r.content)

        # And can we delete them?
        for params in [self.fave_cluster_params, self.fave_audio_params]:
            r = self.client.post(
                reverse("delete_favorite"),
                params,
                follow=True,
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("It worked", r.content)
        self.client.logout()


class UserFavoritesTest(BaseSeleniumTest):
    """
    Functionally test all aspects of favoriting Opinions and Oral Arguments
    including CRUD related operations of a user's favorites.
    """

    fixtures = [
        "test_court.json",
        "authtest_data.json",
        "judge_judy.json",
        "test_objects_search.json",
        "favorites.json",
    ]

    def setUp(self):
        get_homepage_stats.invalidate()
        super(UserFavoritesTest, self).setUp()

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_anonymous_user_is_prompted_when_favoriting_an_opinion(self):
        # Clean up favorites to start
        Favorite.objects.all().delete()

        # Dora needs to do some research, so she fires up CL and performs
        # an initial query on her subject: Lissner
        self.browser.get(self.live_server_url)
        search_box = self.browser.find_element_by_id("id_q")
        search_box.send_keys("lissner")
        search_box.submit()

        # She looks over the results and sees one in particular possibly of
        # interest so she clicks on the title
        articles = self.browser.find_elements_by_tag_name("article")
        self.assertTrue(len(articles) == 1, "Should have 1 result")

        title_anchor = articles[0].find_elements_by_tag_name("a")[0]
        self.assertNotEqual(title_anchor.text.strip(), "")
        title_anchor.click()

        # On the detail page she now sees it might be useful later, so she
        # clicks on the little star next to the result result title
        title = self.browser.find_element_by_css_selector("article h2").text
        star = self.browser.find_element_by_id("favorites-star")
        self.assertEqual(
            star.get_attribute("title").strip(),
            "Save this record as a favorite in your profile",
        )
        star.click()

        # Oops! She's not signed in and she sees a prompt telling her as such
        link = self.browser.find_element_by_css_selector("#modal-logged-out a")
        self.assertIn("Sign In", link.text)
        link.click()

        # Clicking it brings her to the sign in page
        self.assert_text_in_node("Sign in", "body")
        self.assert_text_in_node("Username", "body")
        self.assert_text_in_node("Password", "body")

        # She logs in
        self.browser.find_element_by_id("username").send_keys("pandora")
        self.browser.find_element_by_id("password").send_keys("password")
        self.browser.find_element_by_id("password").submit()

        # And is brought back to that item!
        self.assert_text_in_node(title.strip(), "body")

        # Clicking the star now brings up the "Save Favorite" dialog. Nice!
        star = self.browser.find_element_by_id("favorites-star")
        star.click()

        self.browser.find_element_by_id("modal-save-favorite")
        modal_title = self.browser.find_element_by_id("save-favorite-title")
        self.assertIn("Save Favorite", modal_title.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_logged_in_user_can_save_favorite(self):
        # Meta: assure no Faves even if part of fixtures
        Favorite.objects.all().delete()

        # Dora goes to CL, logs in, and does a search on her topic of interest
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        search_box = self.browser.find_element_by_id("id_q")
        search_box.send_keys("lissner")
        search_box.submit()

        # Drilling into the result she's interested brings her to the details
        # TODO: Candidate for refactor
        articles = self.browser.find_elements_by_tag_name("article")
        title_anchor = articles[0].find_elements_by_tag_name("a")[0]
        search_title = title_anchor.text.strip()
        self.assertNotEqual(search_title, "")
        title_anchor.click()

        # She has used CL before and knows to click the star to favorite it
        star = self.browser.find_element_by_id("favorites-star")
        self.assertEqual(
            star.get_attribute("title").strip(),
            "Save this record as a favorite in your profile",
        )
        self.assertIn("gray", star.get_attribute("class"))
        self.assertNotIn("gold", star.get_attribute("class"))
        star.click()

        # She is prompted to "Save Favorite". She notices the title is already
        # populated with the original title from the search and there's an
        # empty notes field for her to add whatever she wants. She adds a note
        # to help her remember what was interesting about this result.
        title = self.browser.find_element_by_id("save-favorite-title")
        self.assertIn("Save Favorite", title.text.strip())

        name_field = self.browser.find_element_by_id(
            "save-favorite-name-field"
        )
        short_title = name_field.get_attribute("value")
        self.assertIn(short_title, search_title)
        notes = self.browser.find_element_by_id("save-favorite-notes-field")
        notes.send_keys("Hey, Dora. Remember something important!")

        # She clicks 'Save'
        self.browser.find_element_by_id("saveFavorite").click()

        # She now sees the star is full on yellow implying it's a fave!
        time.sleep(1)  # Selenium is sometimes faster than JS.
        star = self.browser.find_element_by_id("favorites-star")
        self.assertIn("gold", star.get_attribute("class"))
        self.assertNotIn("gray", star.get_attribute("class"))

        # She closes her browser and goes to the gym for a bit since it's
        # always leg day amiright
        self.reset_browser()

        # When she returns, she signs back into CL and wants to pull up
        # that favorite again, so she goes to Favorites under the Profile menu
        self.get_url_and_wait(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        # TODO: Refactor. Same code used in
        #       test_basic_homepage_search_and_signin_and_signout
        profile_dropdown = self.browser.find_elements_by_css_selector(
            "a.dropdown-toggle"
        )[0]
        self.assertEqual(profile_dropdown.text.strip(), "Profile")

        dropdown_menu = self.browser.find_element_by_css_selector(
            "ul.dropdown-menu"
        )
        self.assertIsNone(dropdown_menu.get_attribute("display"))

        profile_dropdown.click()
        time.sleep(1)
        self.click_link_for_new_page("Favorites")

        # The case is right there with the same name and notes she gave it!
        # There are columns that show the names and notes of her favorites
        # Along with options to Edit or Delete each favorite!
        self.assertIn("Favorites", self.browser.title)
        table = self.browser.find_element_by_css_selector(".settings-table")
        table_header = table.find_element_by_tag_name("thead")
        # Select the opinions pill
        opinions_pill = self.browser.find_element_by_link_text("Opinions 1")
        opinions_pill.click()
        [
            self.assertIn(heading, table_header.text)
            for heading in ("Name", "Notes")
        ]

        already_found = False
        for tr in table.find_elements_by_tag_name("tr"):
            if short_title in tr.text:
                if already_found:
                    self.fail("Title appears twice!")
                else:
                    self.assertIn(
                        "Hey, Dora. Remember something important!", tr.text
                    )
                    self.assertIn("Edit / Delete", tr.text)
                    already_found = True

        # Clicking the name of the favorite brings her right back to the details
        self.click_link_for_new_page(short_title)

        self.assertIn(short_title, self.browser.title)
        self.assert_text_in_node(short_title, "body")

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_user_can_change_favorites(self):
        # Dora already has some favorites and she logs in and pulls them up
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        profile_dropdown = self.browser.find_elements_by_css_selector(
            "a.dropdown-toggle"
        )[0]
        self.assertEqual(profile_dropdown.text.strip(), "Profile")

        dropdown_menu = self.browser.find_element_by_css_selector(
            "ul.dropdown-menu"
        )
        self.assertIsNone(dropdown_menu.get_attribute("display"))

        profile_dropdown.click()

        favorites = self.browser.find_element_by_link_text("Favorites")
        favorites.click()

        # She sees an edit link next to one of them and clicks it
        self.assertIn("Favorites", self.browser.title)
        # Select the opinions pill
        opinions_pill = self.browser.find_element_by_link_text("Opinions 1")
        opinions_pill.click()
        self.assert_text_in_node(
            "Totes my Notes 2", "body"
        )  # in favorites.json
        edit_link = self.browser.find_element_by_link_text("Edit / Delete")
        edit_link.click()

        # Greeted with an "Edit This Favorite" dialog, she fixes a typo in
        # the name and notes fields
        self.assert_text_in_node_by_id(
            "Edit This Favorite", "modal-save-favorite"
        )
        modal = self.find_element_by_id(self.browser, "modal-save-favorite")
        name = self.find_element_by_id(modal, "save-favorite-name-field")
        notes = self.find_element_by_id(modal, "save-favorite-notes-field")
        # -- via favorites.json[pk=1]
        self.assertEqual(
            name.get_attribute("value"),
            'Formerly known as "case name cluster 3"',
        )
        self.assertEqual(notes.get_attribute("value"), "Totes my Notes 2")

        name.clear()
        name.send_keys("Renamed Favorite")
        notes.clear()
        notes.send_keys("Modified Notes")

        # She clicks Save
        button = modal.find_element_by_id("saveFavorite")
        self.assertIn("Save", button.text)
        button.click()

        # And notices the change on the page immediately
        time.sleep(0.5)  # Selenium is too fast.
        self.assertIn("Favorites", self.browser.title)
        self.assert_text_in_node("Renamed Favorite", "body")
        self.assert_text_in_node("Modified Notes", "body")
        self.assert_text_not_in_node("case name cluster 3", "body")
        self.assert_text_not_in_node("Totes my Notes 2", "body")

        # Skeptical, she hits refresh to be sure
        self.browser.refresh()
        # Select the opinions pill
        opinions_pill = self.browser.find_element_by_link_text("Opinions 1")
        opinions_pill.click()
        self.assert_text_in_node("Renamed Favorite", "body")
        self.assert_text_in_node("Modified Notes", "body")


class APITests(APITestCase):
    """Check that tags are created correctly and blocked correctly via APIs"""

    fixtures = [
        "authtest_data.json",
        "judge_judy.json",
        "test_objects_search.json",
    ]

    def setUp(self):
        self.tag_path = reverse("UserTag-list", kwargs={"version": "v3"})
        self.docket_path = reverse("DocketTag-list", kwargs={"version": "v3"})
        self.client_id = 1001
        self.client = make_client(self.client_id)
        self.client2 = make_client(1002)

    def tearDown(cls):
        UserTag.objects.all().delete()
        DocketTag.objects.all().delete()

    def make_a_good_tag(self, client, tag_name="taggy-tag"):
        data = {
            "name": tag_name,
        }
        return client.post(self.tag_path, data, format="json")

    def tag_a_docket(self, client, docket_id, tag_id):
        data = {
            "docket": docket_id,
            "tag": tag_id,
        }
        return client.post(self.docket_path, data, format="json")

    def test_make_a_tag(self):
        # Make a simple tag
        response = self.make_a_good_tag(self.client)
        self.assertEqual(response.status_code, HTTP_201_CREATED)

        # Link it to the docket
        tag_id = response.json()["id"]
        docket_to_tag_id = 1
        response = self.tag_a_docket(self.client, docket_to_tag_id, tag_id)
        self.assertEqual(response.status_code, HTTP_201_CREATED)

        # And does everything make sense?
        tag = UserTag.objects.get(pk=tag_id)
        tagged_dockets = tag.dockets.all()
        self.assertEqual(tagged_dockets[0].id, docket_to_tag_id)

    def test_failing_slug(self):
        data = {
            "name": "tag with space",
        }
        response = self.client.post(self.tag_path, data, format="json")
        self.assertEqual(response.status_code, HTTP_400_BAD_REQUEST)

    def test_rename_tag_via_put(self):
        response = self.make_a_good_tag(self.client)
        response_data = response.json()
        tag_id = response_data["id"]
        old_name = response_data["name"]
        new_name = "super-taggy-tag"

        # Check name before PUT
        tag = UserTag.objects.get(pk=tag_id)
        self.assertEqual(tag.name, old_name)

        # Check name after the PUT
        put_path = reverse(
            "UserTag-detail", kwargs={"version": "v3", "pk": tag_id}
        )
        response = self.client.put(put_path, {"name": new_name}, format="json")
        self.assertEqual(response.status_code, HTTP_200_OK)
        tag.refresh_from_db()
        self.assertEqual(tag.name, new_name)

    def test_list_users_tags(self):
        """Cam we get a user's tags (and not other users tags)?"""
        # make some tags for some users
        self.make_a_good_tag(self.client, tag_name="foo")
        self.make_a_good_tag(self.client, tag_name="foo2")
        # This tag should not show up in self.client's results
        self.make_a_good_tag(self.client2, tag_name="foo2")

        # All tags for the user
        response = self.client.get(self.tag_path)
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(response.json()["count"], 2)

        # Prefix query
        response = self.client.get(self.tag_path, {"name__startswith": "foo"})
        self.assertEqual(response.json()["count"], 2)
        response = self.client.get(self.tag_path, {"name__startswith": "foo2"})
        self.assertEqual(response.json()["count"], 1)

    def test_can_users_only_see_own_tags_or_public_ones(self):
        # Use two users to create two tags
        self.make_a_good_tag(self.client, tag_name="foo")
        self.make_a_good_tag(self.client2, tag_name="foo2")

        # The user should only be able to see one so far (their own)
        response = self.client.get(self.tag_path)
        self.assertEqual(response.json()["count"], 1)

        # But then the second user names theirs public
        UserTag.objects.filter(name="foo2").update(published=True)

        # And now self.client can see two tags
        response = self.client.get(self.tag_path)
        self.assertEqual(response.json()["count"], 2)

        # And if they want to, they can just show their own
        response = self.client.get(self.tag_path, {"user": self.client_id})
        self.assertEqual(response.json()["count"], 1)

    def test_use_a_tag_thats_not_yours(self):
        # self.client makes a tag. self.client2 tries to use it
        response = self.make_a_good_tag(self.client, tag_name="foo")
        tag_id = response.json()["id"]
        docket_to_tag_id = 1
        response = self.tag_a_docket(self.client, docket_to_tag_id, tag_id)
        self.assertEqual(response.status_code, HTTP_201_CREATED)

        response = self.tag_a_docket(self.client2, docket_to_tag_id, tag_id)
        self.assertEqual(response.status_code, HTTP_400_BAD_REQUEST)

        # Same as above, but with a public tag
        UserTag.objects.filter(pk=tag_id).update(published=True)
        response = self.tag_a_docket(self.client2, docket_to_tag_id, tag_id)
        self.assertEqual(response.status_code, HTTP_400_BAD_REQUEST)

    def test_can_only_see_your_tag_associations(self):
        # Make a tag, and tag a docket with it
        response = self.make_a_good_tag(self.client, tag_name="foo")
        tag_id = response.json()["id"]
        docket_to_tag_id = 1
        self.tag_a_docket(self.client, docket_to_tag_id, tag_id)

        # Check that client2 can't see that association
        response = self.client2.get(self.docket_path)
        self.assertEqual(response.json()["count"], 0)

        # But self.client *can*.
        response = self.client.get(self.docket_path)
        self.assertEqual(response.json()["count"], 1)

        # Making it a public tag changes things. Now client2 can see it.
        UserTag.objects.filter(pk=tag_id).update(published=True)
        response = self.client2.get(self.docket_path)
        self.assertEqual(response.json()["count"], 1)
