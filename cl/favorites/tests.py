import math
import time
from datetime import date, timedelta
from http import HTTPStatus
from unittest.mock import patch

import time_machine
from asgiref.sync import sync_to_async
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.cache import cache
from django.template.defaultfilters import date as template_date
from django.test import AsyncClient, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import make_naive, now
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator
from waffle.testutils import override_flag

from cl.custom_filters.templatetags.pacer import price
from cl.favorites.factories import NoteFactory, PrayerFactory
from cl.favorites.models import DocketTag, Note, Prayer, UserTag
from cl.favorites.utils import (
    create_prayer,
    delete_prayer,
    get_existing_prayers_in_bulk,
    get_lifetime_prayer_stats,
    get_prayer_counts_in_bulk,
    get_top_prayers,
    get_user_prayer_history,
    prayer_eligible,
)
from cl.lib.test_helpers import AudioTestCase, SimpleUserDataMixin
from cl.search.factories import RECAPDocumentFactory
from cl.search.views import get_homepage_stats
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import APITestCase, TestCase
from cl.tests.utils import make_client
from cl.users.factories import UserFactory, UserProfileWithParentsFactory


class NoteTest(SimpleUserDataMixin, TestCase, AudioTestCase):
    fixtures = [
        "test_court.json",
        "test_objects_search.json",
        "judge_judy.json",
    ]

    def setUp(self) -> None:
        # Set up some handy variables
        self.async_client = AsyncClient()
        self.note_cluster_params = {
            "cluster_id": 1,
            "name": "foo",
            "notes": "testing notes",
        }
        self.note_audio_params = {
            "audio_id": self.audio_1.pk,
            "name": "foo",
            "notes": "testing notes",
        }

    async def test_create_note(self) -> None:
        """Can we create a note by sending a post?"""
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        for params in [self.note_cluster_params, self.note_audio_params]:
            r = await self.async_client.post(
                reverse("save_or_update_note"),
                params,
                follow=True,
                X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(r.status_code, 200)
            self.assertIn("It worked", r.content.decode())

        # And can we delete them?
        for params in [self.note_cluster_params, self.note_audio_params]:
            r = await self.async_client.post(
                reverse("delete_note"),
                params,
                follow=True,
                X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("It worked", r.content.decode())
        await self.async_client.alogout()


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
        super().setUp()

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    @override_flag("ui_flag_for_o", False)
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
        # clicks on the little add note button next to the result title
        title = self.browser.find_element(By.CSS_SELECTOR, "article h2").text
        add_note_button = self.browser.find_element(By.ID, "add-note-button")
        self.assertEqual(
            add_note_button.get_attribute("title").strip(),
            "Save this record as a note in your profile",
        )
        add_note_button.click()

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

        # Clicking the add note button now brings up the "Save Note" dialog. Nice!
        add_note_button = self.browser.find_element(By.ID, "add-note-button")
        add_note_button.click()

        self.browser.find_element(By.ID, "modal-save-note")
        modal_title = self.browser.find_element(By.ID, "save-note-title")
        self.assertIn("Save Note", modal_title.text)

    @override_flag("ui_flag_for_o", False)
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

        # She has used CL before and knows to click the add a note button
        add_note_button = self.browser.find_element(By.ID, "add-note-button")
        self.assertEqual(
            add_note_button.get_attribute("title").strip(),
            "Save this record as a note in your profile",
        )
        add_note_icon = add_note_button.find_element(By.TAG_NAME, "i")
        self.assertNotIn("gold", add_note_icon.get_attribute("class"))
        add_note_button.click()

        # She is prompted to "Save Note". She notices the title is already
        # populated with the original title from the search and there's an
        # empty notes field for her to add whatever she wants. She adds a note
        # to help her remember what was interesting about this result.
        title = self.browser.find_element(By.ID, "save-note-title")
        self.assertIn("Save Note", title.text.strip())

        name_field = self.browser.find_element(By.ID, "save-note-name-field")
        short_title = name_field.get_attribute("value")
        self.assertIn(short_title, search_title)
        notes = self.browser.find_element(By.ID, "save-note-notes-field")
        notes.send_keys("Hey, Dora. Remember something important!")

        # She clicks 'Save'
        self.browser.find_element(By.ID, "saveNote").click()

        # She now sees the note icon is full on yellow implying it's a note!
        time.sleep(1)  # Selenium is sometimes faster than JS.
        add_note_button = self.browser.find_element(By.ID, "add-note-button")
        add_note_icon = add_note_button.find_element(By.TAG_NAME, "i")
        self.assertIn("gold", add_note_icon.get_attribute("class"))

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


class FavoritesTest(TestCase):
    """Fvorites app tests that don't require selenium"""

    def test_revert_model_excluded_field(self) -> None:
        # We can't revert an object being tracked with django-pghistory with an
        # excluded field
        tag_name = "test-tag"
        params = {"username": "kramirez"}
        test_user = UserFactory.create(
            username=params["username"],
            email="test@courtlistener.com",
        )

        # Object is created, new event object created
        test_tag = UserTag.objects.create(
            user=test_user,
            name=tag_name,
            title="Test tag",
            description="Original description",
        )

        # Update object, new event object created
        test_tag.description = "Description updated"
        test_tag.save()

        # Revert object to previous change, we use the last result because it
        # always contains the latest change
        # Trying to revert objects with untracked fields throws an exception
        with self.assertRaises(RuntimeError):
            test_tag.events.order_by("-pgh_id")[0].revert()

    def test_revert_tracked_model(self):
        # We can revert an object being tracked with django-pghistory

        # Create test object, create event object
        favorite_obj = NoteFactory.create(name="Original alert name")

        # Update object's name, create event object
        favorite_obj.name = "Updated alert name"
        favorite_obj.save()

        # Check that we updated the value
        self.assertEqual(favorite_obj.name, "Updated alert name")

        # Revert object to previous change, we use the last result because it
        # always contains the latest change
        favorite_obj = favorite_obj.events.order_by("-pgh_id")[0].revert()
        favorite_obj.refresh_from_db()

        # Check that the object name was reverted to original name
        self.assertEqual(favorite_obj.name, "Original alert name")


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

    async def make_a_good_tag(self, client, tag_name="taggy-tag"):
        data = {
            "name": tag_name,
        }
        return await client.post(self.tag_path, data, format="json")

    async def tag_a_docket(self, client, docket_id, tag_id):
        data = {
            "docket": docket_id,
            "tag": tag_id,
        }
        return await client.post(self.docket_path, data, format="json")

    async def test_make_a_tag(self) -> None:
        # Make a simple tag
        response = await self.make_a_good_tag(self.client)
        self.assertEqual(response.status_code, HTTPStatus.CREATED)

        # Link it to the docket
        tag_id = response.json()["id"]
        docket_to_tag_id = 1
        response = await self.tag_a_docket(
            self.client, docket_to_tag_id, tag_id
        )
        self.assertEqual(response.status_code, HTTPStatus.CREATED)

        # And does everything make sense?
        tag = await UserTag.objects.aget(pk=tag_id)
        tagged_dockets = await tag.dockets.all().afirst()
        self.assertEqual(tagged_dockets.id, docket_to_tag_id)

    async def test_failing_slug(self) -> None:
        data = {
            "name": "tag with space",
        }
        response = await self.client.post(self.tag_path, data, format="json")
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

    async def test_rename_tag_via_put(self) -> None:
        response = await self.make_a_good_tag(self.client)
        response_data = response.json()
        tag_id = response_data["id"]
        old_name = response_data["name"]
        new_name = "super-taggy-tag"

        # Check name before PUT
        tag = await UserTag.objects.aget(pk=tag_id)
        self.assertEqual(tag.name, old_name)

        # Check name after the PUT
        put_path = reverse(
            "UserTag-detail", kwargs={"version": "v3", "pk": tag_id}
        )
        response = await self.client.put(
            put_path, {"name": new_name}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        await tag.arefresh_from_db()
        self.assertEqual(tag.name, new_name)

    async def test_list_users_tags(self) -> None:
        """Cam we get a user's tags (and not other users tags)?"""
        # make some tags for some users
        await self.make_a_good_tag(self.client, tag_name="foo")
        await self.make_a_good_tag(self.client, tag_name="foo2")
        # This tag should not show up in self.client's results
        await self.make_a_good_tag(self.client2, tag_name="foo2")

        # All tags for the user
        response = await self.client.get(self.tag_path)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["count"], 2)

        # Prefix query
        response = await self.client.get(
            self.tag_path, {"name__startswith": "foo"}
        )
        self.assertEqual(response.json()["count"], 2)
        response = await self.client.get(
            self.tag_path, {"name__startswith": "foo2"}
        )
        self.assertEqual(response.json()["count"], 1)

    async def test_can_users_only_see_own_tags_or_public_ones(self) -> None:
        # Use two users to create two tags
        await self.make_a_good_tag(self.client, tag_name="foo")
        await self.make_a_good_tag(self.client2, tag_name="foo2")

        # The user should only be able to see one so far (their own)
        response = await self.client.get(self.tag_path)
        self.assertEqual(response.json()["count"], 1)

        # But then the second user names theirs public
        await UserTag.objects.filter(name="foo2").aupdate(published=True)

        # And now self.client can see two tags
        response = await self.client.get(self.tag_path)
        self.assertEqual(response.json()["count"], 2)

        # And if they want to, they can just show their own
        response = await self.client.get(
            self.tag_path, {"user": self.pandora.user.pk}
        )
        self.assertEqual(response.json()["count"], 1)

    async def test_use_a_tag_thats_not_yours(self) -> None:
        # self.client makes a tag. self.client2 tries to use it
        response = await self.make_a_good_tag(self.client, tag_name="foo")
        tag_id = response.json()["id"]
        docket_to_tag_id = 1
        response = await self.tag_a_docket(
            self.client, docket_to_tag_id, tag_id
        )
        self.assertEqual(response.status_code, HTTPStatus.CREATED)

        response = await self.tag_a_docket(
            self.client2, docket_to_tag_id, tag_id
        )
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        # Same as above, but with a public tag
        await UserTag.objects.filter(pk=tag_id).aupdate(published=True)
        response = await self.tag_a_docket(
            self.client2, docket_to_tag_id, tag_id
        )
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

    async def test_can_filter_tag_associations_using_docket_id(self) -> None:
        """Test filter for the docket field in the docket-tags endpoint"""

        # create a tag and use it for docket #1 and #2
        response = await self.make_a_good_tag(self.client, tag_name="foo")
        tag_id = response.json()["id"]
        response = await self.tag_a_docket(self.client, 1, tag_id)
        response = await self.tag_a_docket(self.client, 2, tag_id)

        # create another tag for docket #2
        response = await self.make_a_good_tag(self.client, tag_name="foo-2")
        tag_id = response.json()["id"]
        response = await self.tag_a_docket(self.client, 2, tag_id)

        # filter the associations using the docket id
        response = await self.client.get(self.docket_path, {"docket": 1})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["count"], 1)

        response = await self.client.get(self.docket_path, {"docket": 2})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["count"], 2)

    async def test_can_filter_tag_associations_using_user_id(self) -> None:
        """Test filter for the docket field in the docket-tags endpoint"""

        # create a two tags using client 1 and use them in docket #1
        response = await self.make_a_good_tag(self.client, tag_name="foo")
        tag_id = response.json()["id"]
        response = await self.tag_a_docket(self.client, 1, tag_id)
        response = await self.make_a_good_tag(self.client, tag_name="foo-c1")
        tag_id = response.json()["id"]
        response = await self.tag_a_docket(self.client, 1, tag_id)

        await UserTag.objects.filter(name="foo").aupdate(published=True)

        # create another tag using client 2 and use it in docket #1
        response = await self.make_a_good_tag(self.client2, tag_name="foo-c2")
        tag_id = response.json()["id"]
        response = await self.tag_a_docket(self.client2, 1, tag_id)

        await UserTag.objects.filter(name="foo-c2").aupdate(published=True)

        # query the associations(own + public) for docket #1 using client 1
        response = await self.client.get(self.docket_path, {"docket": 1})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["count"], 3)

        # query the associations(own + public) for docket #1 using client 2
        response = await self.client2.get(self.docket_path, {"docket": 1})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["count"], 2)

        # filter association using user id
        response = await self.client.get(
            self.docket_path, {"docket": 1, "tag__user": self.pandora.user.pk}
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["count"], 2)

        response = await self.client2.get(
            self.docket_path,
            {"docket": 1, "tag__user": self.unconfirmed.user.pk},
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json()["count"], 1)

    async def test_can_only_see_your_tag_associations(self) -> None:
        # Make a tag, and tag a docket with it
        response = await self.make_a_good_tag(self.client, tag_name="foo")
        tag_id = response.json()["id"]
        docket_to_tag_id = 1
        await self.tag_a_docket(self.client, docket_to_tag_id, tag_id)

        # Check that client2 can't see that association
        response = await self.client2.get(self.docket_path)
        self.assertEqual(response.json()["count"], 0)

        # But self.client *can*.
        response = await self.client.get(self.docket_path)
        self.assertEqual(response.json()["count"], 1)

        # Making it a public tag changes things. Now client2 can see it.
        await UserTag.objects.filter(pk=tag_id).aupdate(published=True)
        response = await self.client2.get(self.docket_path)
        self.assertEqual(response.json()["count"], 1)


