from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.urls import reverse

from cl.favorites.factories import NoteFactory
from cl.favorites.models import Note
from cl.search.factories import DocketFactory
from cl.search.models import Docket
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory

if TYPE_CHECKING:
    # Only the type stubs define this; the test client's return type.
    from django.test.client import _MonkeyPatchedWSGIResponse

HTMX = {"HX-Request": "true"}
AJAX = {"X-Requested-With": "XMLHttpRequest"}
FRAGMENT_TEMPLATE = "v2_includes/add_note/form.html"
RELOAD_NOTICE = "Please reload the page and try again."


class SaveNoteHtmxTest(TestCase):
    """Test that save_or_update_note answers htmx requests with the v2 form."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.other_user = UserFactory()
        cls.docket = DocketFactory()
        cls.content_type = ContentType.objects.get_for_model(Docket)
        cls.url = reverse("save_or_update_note")

    def setUp(self) -> None:
        self.client.force_login(self.user)

    def post(self, **overrides: str | int) -> "_MonkeyPatchedWSGIResponse":
        """Post a note for the docket as an htmx request, with fields that
        can be overridden."""
        data = {
            "content_type": self.content_type.pk,
            "object_id": self.docket.pk,
            "name": "Foo v. Bar",
            "notes": "A note",
        }
        return self.client.post(self.url, {**data, **overrides}, headers=HTMX)

    def user_notes(self, user=None):
        """The notes a user has on the docket."""
        return Note.objects.filter(
            content_type=self.content_type,
            object_id=self.docket.pk,
            user=user or self.user,
        )

    def test_creates_a_note(self) -> None:
        """Is a note saved, and the form returned ready to edit it?"""
        r = self.post()

        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(r, FRAGMENT_TEMPLATE)
        note = self.user_notes().get()
        self.assertEqual(note.name, "Foo v. Bar")
        self.assertEqual(note.notes, "A note")
        self.assertContains(r, "Edit Note")
        self.assertContains(r, reverse("delete_note"))

    def test_saved_form_keeps_the_suggested_name(self) -> None:
        """Does the form returned after a save still carry the page's
        suggested name, for a later delete?"""
        r = self.post(default_name="Suggested v. Name")

        self.assertContains(r, 'name="default_name" value="Suggested v. Name"')

    def test_updates_the_existing_note(self) -> None:
        """Does a second save change the user's note instead of adding one?"""
        note = NoteFactory.for_object(self.docket, user=self.user, name="Old")

        r = self.post(name="New name", notes="New notes")

        self.assertEqual(r.status_code, HTTPStatus.OK)
        updated = self.user_notes().get()
        self.assertEqual(updated.pk, note.pk)
        self.assertEqual(updated.name, "New name")
        self.assertEqual(updated.notes, "New notes")

    def test_leaves_other_users_notes_alone(self) -> None:
        """Does saving a note keep another user's note on the same object
        as it was?"""
        other = NoteFactory.for_object(
            self.docket, user=self.other_user, name="Theirs"
        )

        self.post()

        other.refresh_from_db()
        self.assertEqual(other.name, "Theirs")
        self.assertEqual(self.user_notes().count(), 1)
        self.assertEqual(self.user_notes(self.other_user).count(), 1)

    def test_invalid_fields_come_back_with_errors(self) -> None:
        """Are bad values answered with the form and its messages, and
        nothing saved?"""
        cases = (
            ("blank name", {"name": ""}, "This field is required."),
            (
                "long name",
                {"name": "a" * 101},
                "Ensure this value has at most 100 characters",
            ),
            (
                "long notes",
                {"notes": "a" * 501},
                "Ensure this value has at most 500 characters",
            ),
        )
        for label, overrides, message in cases:
            with self.subTest(case=label):
                r = self.post(**overrides)

                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(r, FRAGMENT_TEMPLATE)
                self.assertContains(r, message)
                self.assertNotContains(r, RELOAD_NOTICE)
                self.assertFalse(self.user_notes().exists())

    def test_unusable_object_ids_ask_for_a_reload(self) -> None:
        """Does a request that doesn't name a noteable object get the reload
        notice, and no note is saved?"""
        user_content_type = ContentType.objects.get_for_model(type(self.user))
        cases = (
            ("missing content_type", {"content_type": ""}),
            ("missing object_id", {"object_id": ""}),
            ("unknown content_type", {"content_type": 999999999}),
            ("non-numeric object_id", {"object_id": "abc"}),
            (
                "model that can't be noted",
                {"content_type": user_content_type.pk},
            ),
        )
        for label, overrides in cases:
            with self.subTest(case=label):
                r = self.post(**overrides)

                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertContains(r, RELOAD_NOTICE)
                self.assertFalse(Note.objects.exists())

    def test_a_save_that_loses_a_race_updates_the_winner(self) -> None:
        """When another request creates the note first, is this request's
        text applied to it, leaving one note?"""
        winner = NoteFactory.for_object(
            self.docket, user=self.user, name="Winner"
        )
        real_save = Note.save
        failures = []

        def save_once_then_really(note: Note, *args, **kwargs) -> None:
            """Fail the first save as the unique constraint would."""
            if not failures:
                failures.append(note)
                raise IntegrityError
            real_save(note, *args, **kwargs)

        # The first lookup saw no note, which is why this request tried to
        # create one.
        with (
            mock.patch("cl.favorites.views.get_note") as get_note,
            mock.patch.object(
                Note, "save", autospec=True, side_effect=save_once_then_really
            ),
        ):
            get_note.side_effect = [Note(), winner]
            r = self.post(name="Late edit")

        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertEqual(self.user_notes().count(), 1)
        winner.refresh_from_db()
        self.assertEqual(winner.name, "Late edit")
        self.assertContains(r, "Edit Note")

    def test_only_post_is_allowed(self) -> None:
        """Is a GET from htmx refused?"""
        r = self.client.get(self.url, headers=HTMX)

        self.assertEqual(r.status_code, HTTPStatus.METHOD_NOT_ALLOWED)


