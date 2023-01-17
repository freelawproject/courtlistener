import time

from django.contrib.auth.hashers import make_password
from django.test import Client
from django.urls import reverse
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
)
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.favorites.factories import NoteFactory
from cl.favorites.models import DocketTag, Note, UserTag
from cl.lib.test_helpers import SimpleUserDataMixin
from cl.search.views import get_homepage_stats
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import APITestCase, TestCase
from cl.tests.utils import make_client
from cl.users.factories import UserProfileWithParentsFactory


class NoteTest(SimpleUserDataMixin, TestCase):
    fixtures = [
        "test_court.json",
        "test_objects_search.json",
        "judge_judy.json",
        "test_objects_audio.json",
    ]

    def setUp(self) -> None:
        # Set up some handy variables
        self.client = Client()
        self.note_cluster_params = {
            "cluster_id": 1,
            "name": "foo",
            "notes": "testing notes",
        }
        self.note_audio_params = {
            "audio_id": 1,
            "name": "foo",
            "notes": "testing notes",
        }

    def test_create_note(self) -> None:
        """Can we create a note by sending a post?"""
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        for params in [self.note_cluster_params, self.note_audio_params]:
            r = self.client.post(
                reverse("save_or_update_note"),
                params,
                follow=True,
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(r.status_code, 200)
            self.assertIn("It worked", r.content.decode())

        # And can we delete them?
        for params in [self.note_cluster_params, self.note_audio_params]:
            r = self.client.post(
                reverse("delete_note"),
                params,
                follow=True,
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("It worked", r.content.decode())
        self.client.logout()


class UserNotesTest(BaseSeleniumTest):
    """
    Functionally test all aspects of favoriting Opinions and Oral Arguments
    including CRUD related operations of a user's notes.
    """

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
    ]

    def setUp(self) -> None:
        get_homepage_stats.invalidate()
        self.f = NoteFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )
        super(UserNotesTest, self).setUp()

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_anonymous_user_is_prompted_when_favoriting_an_opinion(
        self,
    ) -> None:
        # Clean up notes to start
        Note.objects.all().delete()

        # Dora needs to do some research, so she fires up CL and performs
        # an initial query on her subject: Lissner
        self.browser.get(self.live_server_url)
        search_box = self.browser.find_element(By.ID, "id_q")
        search_box.send_keys("lissner")
        search_box.submit()

        # She looks over the results and sees one in particular possibly of
        # interest so she clicks on the title
        articles = self.browser.find_elements(By.TAG_NAME, "article")
        self.assertTrue(len(articles) == 1, "Should have 1 result")

        title_anchor = articles[0].find_elements(By.TAG_NAME, "a")[0]
        self.assertNotEqual(title_anchor.text.strip(), "")
        title_anchor.click()

        # On the detail page she now sees it might be useful later, so she
        # clicks on the little star next to the result result title
        title = self.browser.find_element(By.CSS_SELECTOR, "article h2").text
        star = self.browser.find_element(By.ID, "add-note-button")
        self.assertEqual(
            star.get_attribute("title").strip(),
            "Save this record as a note in your profile",
        )
        star.click()

        # Oops! She's not signed in and she sees a prompt telling her as such
        link = self.browser.find_element(
            By.CSS_SELECTOR, "#modal-logged-out a"
        )
        self.assertIn("Sign In", link.text)
        link.click()

        # Clicking it brings her to the sign in page
        self.assert_text_in_node("Sign in", "body")
        self.assert_text_in_node("Username", "body")
        self.assert_text_in_node("Password", "body")

        # She logs in
        self.browser.find_element(By.ID, "username").send_keys("pandora")
        self.browser.find_element(By.ID, "password").send_keys("password")
        self.browser.find_element(By.ID, "password").submit()

        # And is brought back to that item!
        self.assert_text_in_node(title.strip(), "body")

        # Clicking the star now brings up the "Save Note" dialog. Nice!
        star = self.browser.find_element(By.ID, "add-note-button")
        star.click()

        self.browser.find_element(By.ID, "modal-save-note")
        modal_title = self.browser.find_element(By.ID, "save-note-title")
        self.assertIn("Save Note", modal_title.text)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_logged_in_user_can_save_note(self) -> None:
        # Meta: assure no Faves even if part of fixtures
        Note.objects.all().delete()

        # Dora goes to CL, logs in, and does a search on her topic of interest
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        search_box = self.browser.find_element(By.ID, "id_q")
        search_box.send_keys("lissner")
        search_box.submit()

        # Drilling into the result she's interested brings her to the details
        # TODO: Candidate for refactor
        articles = self.browser.find_elements(By.TAG_NAME, "article")
        title_anchor = articles[0].find_elements(By.TAG_NAME, "a")[0]
        search_title = title_anchor.text.strip()
        self.assertNotEqual(search_title, "")
        title_anchor.click()

        # She has used CL before and knows to click the notes button save a note
        star = self.browser.find_element(By.ID, "add-note-button")
        self.assertEqual(
            star.get_attribute("title").strip(),
            "Save this record as a note in your profile",
        )
        self.assertIn("btn-success", star.get_attribute("class"))
        self.assertNotIn("btn-danger", star.get_attribute("class"))
        star.click()

        # She is prompted to "Save Note". She notices the title is already
        # populated with the original title from the search and there's an
        # empty notes field for her to add whatever she wants. She adds a note
        # to help her remember what was interesting about this result.
        title = self.browser.find_element(By.ID, "save-note-title")
        self.assertIn("Save Note", title.text.strip())

        name_field = self.browser.find_element(
            By.ID, "save-note-name-field"
        )
        short_title = name_field.get_attribute("value")
        self.assertIn(short_title, search_title)
        notes = self.browser.find_element(By.ID, "save-note-notes-field")
        notes.send_keys("Hey, Dora. Remember something important!")

        # She clicks 'Save'
        self.browser.find_element(By.ID, "saveNote").click()

        # She now sees the star is full on yellow implying it's a note!
        time.sleep(1)  # Selenium is sometimes faster than JS.
        star = self.browser.find_element(By.ID, "add-note-button")
        self.assertIn("btn-danger", star.get_attribute("class"))
        self.assertNotIn("btn-success", star.get_attribute("class"))

        # She closes her browser and goes to the gym for a bit since it's
        # always leg day amiright
        self.reset_browser()

        # When she returns, she signs back into CL and wants to pull up
        # that note again, so she goes to Notes under the Profile menu
        self.get_url_and_wait(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        # TODO: Refactor. Same code used in
        #       test_basic_homepage_search_and_signin_and_signout
        profile_dropdown = self.browser.find_elements(
            By.CSS_SELECTOR, "a.dropdown-toggle"
        )[0]
        self.assertEqual(profile_dropdown.text.strip(), "Profile")

        dropdown_menu = self.browser.find_element(
            By.CSS_SELECTOR, "ul.dropdown-menu"
        )
        self.assertIsNone(dropdown_menu.get_attribute("display"))

        profile_dropdown.click()
        time.sleep(1)
        self.click_link_for_new_page("Notes")

        # The case is right there with the same name and notes she gave it!
        # There are columns that show the names and notes of her notes
        # Along with options to Edit or Delete each note!
        self.assertIn("Notes", self.browser.title)
        table = self.browser.find_element(By.CSS_SELECTOR, ".settings-table")
        table_header = table.find_element(By.TAG_NAME, "thead")
        # Select the opinions pill
        opinions_pill = self.browser.find_element(By.LINK_TEXT, "Opinions 1")
        opinions_pill.click()
        [
            self.assertIn(heading, table_header.text)
            for heading in ("Name", "Notes")
        ]

        already_found = False
        for tr in table.find_elements(By.TAG_NAME, "tr"):
            if short_title in tr.text:
                if already_found:
                    self.fail("Title appears twice!")
                else:
                    self.assertIn(
                        "Hey, Dora. Remember something important!", tr.text
                    )
                    self.assertIn("Edit / Delete", tr.text)
                    already_found = True

        # Clicking the name of the note brings her
        # right back to the details
        self.click_link_for_new_page(short_title)

        self.assertIn(short_title, self.browser.title)
        self.assert_text_in_node(short_title, "body")

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_user_can_change_notes(self) -> None:
        # Dora already has some notes and she logs in and pulls them up
        self.browser.get(self.live_server_url)
        self.attempt_sign_in("pandora", "password")

        profile_dropdown = self.browser.find_elements(
            By.CSS_SELECTOR, "a.dropdown-toggle"
        )[0]
        self.assertEqual(profile_dropdown.text.strip(), "Profile")

        dropdown_menu = self.browser.find_element(
            By.CSS_SELECTOR, "ul.dropdown-menu"
        )
        self.assertIsNone(dropdown_menu.get_attribute("display"))

        profile_dropdown.click()

        notes = self.browser.find_element(By.LINK_TEXT, "Notes")
        notes.click()

        # She sees an edit link next to one of them and clicks it
        self.assertIn("Notes", self.browser.title)
        # Select the opinions pill
        opinions_pill = self.browser.find_element(By.LINK_TEXT, "Opinions 1")
        opinions_pill.click()
        self.assert_text_in_node(self.f.notes, "body")
        edit_link = self.browser.find_element(By.LINK_TEXT, "Edit / Delete")
        edit_link.click()

        # Greeted with an "Edit This Note" dialog, she fixes a typo in
        # the name and notes fields
        self.assert_text_in_node_by_id("Edit This Note", "modal-save-note")
        modal = self.find_element_by_id(self.browser, "modal-save-note")
        name = self.find_element_by_id(modal, "save-note-name-field")
        notes = self.find_element_by_id(modal, "save-note-notes-field")
        # -- via notes.json[pk=1]
        self.assertEqual(name.get_property("value"), self.f.name)
        self.assertEqual(notes.get_property("value"), self.f.notes)

        name.clear()
        name.send_keys("Renamed Note")
        notes.clear()
        notes.send_keys("Modified Notes")

        # She clicks Save
        button = modal.find_element(By.ID, "saveNote")
        self.assertIn("Save", button.text)
        button.click()

        # And notices the change on the page immediately
        time.sleep(0.5)  # Selenium is too fast.
        self.assertIn("Notes", self.browser.title)
        self.assert_text_in_node("Renamed Note", "body")
        self.assert_text_in_node("Modified Notes", "body")
        self.assert_text_not_in_node("case name cluster 3", "body")
        self.assert_text_not_in_node("Totes my Notes 2", "body")

        # Skeptical, she hits refresh to be sure
        self.browser.refresh()
        # Select the opinions pill
        opinions_pill = self.browser.find_element(By.LINK_TEXT, "Opinions 1")
        opinions_pill.click()
        self.assert_text_in_node("Renamed Note", "body")
        self.assert_text_in_node("Modified Notes", "body")


class APITests(APITestCase):
    """Check that tags are created correctly and blocked correctly via APIs"""

    fixtures = [
        "judge_judy.json",
        "test_objects_search.json",
    ]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.pandora = UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )
        cls.unconfirmed = UserProfileWithParentsFactory.create(
            user__username="unconfirmed_email",
            user__password=make_password("password"),
            email_confirmed=False,
        )

    def setUp(self) -> None:
        self.tag_path = reverse("UserTag-list", kwargs={"version": "v3"})
        self.docket_path = reverse("DocketTag-list", kwargs={"version": "v3"})
        self.client = make_client(self.pandora.user.pk)
        self.client2 = make_client(self.unconfirmed.user.pk)

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

    def test_make_a_tag(self) -> None:
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

    def test_failing_slug(self) -> None:
        data = {
            "name": "tag with space",
        }
        response = self.client.post(self.tag_path, data, format="json")
        self.assertEqual(response.status_code, HTTP_400_BAD_REQUEST)

    def test_rename_tag_via_put(self) -> None:
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

    def test_list_users_tags(self) -> None:
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

    def test_can_users_only_see_own_tags_or_public_ones(self) -> None:
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
        response = self.client.get(
            self.tag_path, {"user": self.pandora.user.pk}
        )
        self.assertEqual(response.json()["count"], 1)

    def test_use_a_tag_thats_not_yours(self) -> None:
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

    def test_can_only_see_your_tag_associations(self) -> None:
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
