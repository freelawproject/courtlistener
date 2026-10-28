from typing import Any

from django import forms

from cl.favorites.forms import NoteForm as V1NoteForm
from cl.lib import widgets


class LineBreakCharField(forms.CharField):
    """A CharField that counts a line break as one character.

    Browsers count a textarea line break as one character for maxlength but
    submit it as CRLF, so without this a note that fits the counter can fail
    max_length.
    """

    def to_python(self, value: Any) -> str | None:
        """Normalize CRLF to LF. Runs before the length validators, which is
        why this isn't a clean_notes() method."""
        cleaned = super().to_python(value)
        if not cleaned:
            return cleaned

        return cleaned.replace("\r\n", "\n")


class NoteForm(V1NoteForm):
    """The v1 note form, with new-stack widgets and labels.

    Validation, saving and prefilling all come from the v1 form, so the two
    cannot drift apart. The v1 widgets carry Bootstrap classes and hardcoded
    ids; these leave ids to the template, which sets them per rendered
    instance. content_type/object_id stay hidden inputs, so callers must
    render them with the form.
    """

    ## Default name is a hidden field, so the form can be prefilled after a delete.
    default_name = forms.CharField(
        required=False, max_length=100, widget=forms.HiddenInput()
    )

    class Meta(V1NoteForm.Meta):
        labels = {"name": "Name", "notes": "Notes"}
        field_classes = {"notes": LineBreakCharField}
        widgets = {
            "content_type": forms.HiddenInput(),
            "object_id": forms.HiddenInput(),
            "name": widgets.TextInput(attrs={"maxlength": "100"}),
            "notes": widgets.Textarea(attrs={"maxlength": "500", "rows": "6"}),
        }

    def full_clean(self) -> None:
        """Validate, then mark the first invalid visible field for autofocus.

        htmx focuses an [autofocus] element in the fragment it swaps in, which
        puts keyboard and screen reader users on the error after a failed save.
        Only bound forms with errors are marked.
        """
        super().full_clean()
        for name in self.errors:
            # Non-field errors are keyed "__all__", which isn't a field.
            field = self.fields.get(name)
            if field and not field.widget.is_hidden:
                field.widget.attrs["autofocus"] = True
                return

    @property
    def has_hidden_field_errors(self) -> bool:
        """Whether content_type or object_id failed validation.

        Users can't correct those fields, so templates show one fixed notice
        instead of the field messages.
        """
        return any(field.errors for field in self.hidden_fields())