class RECAPPrayAndPay(TestCase):

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.user_2 = UserFactory()
        cls.user_3 = UserFactory()

        cls.rd_1 = RECAPDocumentFactory(
            pacer_doc_id="98763421",
            document_number="1",
            is_available=True,
        )
        cls.rd_2 = RECAPDocumentFactory(
            pacer_doc_id="98763422",
            document_number="2",
            is_available=False,
        )

        cls.rd_3 = RECAPDocumentFactory(
            pacer_doc_id="98763423",
            document_number="3",
            is_available=False,
        )
        cls.rd_4 = RECAPDocumentFactory(
            pacer_doc_id="98763424",
            document_number="4",
            is_available=False,
        )

        cls.rd_5 = RECAPDocumentFactory(
            pacer_doc_id="98763425",
            document_number="5",
            is_available=False,
        )

        cls.rd_6 = RECAPDocumentFactory(
            pacer_doc_id="98763426",
            document_number="6",
            is_available=False,
        )

    @override_settings(ALLOWED_PRAYER_COUNT=2)
    async def test_prayer_eligible(self) -> None:
        """Does the prayer_eligible method work properly?"""

        current_time = now()
        with time_machine.travel(current_time, tick=False):
            # No user prayers in the last 24 hours yet for this user.
            user_is_eligible, _ = await prayer_eligible(self.user)
            self.assertTrue(user_is_eligible)

            # Add prays for this user.
            await sync_to_async(PrayerFactory)(
                user=self.user, recap_document=self.rd_1
            )

            user_prays = Prayer.objects.filter(user=self.user)
            self.assertEqual(await user_prays.acount(), 1)
            user_is_eligible, _ = await prayer_eligible(self.user)
            self.assertTrue(user_is_eligible)

            await sync_to_async(PrayerFactory)(
                user=self.user, recap_document=self.rd_2
            )
            self.assertEqual(await user_prays.acount(), 2)

            # After two prays (ALLOWED_PRAYER_COUNT) in the last 24 hours.
            # The user is no longer eligible to create more prays
            user_is_eligible, _ = await prayer_eligible(self.user)
            self.assertFalse(user_is_eligible)

        with time_machine.travel(
            current_time + timedelta(hours=25), tick=False
        ):
            # After more than 24 hours the user is eligible to create more prays.
            await sync_to_async(PrayerFactory)(
                user=self.user, recap_document=self.rd_3
            )
            self.assertEqual(await user_prays.acount(), 3)
            user_is_eligible, _ = await prayer_eligible(self.user)
            self.assertTrue(user_is_eligible)

    async def test_create_prayer(self) -> None:
        """Does the create_prayer method work properly?"""

        # Prayer is not created if the document is already available.
        prayer_created = await create_prayer(self.user, self.rd_1)
        self.assertEqual(prayer_created, None)

        # Prayer is created if the user eligible and RD is not available.
        prayer_created = await create_prayer(self.user, self.rd_2)
        self.assertTrue(prayer_created)

        # Ensure that a user cannot "pray" for the same document more than once
        same_prayer_created = await create_prayer(self.user, self.rd_2)
        self.assertIsNone(same_prayer_created)

    async def test_delete_prayer(self) -> None:
        """Does the delete_prayer method work properly?"""

        # Prayer is added, then deleted successfully
        prayer_created = await create_prayer(self.user, self.rd_2)
        prayer_deleted = await delete_prayer(self.user, self.rd_2)
        self.assertTrue(prayer_deleted)

        # Prayer is created, then document is made available to check that a user can't delete a prayer that has been granted
        prayer_created = await create_prayer(self.user, self.rd_6)
        self.rd_6.is_available = True
        await sync_to_async(self.rd_6.save)()
        prayer_deleted = await delete_prayer(self.user, self.rd_6)
        self.assertFalse(prayer_deleted)

        # Ensure that a user cannot delete the same prayer twice
        prayer_created = await create_prayer(self.user, self.rd_2)
        prayer_deleted = await delete_prayer(self.user, self.rd_2)
        prayer_deleted = await delete_prayer(self.user, self.rd_2)
        self.assertFalse(prayer_deleted)

    async def test_get_top_prayers_by_number(self) -> None:
        """Does the get_top_prayers method work properly?"""

        # Test top documents based on prayers count.
        current_time = now()
        with time_machine.travel(current_time, tick=False):
            await create_prayer(self.user, self.rd_2)
            await create_prayer(self.user_2, self.rd_2)
            await create_prayer(self.user_3, self.rd_2)

            await create_prayer(self.user, self.rd_4)
            await create_prayer(self.user_3, self.rd_4)

            await create_prayer(self.user_2, self.rd_3)

        prays = Prayer.objects.all()
        self.assertEqual(await prays.acount(), 6)

        top_prayers = await get_top_prayers()
        self.assertEqual(await top_prayers.acount(), 3)
        expected_top_prayers = [self.rd_2.pk, self.rd_4.pk, self.rd_3.pk]
        actual_top_prayers = [top_rd.pk async for top_rd in top_prayers]
        self.assertEqual(
            actual_top_prayers,
            expected_top_prayers,
            msg="Wrong top_prayers based on prayers count.",
        )

    async def test_get_top_prayers_by_age(self) -> None:
        """Does the get_top_prayers method work properly?"""

        # Test top documents based on prayer age.
        current_time = now()
        with time_machine.travel(
            current_time - timedelta(minutes=1), tick=False
        ):
            await create_prayer(self.user, self.rd_4)

        with time_machine.travel(
            current_time - timedelta(minutes=2), tick=False
        ):
            await create_prayer(self.user, self.rd_2)

        with time_machine.travel(
            current_time - timedelta(minutes=3), tick=False
        ):
            await create_prayer(self.user_2, self.rd_3)

        top_prayers = await get_top_prayers()
        self.assertEqual(await top_prayers.acount(), 3)
        expected_top_prayers = [self.rd_3.pk, self.rd_2.pk, self.rd_4.pk]
        actual_top_prayers = [top_rd.pk async for top_rd in top_prayers]

        self.assertEqual(
            actual_top_prayers,
            expected_top_prayers,
            msg="Wrong top_prayers based on prayers age.",
        )

    async def test_get_top_prayers_by_number_and_age(self) -> None:
        """Does the get_top_prayers method work properly?"""

        # Create prayers with different counts and ages
        current_time = now()
        with time_machine.travel(current_time - timedelta(days=5), tick=False):
            await create_prayer(self.user, self.rd_5)  # 1 prayer, 5 days old

        with time_machine.travel(current_time - timedelta(days=3), tick=False):
            await create_prayer(self.user, self.rd_2)
            await create_prayer(
                self.user_2, self.rd_2
            )  # 2 prayers, 3 days old

        with time_machine.travel(current_time - timedelta(days=1), tick=False):
            await create_prayer(self.user, self.rd_3)
            await create_prayer(self.user_2, self.rd_3)
            await create_prayer(self.user_3, self.rd_3)  # 3 prayers, 1 day old

        with time_machine.travel(current_time - timedelta(days=4), tick=False):
            await create_prayer(self.user, self.rd_4)
            await create_prayer(
                self.user_2, self.rd_4
            )  # 2 prayers, 4 days old

        top_prayers = await get_top_prayers()
        self.assertEqual(await top_prayers.acount(), 4)

        expected_top_prayers = [
            self.rd_4.pk,
            self.rd_2.pk,
            self.rd_5.pk,
            self.rd_3.pk,
        ]
        actual_top_prayers = [top_rd.pk async for top_rd in top_prayers]

        self.assertEqual(
            actual_top_prayers,
            expected_top_prayers,
            msg="Wrong top_prayers based on combined prayer count and age.",
        )

        # Compute expected geometric means
        rd_4_score = math.sqrt(2 * (4 * 3600 * 24))
        rd_2_score = math.sqrt(2 * (3 * 3600 * 24))
        rd_5_score = math.sqrt(1 * (5 * 3600 * 24))
        rd_3_score = math.sqrt(3 * (1 * 3600 * 24))

        self.assertAlmostEqual(
            top_prayers[0].geometric_mean, rd_4_score, places=2
        )
        self.assertAlmostEqual(
            top_prayers[1].geometric_mean, rd_2_score, places=2
        )
        self.assertAlmostEqual(
            top_prayers[2].geometric_mean, rd_5_score, places=2
        )
        self.assertAlmostEqual(
            top_prayers[3].geometric_mean, rd_3_score, places=2
        )

    async def test_get_user_prayer_history(self) -> None:
        """Does the get_user_prayer_history method work properly?"""
        # Prayers for user_2
        await create_prayer(self.user_2, self.rd_4)

        # Prayers for user
        await create_prayer(self.user, self.rd_2)
        prayer_rd3 = await create_prayer(self.user, self.rd_3)
        prayer_rd5 = await create_prayer(self.user, self.rd_5)

        # Verify that the initial prayer count and total cost are 0.
        count, total_cost = await get_user_prayer_history(self.user)
        self.assertEqual(count, 0)
        self.assertEqual(total_cost, 0.0)

        # Update `rd_3`'s page count and set `prayer_rd3`'s status to `GRANTED`
        self.rd_3.page_count = 2
        await self.rd_3.asave()

        prayer_rd3.status = Prayer.GRANTED
        await prayer_rd3.asave()

        # Verify that the count is 1 and total cost is 0.20.
        count, total_cost = await get_user_prayer_history(self.user)
        self.assertEqual(count, 1)
        self.assertEqual(total_cost, 0.20)

        # Update `rd_5`'s page count and set `prayer_rd5`'s status to `GRANTED`
        self.rd_5.page_count = 40
        await self.rd_5.asave()

        prayer_rd5.status = Prayer.GRANTED
        await prayer_rd5.asave()

        # Verify that the count is 2 and the total cost is now 3.20.
        count, total_cost = await get_user_prayer_history(self.user)
        self.assertEqual(count, 2)
        self.assertEqual(total_cost, 3.20)

    @patch("cl.favorites.utils.cache.aget")
    async def test_get_lifetime_prayer_stats(self, mock_cache_aget) -> None:
        """Does the get_lifetime_prayer_stats method work properly?"""
        mock_cache_aget.return_value = None

        # Update page counts for recap documents
        self.rd_2.page_count = 5
        await self.rd_2.asave()
        self.rd_3.page_count = 1
        await self.rd_3.asave()
        self.rd_4.page_count = 45
        await self.rd_4.asave()
        self.rd_5.page_count = 20
        await self.rd_5.asave()

        # Create prayer requests for the following user-document pairs:
        # - User: Recap Document 2, Recap Document 3, Recap Document 5
        # - User 2: Recap Document 2, Recap Document 3, Recap Document 4
        await create_prayer(self.user, self.rd_2)
        await create_prayer(self.user_2, self.rd_2)
        await create_prayer(self.user, self.rd_3)
        await create_prayer(self.user_2, self.rd_3)
        await create_prayer(self.user_2, self.rd_4)
        await create_prayer(self.user, self.rd_5)

        # Verify expected values for waiting prayers:
        # - Total count of 6 prayers
        # - 4 distinct documents
        # - Total cost of $5.60 (sum of individual document costs)
        prayer_stats = await get_lifetime_prayer_stats(Prayer.WAITING)
        self.assertEqual(prayer_stats.prayer_count, 6)
        self.assertEqual(prayer_stats.distinct_count, 4)
        self.assertEqual(prayer_stats.total_cost, "5.60")

        # Verify that no prayers have been granted:
        # - Zero count of granted prayers
        # - Zero distinct documents
        # - Zero total cost
        prayer_stats = await get_lifetime_prayer_stats(Prayer.GRANTED)
        self.assertEqual(prayer_stats.prayer_count, 0)
        self.assertEqual(prayer_stats.distinct_count, 0)
        self.assertEqual(prayer_stats.total_cost, "0.00")

        # rd_2 is granted.
        self.rd_2.is_available = True
        await self.rd_2.asave()

        # Verify that granting `rd_2` reduces the number of waiting prayers:
        # - Total waiting prayers should decrease by 2 (as `rd_2` had 2 prayers)
        # - Distinct documents should decrease by 1
        # - Total cost should decrease to 5.10 (excluding `rd_2`'s cost)
        prayer_stats = await get_lifetime_prayer_stats(Prayer.WAITING)
        self.assertEqual(prayer_stats.prayer_count, 4)
        self.assertEqual(prayer_stats.distinct_count, 3)
        self.assertEqual(prayer_stats.total_cost, "5.10")

        # Verify that granting `rd_2` increases the number of granted prayers:
        # - Total granted prayers should increase by 2 (as `rd_2` had 2 prayers)
        # - Distinct documents should increase by 1
        # - Total cost should increase by 0.50 (the cost of granting `rd_2`)
        prayer_stats = await get_lifetime_prayer_stats(Prayer.GRANTED)
        self.assertEqual(prayer_stats.prayer_count, 2)
        self.assertEqual(prayer_stats.distinct_count, 1)
        self.assertEqual(prayer_stats.total_cost, "0.50")

        # rd_4 is granted.
        self.rd_4.is_available = True
        await self.rd_4.asave()

        # Verify that granting `rd_4` reduces the number of waiting prayers:
        # - Total waiting prayers should decrease by 3 (2 from `rd_2` and 1 from `rd_4`)
        # - Distinct documents should decrease by 2 (`rd_2` and `rd_4`)
        # - Total cost should decrease to 2.10 (excluding costs of `rd_2` and `rd_4`)
        prayer_stats = await get_lifetime_prayer_stats(Prayer.WAITING)
        self.assertEqual(prayer_stats.prayer_count, 3)
        self.assertEqual(prayer_stats.distinct_count, 2)
        self.assertEqual(prayer_stats.total_cost, "2.10")

        # Verify that granting `rd_4` increases the number of granted prayers:
        # - Total granted prayers should increase by 3 (2 from `rd_2` and 1 from `rd_4`)
        # - Distinct documents should increase by 1 (`rd_2` and `rd_4` are now granted)
        # - Total cost should increase by 3.50 (the combined cost of `rd_2` and `rd_4`)
        prayer_stats = await get_lifetime_prayer_stats(Prayer.GRANTED)
        self.assertEqual(prayer_stats.prayer_count, 3)
        self.assertEqual(prayer_stats.distinct_count, 2)
        self.assertEqual(prayer_stats.total_cost, "3.50")

        await cache.adelete(f"prayer-stats-{Prayer.WAITING}")
        await cache.adelete(f"prayer-stats-{Prayer.GRANTED}")

    async def test_prayers_integration(self) -> None:
        """Integration test for prayers."""

        rd_6 = await sync_to_async(RECAPDocumentFactory)(
            docket_entry__entry_number=6,
            docket_entry__date_filed=date(2015, 8, 16),
            pacer_doc_id="98763427",
            document_number="1",
            is_available=False,
            page_count=10,
            description="Dismissing Case",
        )

        current_time = now()
        with time_machine.travel(current_time, tick=False):
            # Create prayers
            prayer_1 = await create_prayer(self.user, rd_6)
            await create_prayer(self.user_2, rd_6)
            await create_prayer(self.user, self.rd_4)

        # Assert number of Prayer in Waiting status.
        waiting_prays = Prayer.objects.filter(status=Prayer.WAITING)
        self.assertEqual(
            await waiting_prays.acount(),
            3,
            msg="Wrong number of waiting prayers",
        )

        # Confirm top prayers list is as expected.
        top_prayers = await get_top_prayers()
        self.assertEqual(
            await top_prayers.acount(), 2, msg="Wrong number of top prayers"
        )

        expected_top_prayers = [rd_6.pk, self.rd_4.pk]
        actual_top_prayers = [top_rd.pk async for top_rd in top_prayers]
        self.assertEqual(
            actual_top_prayers, expected_top_prayers, msg="Wrong top_prayers."
        )

        # Assert prayer_counts dict.
        prayers_counts_dict = await get_prayer_counts_in_bulk(
            [rd_6, self.rd_4]
        )
        self.assertEqual({rd_6.pk: 2, self.rd_4.pk: 1}, prayers_counts_dict)

        # Assert existing_prayers dict for user
        existing_prayers_dict = await get_existing_prayers_in_bulk(
            self.user, [rd_6, self.rd_4]
        )
        self.assertEqual(
            {rd_6.pk: True, self.rd_4.pk: True}, existing_prayers_dict
        )

        # Assert existing_prayers dict for user_2
        existing_prayers_dict = await get_existing_prayers_in_bulk(
            self.user_2, [rd_6, self.rd_4]
        )
        self.assertEqual({rd_6.pk: True}, existing_prayers_dict)

        # rd_6 is granted.
        rd_6.is_available = True
        await rd_6.asave()

        # Confirm Prayers related to rd_6 are now set to Granted status.
        self.assertEqual(
            await waiting_prays.acount(),
            1,
            msg="Wrong number of waiting prayers",
        )
        granted_prays = Prayer.objects.filter(status=Prayer.GRANTED)
        self.assertEqual(
            await granted_prays.acount(),
            2,
            msg="Wrong number of granted prayers",
        )

        # Assert that prayer granted email notifications are properly sent to users.
        self.assertEqual(
            len(mail.outbox), 2, msg="Wrong number of emails sent."
        )
        self.assertIn(
            "A document you requested is now on CourtListener",
            mail.outbox[0].subject,
        )

        email_text_content = mail.outbox[0].body
        html_content = None
        for content, content_type in mail.outbox[0].alternatives:
            if content_type == "text/html":
                html_content = content
                break

        self.assertIn(
            f"https://www.courtlistener.com{rd_6.get_absolute_url()}",
            email_text_content,
        )
        self.assertIn(
            f"You requested it on {template_date(make_naive(prayer_1.date_created), 'F j, Y')}",
            email_text_content,
        )
        self.assertIn(
            f"{len(actual_top_prayers)} people were waiting for it.",
            email_text_content,
        )
        self.assertIn(
            f"Somebody paid ${price(rd_6)}",
            email_text_content,
        )

        self.assertIn(
            f"https://www.courtlistener.com{rd_6.get_absolute_url()}",
            html_content,
        )
        self.assertIn(
            f"{len(actual_top_prayers)} people were waiting for it.",
            html_content,
        )
        self.assertIn(
            f"You requested it on {template_date(make_naive(prayer_1.date_created), 'F j, Y')}",
            html_content,
        )
        self.assertIn(
            f"Somebody paid ${price(rd_6)}",
            html_content,
        )
        email_recipients = {email.to[0] for email in mail.outbox}
        self.assertEqual(
            email_recipients, {self.user_2.email, self.user.email}
        )

        top_prayers = await get_top_prayers()
        self.assertEqual(
            await top_prayers.acount(), 1, msg="Wrong top_prayers."
        )
        self.assertEqual(
            await top_prayers.afirst(),
            self.rd_4,
            msg="The top prayer didn't match.",
        )


