from unittest import mock

from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.contenttypes.models import ContentType
from django.template import engines
from django.test import RequestFactory
from django_cotton.compiler_regex import CottonCompiler

from cl.favorites.factories import NoteFactory
from cl.favorites.forms import NoteForm as V1NoteForm
from cl.favorites.forms import get_note_form_for
from cl.favorites.forms_v2 import NoteForm
from cl.lib.widgets import NEW_STACK_WIDGET_CLASSES
from cl.search.factories import DocketFactory
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory


class NoteFormV2Test(TestCase):
    """Test the new-stack note form used by the v2 pages."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.docket = DocketFactory()
        cls.content_type = ContentType.objects.get_for_model(cls.docket)

    def build_form(self, **overrides: str | int) -> NoteForm:
        """Build a bound form for the docket, with fields that can be
        overridden."""
        data = {
            "content_type": self.content_type.pk,
            "object_id": self.docket.pk,
            "name": "Foo v. Bar",
            "notes": "A note",
        }
        return NoteForm(data={**data, **overrides})

    def test_fields_use_new_stack_widgets(self) -> None:
        """Does the form render the new-stack widgets without legacy ids?"""
        form = NoteForm()

        self.assertEqual(
            list(form.fields),
            ["content_type", "object_id", "name", "notes", "default_name"],
        )
        for field_name, max_length in (("name", "100"), ("notes", "500")):
            with self.subTest(field=field_name):
                attrs = form.fields[field_name].widget.attrs
                self.assertEqual(attrs["class"], NEW_STACK_WIDGET_CLASSES)
                self.assertEqual(attrs["maxlength"], max_length)
                self.assertNotIn("id", attrs)

        for field_name in ("content_type", "object_id", "default_name"):
            with self.subTest(field=field_name):
                self.assertTrue(form.fields[field_name].widget.is_hidden)

    def test_default_name_is_optional_and_limited(self) -> None:
        """Is the suggested name optional, and held to the name's limit?"""
        self.assertTrue(self.build_form().is_valid())
        self.assertTrue(self.build_form(default_name="a" * 100).is_valid())
        over_limit = self.build_form(default_name="a" * 101)

        self.assertFalse(over_limit.is_valid())
        self.assertTrue(over_limit.has_hidden_field_errors)

    def test_labels(self) -> None:
        """Are users shown short labels instead of the model's verbose
        names?"""
        form = NoteForm()

        self.assertEqual(form["name"].label, "Name")
        self.assertEqual(form["notes"].label, "Notes")

    def test_valid_form(self) -> None:
        """Is a complete form accepted?"""
        self.assertTrue(self.build_form().is_valid())

    def test_notes_can_be_blank(self) -> None:
        """Is a note with a name and no notes text accepted, as the model
        allows?"""
        self.assertTrue(self.build_form(notes="").is_valid())

    def test_name_is_required(self) -> None:
        """Is a note without a name rejected?"""
        form = self.build_form(name="")

        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_length_limits(self) -> None:
        """Are values over the model's limits rejected?"""
        for field_name, limit in (("name", 100), ("notes", 500)):
            with self.subTest(field=field_name):
                at_limit = self.build_form(**{field_name: "a" * limit})
                over_limit = self.build_form(**{field_name: "a" * (limit + 1)})

                self.assertTrue(at_limit.is_valid())
                self.assertFalse(over_limit.is_valid())
                self.assertIn(field_name, over_limit.errors)

    def test_rejects_a_dangling_object_id(self) -> None:
        """Is an object_id that names no row rejected? It's a plain integer,
        so only clean() stops it."""
        form = self.build_form(object_id=999999999)

        self.assertFalse(form.is_valid())
        self.assertIn("object_id", form.errors)

    def test_has_hidden_field_errors(self) -> None:
        """Is only a failure of the hidden fields reported, and not a failure
        of the fields the user fills in?"""
        cases = (
            ("valid", self.build_form(), False),
            ("dangling object_id", self.build_form(object_id=999999999), True),
            (
                "unknown content_type",
                self.build_form(content_type=999999999),
                True,
            ),
            ("blank name", self.build_form(name=""), False),
        )
        for label, form, expected in cases:
            with self.subTest(case=label):
                form.is_valid()

                self.assertIs(form.has_hidden_field_errors, expected)

    def test_unbound_form_has_no_hidden_field_errors(self) -> None:
        """Does a form that was never submitted report no errors?"""
        self.assertFalse(NoteForm().has_hidden_field_errors)

    def test_binds_an_existing_note(self) -> None:
        """Does the form work with instance=, prefilled from the note?"""
        user = UserFactory()
        note = NoteFactory.for_object(self.docket, user=user, name="Old name")

        form = NoteForm(instance=note)

        self.assertEqual(form.initial["content_type"], self.content_type.pk)
        self.assertEqual(form.initial["object_id"], self.docket.pk)
        self.assertEqual(form.initial["name"], "Old name")

    def test_save_updates_the_existing_note(self) -> None:
        """Does saving a bound form update the note instead of creating a
        second one?"""
        user = UserFactory()
        note = NoteFactory.for_object(self.docket, user=user, name="Old name")
        form = NoteForm(
            data={
                "content_type": self.content_type.pk,
                "object_id": self.docket.pk,
                "name": "New name",
                "notes": "New notes",
            },
            instance=note,
        )

        self.assertTrue(form.is_valid())
        saved = form.save(commit=False)
        saved.user = user
        saved.save()

        note.refresh_from_db()
        self.assertEqual(saved.pk, note.pk)
        self.assertEqual(note.name, "New name")
        self.assertEqual(note.notes, "New notes")