class SaveNoteLegacyTest(TestCase):
    """Test that save_or_update_note still serves the legacy modal."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.docket = DocketFactory()
        cls.content_type = ContentType.objects.get_for_model(Docket)
        cls.url = reverse("save_or_update_note")
        cls.data = {
            "content_type": cls.content_type.pk,
            "object_id": cls.docket.pk,
            "name": "Foo v. Bar",
            "notes": "A note",
        }

    def test_ajax_request_gets_plain_text(self) -> None:
        """Does an AJAX request save the note and get the legacy text?"""
        self.client.force_login(self.user)

        r = self.client.post(self.url, self.data, headers=AJAX)

        self.assertEqual(r.content.decode(), "It worked")
        self.assertTrue(Note.objects.filter(user=self.user).exists())

    def test_plain_request_is_refused(self) -> None:
        """Is a request that is neither AJAX nor htmx still a 405?"""
        self.client.force_login(self.user)

        r = self.client.post(self.url, self.data)

        self.assertEqual(r.status_code, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertFalse(Note.objects.exists())

    def test_logged_out_user_is_sent_to_sign_in(self) -> None:
        """Does the login requirement still apply to both kinds of request?"""
        for label, headers in (("htmx", HTMX), ("ajax", AJAX)):
            with self.subTest(kind=label):
                r = self.client.post(self.url, self.data, headers=headers)

                self.assertEqual(r.status_code, HTTPStatus.FOUND)
                self.assertTrue(r["Location"].startswith(reverse("sign-in")))
                self.assertFalse(Note.objects.exists())


class DeleteNoteHtmxTest(TestCase):
    """Test that delete_note answers htmx requests with the v2 form."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.other_user = UserFactory()
        cls.docket = DocketFactory()
        cls.content_type = ContentType.objects.get_for_model(Docket)
        cls.url = reverse("delete_note")

    def setUp(self) -> None:
        self.client.force_login(self.user)

    def post(self, **overrides: str | int) -> "_MonkeyPatchedWSGIResponse":
        """Delete the docket's note as an htmx request, with fields that can
        be overridden."""
        data = {
            "content_type": self.content_type.pk,
            "object_id": self.docket.pk,
            "name": "Foo v. Bar",
            "notes": "A note",
        }
        return self.client.post(self.url, {**data, **overrides}, headers=HTMX)

    def test_deletes_the_note(self) -> None:
        """Is the note deleted, and the form returned in its empty state?"""
        NoteFactory.for_object(self.docket, user=self.user)

        r = self.post()

        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(r, FRAGMENT_TEMPLATE)
        self.assertFalse(Note.objects.filter(user=self.user).exists())
        self.assertContains(r, "Add Note")
        self.assertNotContains(r, reverse("delete_note"))
        self.assertNotContains(r, RELOAD_NOTICE)

    def test_the_returned_form_can_save_again(self) -> None:
        """Does the returned form still identify the object, so the next save
        works?"""
        NoteFactory.for_object(self.docket, user=self.user)

        r = self.post()

        self.assertContains(
            r, f'name="content_type" value="{self.content_type.pk}"'
        )
        self.assertContains(r, f'name="object_id" value="{self.docket.pk}"')

    def test_the_returned_form_is_back_to_its_initial_state(self) -> None:
        """Does the form come back with Name prefilled with the page's
        suggested name and Notes empty, whatever the note held?"""
        NoteFactory.for_object(
            self.docket, user=self.user, name="Renamed", notes="Old text"
        )

        r = self.post(
            name="Renamed",
            notes="Old text",
            default_name="Suggested v. Name",
        )

        self.assertContains(r, 'value="Suggested v. Name"', count=2)
        self.assertNotContains(r, "Renamed")
        self.assertNotContains(r, "Old text")

    def test_a_long_suggested_name_is_cut_to_the_name_limit(self) -> None:
        """Is a suggested name over the limit trimmed, not shown as is?"""
        NoteFactory.for_object(self.docket, user=self.user)

        r = self.post(default_name="a" * 150)

        self.assertContains(r, f'value="{"a" * 100}"', count=2)
        self.assertNotContains(r, "a" * 101)

    def test_leaves_other_users_notes_alone(self) -> None:
        """Does deleting keep another user's note on the same object?"""
        NoteFactory.for_object(self.docket, user=self.user)
        other = NoteFactory.for_object(self.docket, user=self.other_user)

        self.post()

        self.assertTrue(Note.objects.filter(pk=other.pk).exists())

    def test_a_note_that_is_already_gone_counts_as_deleted(self) -> None:
        """Is deleting a missing note, as after a double click, answered with
        the form and no error?"""
        r = self.post()

        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(r, FRAGMENT_TEMPLATE)
        self.assertNotContains(r, RELOAD_NOTICE)

    def test_form_values_do_not_block_the_delete(self) -> None:
        """Is a note deleted even if the posted name or notes would fail
        validation?"""
        NoteFactory.for_object(self.docket, user=self.user)

        self.post(name="", notes="a" * 501)

        self.assertFalse(Note.objects.filter(user=self.user).exists())

    def test_unusable_object_ids_ask_for_a_reload(self) -> None:
        """Does a request that doesn't name a noteable object get the reload
        notice, and keep the user's note?"""
        note = NoteFactory.for_object(self.docket, user=self.user)
        user_content_type = ContentType.objects.get_for_model(type(self.user))
        cases = (
            ("missing content_type", {"content_type": ""}),
            ("missing object_id", {"object_id": ""}),
            ("unknown content_type", {"content_type": 999999999}),
            ("non-numeric object_id", {"object_id": "abc"}),
            (
                "model that can't be noted",
                {"content_type": user_content_type.pk},
            ),
        )
        for label, overrides in cases:
            with self.subTest(case=label):
                r = self.post(**overrides)

                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertContains(r, RELOAD_NOTICE)
                self.assertTrue(Note.objects.filter(pk=note.pk).exists())

    def test_only_post_is_allowed(self) -> None:
        """Is a GET from htmx refused?"""
        r = self.client.get(self.url, headers=HTMX)

        self.assertEqual(r.status_code, HTTPStatus.METHOD_NOT_ALLOWED)