class PrayerAPITests(APITestCase):
    """Check that Prayer API operations work as expected."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_1 = UserFactory()
        cls.user_2 = UserFactory()

        cls.rd_1 = RECAPDocumentFactory(
            pacer_doc_id="98763421",
            document_number="1",
            is_available=True,
        )
        cls.rd_2 = RECAPDocumentFactory(
            pacer_doc_id="98763422",
            document_number="2",
            is_available=False,
        )
        cls.rd_3 = RECAPDocumentFactory(
            pacer_doc_id="98763423",
            document_number="3",
            is_available=False,
        )

    def setUp(self) -> None:
        self.prayer_path = reverse("prayer-list", kwargs={"version": "v4"})
        self.client = make_client(self.user_1.pk)
        self.client_2 = make_client(self.user_2.pk)

    async def make_a_prayer(
        self,
        client,
        recap_doc_id,
    ):
        data = {
            "recap_document": recap_doc_id,
        }
        return await client.post(self.prayer_path, data, format="json")

    async def test_make_a_prayer(self) -> None:
        """Can we make a prayer?"""

        prayer = Prayer.objects.all()
        response = await self.make_a_prayer(self.client, self.rd_1.pk)
        prayer_first = await prayer.afirst()
        self.assertIsNotNone(prayer_first)
        self.assertEqual(await prayer.acount(), 1)
        self.assertEqual(response.status_code, HTTPStatus.CREATED)

    async def test_duplicate_prayer_fails(self) -> None:
        """Ensure a user can't create multiple prayers for the same document
        and user.
        """
        await self.make_a_prayer(self.client, self.rd_1.pk)
        response = await self.make_a_prayer(self.client, self.rd_1.pk)
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

    async def test_list_users_prayers(self) -> None:
        """Can we list user's own prayers?"""

        # Make two prayers for user_1
        await self.make_a_prayer(self.client, self.rd_1.pk)
        await self.make_a_prayer(self.client, self.rd_3.id)

        # Make one prayer for user_2
        await self.make_a_prayer(self.client_2, self.rd_1.pk)

        # Get the prayers for user_1, should be 2
        response = await self.client.get(self.prayer_path)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(len(response.json()["results"]), 2)

        # Get the prayers for user_2, should be 1
        response_2 = await self.client_2.get(self.prayer_path)
        self.assertEqual(response_2.status_code, HTTPStatus.OK)
        self.assertEqual(len(response_2.json()["results"]), 1)

    async def test_delete_prayer(self) -> None:
        """Can we delete a prayer?
        Avoid users from deleting other users' prayers.
        """

        # Make two prayers for user_1
        prayer_1 = await self.make_a_prayer(self.client, self.rd_1.pk)
        prayer_2 = await self.make_a_prayer(self.client, self.rd_3.id)

        prayer = Prayer.objects.all()
        self.assertEqual(await prayer.acount(), 2)

        prayer_1_path_detail = reverse(
            "prayer-detail",
            kwargs={"pk": prayer_1.json()["id"], "version": "v4"},
        )

        # Delete the prayer for user_1
        response = await self.client.delete(prayer_1_path_detail)
        self.assertEqual(response.status_code, HTTPStatus.NO_CONTENT)
        self.assertEqual(await prayer.acount(), 1)

        prayer_2_path_detail = reverse(
            "prayer-detail",
            kwargs={"pk": prayer_2.json()["id"], "version": "v3"},
        )

        # user_2 tries to delete a user_1 prayer, it should fail
        response = await self.client_2.delete(prayer_2_path_detail)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(await prayer.acount(), 1)

    async def test_prayer_detail(self) -> None:
        """Can we get the detail for a prayer? Avoid users from getting other
        users prayers.
        """

        # Make one prayer for user_1
        prayer_1 = await self.make_a_prayer(self.client, self.rd_1.pk)
        prayer = Prayer.objects.all()
        self.assertEqual(await prayer.acount(), 1)
        prayer_1_path_detail = reverse(
            "prayer-detail",
            kwargs={"pk": prayer_1.json()["id"], "version": "v3"},
        )

        # Get the prayer detail for user_1
        response = await self.client.get(prayer_1_path_detail)
        self.assertEqual(response.status_code, HTTPStatus.OK)

        # user_2 tries to get user_1 prayer, it should fail
        response = await self.client_2.get(prayer_1_path_detail)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)

    async def test_prayer_update_fails(self) -> None:
        """PUT AND PATCH methods are restricted."""

        # Make one prayer for user_1
        prayer_1 = await self.make_a_prayer(self.client, self.rd_1.pk)
        prayer_1_path_detail = reverse(
            "prayer-detail",
            kwargs={"pk": prayer_1.json()["id"], "version": "v3"},
        )
        # PATCH not allowed
        data = {"status": 2}
        response = await self.client.patch(
            prayer_1_path_detail, data, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.METHOD_NOT_ALLOWED)

        # PUT not allowed
        data = {"status": 2, "recap_document": self.rd_1.pk}
        response = await self.client.put(
            prayer_1_path_detail, data, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.METHOD_NOT_ALLOWED)

    @override_settings(ALLOWED_PRAYER_COUNT=2)
    async def test_prayer_creation_eligibility(self):
        """Test the prayer creation eligibility and limits in the API."""
        current_time = timezone.now()
        prayers = Prayer.objects.all()

        with time_machine.travel(current_time, tick=False):
            # First prayer succeed
            response = await self.make_a_prayer(self.client, self.rd_1.pk)
            self.assertEqual(response.status_code, HTTPStatus.CREATED)
            self.assertEqual(await prayers.acount(), 1)

            # Second prayer succeed
            response = await self.make_a_prayer(self.client, self.rd_2.pk)
            self.assertEqual(response.status_code, HTTPStatus.CREATED)
            self.assertEqual(await prayers.acount(), 2)

            # Third prayer fails due to limit
            response = await self.make_a_prayer(self.client, self.rd_3.pk)
            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
            self.assertIn("maximum number of prayers", str(response.data))
            self.assertEqual(await prayers.acount(), 2)

        # After more than 24 hours the user is eligible to create more prays.
        with time_machine.travel(
            current_time + timedelta(hours=25), tick=False
        ):
            response = await self.make_a_prayer(self.client, self.rd_3.pk)
            self.assertEqual(response.status_code, HTTPStatus.CREATED)
            self.assertEqual(await prayers.acount(), 3)