class NoteFormComponentTest(TestCase):
    """Test the c-add-note.form component's error notice and counter."""

    NOTICE = "Please reload the page and try again."

    @classmethod
    def setUpTestData(cls) -> None:
        cls.docket = DocketFactory()
        cls.content_type = ContentType.objects.get_for_model(cls.docket)

    def render(self, **overrides: str | int) -> str:
        """Render the component with a validated form, with fields that can
        be overridden."""
        data = {
            "content_type": self.content_type.pk,
            "object_id": self.docket.pk,
            "name": "Foo v. Bar",
            "notes": "A note",
        }
        form = NoteForm(data={**data, **overrides})
        form.is_valid()
        compiled = CottonCompiler().process('<c-add-note.form :form="form" />')
        return (
            engines["django"]
            .from_string(compiled)
            .render({"form": form, "request": RequestFactory().get("/")})
        )

    def test_notice_is_shown_when_a_hidden_field_fails(self) -> None:
        """Is the user told to reload when the noted object can't be found?"""
        html = self.render(object_id=999999999)

        self.assertIn('role="alert"', html)
        self.assertIn(self.NOTICE, html)

    def test_suggested_name_travels_with_the_form(self) -> None:
        """Is the page's suggested name rendered as a hidden input, so it is
        posted back with the form?"""
        html = self.render(default_name="Foo v. Bar")

        self.assertIn('name="default_name"', html)
        self.assertIn('value="Foo v. Bar"', html)

    def test_notice_is_not_shown_for_a_valid_form(self) -> None:
        """Is a form with no errors rendered without the notice?"""
        html = self.render()

        self.assertNotIn('role="alert"', html)
        self.assertNotIn(self.NOTICE, html)

    def test_notice_is_not_shown_for_a_field_error(self) -> None:
        """Is a mistake in a visible field left to that field's own message,
        without telling the user to reload?"""
        html = self.render(name="")

        self.assertNotIn(self.NOTICE, html)
        self.assertIn("This field is required.", html)

    def test_counter_wraps_only_the_notes_field(self) -> None:
        """Is the counter's root around the notes textarea, so typing in it
        updates the count, and not around the name field?"""
        html = self.render()

        root = html.index('x-data="noteCounter"')
        self.assertIn('x-on:input="update"', html)
        self.assertLess(html.index('name="name"'), root)
        self.assertGreater(html.index('name="notes"'), root)

    def test_counter_reads_its_limit_from_the_textarea(self) -> None:
        """Does the textarea carry the maxlength the counter counts down
        from, so the limit is defined in one place?"""
        html = self.render()

        self.assertIn('maxlength="500"', html)
        self.assertNotIn("characters-remaining", html)

    def test_counter_keeps_the_visible_count_from_screen_readers(self) -> None:
        """Is the visible count hidden from assistive tech, with a separate
        status region to announce at the thresholds?"""
        html = self.render()

        self.assertIn('aria-hidden="true"', html)
        self.assertIn('x-text="remainingText"', html)
        self.assertIn('role="status"', html)
        self.assertIn('x-text="announcement"', html)


