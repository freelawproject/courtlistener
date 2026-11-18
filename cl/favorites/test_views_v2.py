from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.db.models import QuerySet
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

    def post(self, **overrides: str | int) -> _MonkeyPatchedWSGIResponse:
        """Post a note for the docket as an htmx request.

        Its fields can be overridden.
        """
        data = {
            "content_type": self.content_type.pk,
            "object_id": self.docket.pk,
            "name": "Foo v. Bar",
            "notes": "A note",
        }
        return self.client.post(self.url, {**data, **overrides}, headers=HTMX)

    def user_notes(self, user: User | None = None) -> QuerySet[Note]:
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

    def test_save_closes_the_dialog_and_updates_the_button(self) -> None:
        """Does a save announce itself and refresh the note button in place?"""
        r = self.post()

        self.assertEqual(r["HX-Trigger-After-Swap"], "note-saved")
        self.assertContains(r, 'hx-swap-oob="innerHTML"')
        self.assertContains(
            r, f'id="note-trigger-{self.content_type.pk}-{self.docket.pk}"'
        )
        self.assertContains(r, "Edit Note", count=2)

    def test_failed_save_keeps_the_dialog_and_the_button(self) -> None:
        """Does a failed save leave the dialog open?

        The note button must stay as it was.
        """
        cases = (
            ("blank name", {"name": ""}),
            ("missing object_id", {"object_id": ""}),
        )
        for label, overrides in cases:
            with self.subTest(case=label):
                r = self.post(**overrides)

                self.assertNotIn("HX-Trigger-After-Swap", r)
                self.assertNotContains(r, "hx-swap-oob")

    def test_saved_form_keeps_the_suggested_name(self) -> None:
        """Does the form returned after a save keep the suggested name?

        A later delete needs it.
        """
        r = self.post(default_name="Suggested v. Name")

        self.assertContains(r, 'name="default_name" value="Suggested v. Name"')

    def test_updates_the_existing_note(self) -> None:
        """Does a second save change the user's note instead of adding one?"""
        note = NoteFactory(
            content_object=self.docket, user=self.user, name="Old"
        )

        r = self.post(name="New name", notes="New notes")

        self.assertEqual(r.status_code, HTTPStatus.OK)
        updated = self.user_notes().get()
        self.assertEqual(updated.pk, note.pk)
        self.assertEqual(updated.name, "New name")
        self.assertEqual(updated.notes, "New notes")

    def test_leaves_other_users_notes_alone(self) -> None:
        """Does saving a note leave another user's note on the object alone?"""
        other = NoteFactory(
            content_object=self.docket, user=self.other_user, name="Theirs"
        )

        self.post()

        other.refresh_from_db()
        self.assertEqual(other.name, "Theirs")
        self.assertEqual(self.user_notes().count(), 1)
        self.assertEqual(self.user_notes(self.other_user).count(), 1)

    def test_invalid_fields_come_back_with_errors(self) -> None:
        """Are bad values answered with the form and its messages?

        Nothing may be saved.
        """
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
        """Does a request naming no noteable object get the reload notice?

        No note may be saved.
        """
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
        """Does a save that loses a race update the winning note?

        When another request creates the note first, this request's text
        must be applied to it, leaving one note.
        """
        winner = NoteFactory(
            content_object=self.docket, user=self.user, name="Winner"
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

    def post(self, **overrides: str | int) -> _MonkeyPatchedWSGIResponse:
        """Delete the docket's note as an htmx request.

        Its fields can be overridden.
        """
        data = {
            "content_type": self.content_type.pk,
            "object_id": self.docket.pk,
            "name": "Foo v. Bar",
            "notes": "A note",
        }
        return self.client.post(self.url, {**data, **overrides}, headers=HTMX)

    def test_deletes_the_note(self) -> None:
        """Is the note deleted, and the form returned in its empty state?"""
        NoteFactory(content_object=self.docket, user=self.user)

        r = self.post()

        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(r, FRAGMENT_TEMPLATE)
        self.assertFalse(Note.objects.filter(user=self.user).exists())
        self.assertContains(r, "Add Note")
        self.assertNotContains(r, reverse("delete_note"))
        self.assertNotContains(r, RELOAD_NOTICE)

    def test_delete_closes_the_dialog_and_updates_the_button(self) -> None:
        """Does a delete announce itself and refresh the note button?

        The button is refreshed in place, whether or not the note was still
        there.
        """
        for label, has_note in (
            ("note exists", True),
            ("already gone", False),
        ):
            with self.subTest(case=label):
                if has_note:
                    NoteFactory(content_object=self.docket, user=self.user)

                r = self.post()

                self.assertEqual(r["HX-Trigger-After-Swap"], "note-deleted")
                self.assertContains(r, 'hx-swap-oob="innerHTML"')
                self.assertContains(
                    r,
                    f'id="note-trigger-{self.content_type.pk}-{self.docket.pk}"',
                )
                self.assertContains(r, "Add Note", count=2)

    def test_failed_delete_keeps_the_dialog_and_the_button(self) -> None:
        """Does a failed delete leave the dialog open?

        The delete names no noteable object, and the note button must stay
        as it was.
        """
        r = self.post(object_id="")

        self.assertNotIn("HX-Trigger-After-Swap", r)
        self.assertNotContains(r, "hx-swap-oob")

    def test_the_returned_form_is_back_to_its_initial_state(self) -> None:
        """Does the form come back to its initial state after a delete?

        Name is prefilled with the page's suggested name and Notes is empty,
        whatever the note held, and the object is still identified so the
        next save works.
        """
        NoteFactory(
            content_object=self.docket,
            user=self.user,
            name="Renamed",
            notes="Old text",
        )

        r = self.post(
            name="Renamed",
            notes="Old text",
            default_name="Suggested v. Name",
        )

        self.assertContains(r, 'value="Suggested v. Name"', count=2)
        self.assertNotContains(r, "Renamed")
        self.assertNotContains(r, "Old text")
        self.assertContains(
            r, f'name="content_type" value="{self.content_type.pk}"'
        )
        self.assertContains(r, f'name="object_id" value="{self.docket.pk}"')

    def test_leaves_other_users_notes_alone(self) -> None:
        """Does deleting keep another user's note on the same object?"""
        NoteFactory(content_object=self.docket, user=self.user)
        other = NoteFactory(content_object=self.docket, user=self.other_user)

        self.post()

        self.assertTrue(Note.objects.filter(pk=other.pk).exists())

    def test_a_note_that_is_already_gone_counts_as_deleted(self) -> None:
        """Is deleting a missing note answered with the form and no error?

        This happens after a double click.
        """
        r = self.post()

        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(r, FRAGMENT_TEMPLATE)
        self.assertNotContains(r, RELOAD_NOTICE)

    def test_unusable_object_ids_ask_for_a_reload(self) -> None:
        """Does a request naming no noteable object get the reload notice?

        The user's note must be kept.
        """
        note = NoteFactory(content_object=self.docket, user=self.user)
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
        NoteFactory(content_object=self.docket, user=self.user)
        self.client.force_login(self.user)

        r = self.client.post(self.url, self.data, headers=AJAX)

        self.assertEqual(r.content.decode(), "It worked.")
        self.assertFalse(Note.objects.filter(user=self.user).exists())

    def test_plain_request_is_refused(self) -> None:
        """Is a request that is neither AJAX nor htmx still a 405?

        The note must be kept.
        """
        note = NoteFactory(content_object=self.docket, user=self.user)
        self.client.force_login(self.user)

        r = self.client.post(self.url, self.data)

        self.assertEqual(r.status_code, HTTPStatus.METHOD_NOT_ALLOWED)
        self.assertTrue(Note.objects.filter(pk=note.pk).exists())