class DeleteNoteLegacyTest(TestCase):
    """Test that delete_note still serves the legacy modal."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.docket = DocketFactory()
        cls.content_type = ContentType.objects.get_for_model(Docket)
        cls.url = reverse("delete_note")
        cls.data = {
            "content_type": cls.content_type.pk,
            "object_id": cls.docket.pk,
        }

    def test_ajax_request_gets_plain_text(self) -> None:
        """Does an AJAX request delete the note and get the legacy text?"""
        NoteFactory.for_object(self.docket, user=self.user)
        self.client.force_login(self.user)

        r = self.client.post(self.url, self.data, headers=AJAX)

        self.assertEqual(r.content.decode(), "It worked.")
        self.assertFalse(Note.objects.filter(user=self.user).exists())

    def test_plain_request_is_refused(self) -> None:
        """Is a request that is neither AJAX nor htmx still a 405, with the
        note kept?"""
        note = NoteFactory.for_object(self.docket, user=self.user)
        self.client.force_login(self.user)

        r = self.client.post(self.url, self.data)

        self.assertEqual(r.status_code, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertTrue(Note.objects.filter(pk=note.pk).exists())

    def test_logged_out_user_is_sent_to_sign_in(self) -> None:
        """Does the login requirement still apply to both kinds of request?"""
        note = NoteFactory.for_object(self.docket, user=self.user)
        for label, headers in (("htmx", HTMX), ("ajax", AJAX)):
            with self.subTest(kind=label):
                r = self.client.post(self.url, self.data, headers=headers)

                self.assertEqual(r.status_code, HTTPStatus.FOUND)
                self.assertTrue(r["Location"].startswith(reverse("sign-in")))
                self.assertTrue(Note.objects.filter(pk=note.pk).exists())