class NoteDialogComponentTest(TestCase):
    """Test the c-add-note.dialog component's button and listeners."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.docket = DocketFactory()
        cls.content_type = ContentType.objects.get_for_model(cls.docket)

    def render(self, user: AnonymousUser | User, note: bool = False) -> str:
        """Render the dialog for the docket, for a user who may have a
        note."""
        if note:
            instance = NoteFactory.for_object(self.docket, user=user)
            form = NoteForm(instance=instance)
        else:
            form = NoteForm(
                initial={
                    "content_type": self.content_type.pk,
                    "object_id": self.docket.pk,
                }
            )
        request = RequestFactory().get("/")
        request.user = user
        compiled = CottonCompiler().process(
            '<c-add-note.dialog :form="form" />'
        )
        return (
            engines["django"]
            .from_string(compiled)
            .render({"form": form, "request": request})
        )

    def test_button_has_the_id_the_response_updates(self) -> None:
        """Does the note button carry the id that the htmx response targets,
        built from the object's content type and id?"""
        html = self.render(AnonymousUser())

        self.assertIn(
            f'id="note-trigger-{self.content_type.pk}-{self.docket.pk}"', html
        )

    def test_button_label_follows_the_note(self) -> None:
        """Does the button offer to add a note, or to edit the existing
        one?"""
        user = UserFactory()

        self.assertIn("Add Note", self.render(user))
        self.assertIn("Edit Note", self.render(user, note=True))

    def test_dialog_closes_when_a_note_is_saved_or_deleted(self) -> None:
        """Does the dialog listen for the events the views send?"""
        html = self.render(UserFactory())

        self.assertIn('x-on:note-saved.window="close"', html)
        self.assertIn('x-on:note-deleted.window="close"', html)


class GetNoteFormForTest(TestCase):
    """Test that get_note_form_for() builds the form class it is given."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.docket = DocketFactory()
        cls.user = UserFactory()

    async def test_defaults_to_the_v1_form(self) -> None:
        """Do callers that don't choose a class keep getting the v1 form?"""
        for user in (AnonymousUser(), self.user):
            with self.subTest(user=type(user).__name__):
                form = await get_note_form_for(self.docket, user, "Foo v. Bar")

                self.assertIs(type(form), V1NoteForm)

    async def test_builds_the_given_class_for_a_new_note(self) -> None:
        """Is a blank form built with the given class and prefilled?"""
        form = await get_note_form_for(
            self.docket, self.user, "Foo v. Bar", form_class=NoteForm
        )

        self.assertIs(type(form), NoteForm)
        self.assertFalse(form.instance.pk)
        self.assertEqual(form.initial["object_id"], self.docket.pk)
        self.assertEqual(form.initial["name"], "Foo v. Bar")
        self.assertEqual(form.initial["default_name"], "Foo v. Bar")

    async def test_builds_the_given_class_for_an_existing_note(self) -> None:
        """Is the user's existing note bound to the given class?"""
        note = await sync_to_async(NoteFactory.for_object)(
            self.docket, user=self.user, name="Old name"
        )

        form = await get_note_form_for(
            self.docket, self.user, "Ignored", form_class=NoteForm
        )

        self.assertIs(type(form), NoteForm)
        self.assertEqual(form.instance.pk, note.pk)
        self.assertEqual(form.initial["name"], "Old name")

    async def test_existing_note_still_gets_the_suggested_name(self) -> None:
        """Does a v2 form for an existing note carry the page's suggested
        name, whether it is given as text or as a lazy callable?"""
        await sync_to_async(NoteFactory.for_object)(
            self.docket, user=self.user, name="Old name"
        )

        async def lazy_name() -> str:
            return "From the callable"

        for label, name, expected in (
            ("text", "Foo v. Bar", "Foo v. Bar"),
            ("callable", lazy_name, "From the callable"),
        ):
            with self.subTest(name=label):
                form = await get_note_form_for(
                    self.docket, self.user, name, form_class=NoteForm
                )

                self.assertEqual(form.initial["name"], "Old name")
                self.assertEqual(form.initial["default_name"], expected)

    async def test_v1_form_does_not_compute_the_name_for_an_existing_note(
        self,
    ) -> None:
        """Is the lazy name still skipped for the v1 form when the user has a
        note, as the audio page relies on?"""
        await sync_to_async(NoteFactory.for_object)(
            self.docket, user=self.user, name="Old name"
        )
        lazy_name = mock.AsyncMock(return_value="Never needed")

        await get_note_form_for(self.docket, self.user, lazy_name)

        lazy_name.assert_not_awaited()
