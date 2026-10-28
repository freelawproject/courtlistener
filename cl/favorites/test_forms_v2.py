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

    def test_default_name_is_optional_and_limited(self) -> None:
        """Is the suggested name optional, and held to the name's limit?"""
        self.assertTrue(self.build_form().is_valid())
        self.assertTrue(self.build_form(default_name="a" * 100).is_valid())
        over_limit = self.build_form(default_name="a" * 101)

        self.assertFalse(over_limit.is_valid())
        self.assertTrue(over_limit.has_hidden_field_errors)

    def test_length_limits(self) -> None:
        """Are values over the model's limits rejected?"""
        for field_name, limit in (("name", 100), ("notes", 500)):
            with self.subTest(field=field_name):
                at_limit = self.build_form(**{field_name: "a" * limit})
                over_limit = self.build_form(**{field_name: "a" * (limit + 1)})

                self.assertTrue(at_limit.is_valid())
                self.assertFalse(over_limit.is_valid())
                self.assertIn(field_name, over_limit.errors)

    def test_line_breaks_count_as_one_character(self) -> None:
        """Does a note the browser counted as 500 characters pass, even though
        it is submitted with CRLF line breaks?"""
        within_limit = "a" * 250 + "\r\n" + "a" * 249
        over_limit = "a" * 251 + "\r\n" + "a" * 249

        form = self.build_form(notes=within_limit)
        self.assertTrue(form.is_valid())
        self.assertNotIn("\r", form.cleaned_data["notes"])
        self.assertFalse(self.build_form(notes=over_limit).is_valid())

    def test_first_invalid_visible_field_takes_focus(self) -> None:
        """Does a failed save mark the first invalid visible field for
        autofocus, and nothing else?"""
        for label, form, focused in (
            ("name", self.build_form(name="", notes="a" * 501), "name"),
            ("notes", self.build_form(notes="a" * 501), "notes"),
            ("valid", self.build_form(), None),
            ("hidden only", self.build_form(object_id=999999999), None),
            ("unbound", NoteForm(), None),
        ):
            with self.subTest(case=label):
                form.is_valid()
                marked = [
                    name
                    for name, field in form.fields.items()
                    if field.widget.attrs.get("autofocus")
                ]

                self.assertEqual(marked, [focused] if focused else [])

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
            ("unbound", NoteForm(), False),
        )
        for label, form, expected in cases:
            with self.subTest(case=label):
                form.is_valid()

                self.assertIs(form.has_hidden_field_errors, expected)


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

    def test_notice_is_only_for_hidden_field_errors(self) -> None:
        """Is the user told to reload only when a hidden field fails, and left
        to the field's own message when a visible one does?"""
        for label, overrides, notice, message in (
            ("hidden field", {"object_id": 999999999}, True, None),
            ("visible field", {"name": ""}, False, "This field is required."),
            ("valid", {}, False, None),
        ):
            with self.subTest(case=label):
                html = self.render(**overrides)

                self.assertEqual(self.NOTICE in html, notice)
                self.assertEqual('role="alert"' in html, notice)
                if message:
                    self.assertIn(message, html)

    def test_counter_markup(self) -> None:
        """Does the notes field sit in a counter that reads the textarea's own
        limit, keeps the visible count from screen readers, and has a status
        region for the thresholds?"""
        html = self.render()

        root = html.index('x-data="noteCounter"')
        self.assertLess(html.index('name="name"'), root)
        self.assertGreater(html.index('name="notes"'), root)
        for markup in (
            'x-on:input="update"',
            'maxlength="500"',
            'aria-hidden="true"',
            'x-text="remainingText"',
            'role="status"',
            'x-text="announcement"',
        ):
            with self.subTest(markup=markup):
                self.assertIn(markup, html)
        self.assertNotIn("characters-remaining", html)


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

    def test_dialog_listens_for_the_events_the_views_send(self) -> None:
        """Does the dialog close on the save and delete events, and announce
        them from a status region that stays on the page?"""
        html = self.render(UserFactory())

        for markup in (
            'x-on:note-saved.window="close"',
            'x-on:note-deleted.window="close"',
            'role="status"',
            'x-on:note-saved.window="saved"',
            'x-on:note-deleted.window="deleted"',
            'data-saved="Note saved."',
            'data-deleted="Note deleted."',
        ):
            with self.subTest(markup=markup):
                self.assertIn(markup, html)


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

                self.assertIs(type(form), NoteForm)
                self.assertEqual(form.initial["name"], "Old name")
                self.assertEqual(form.initial["default_name"], expected)
