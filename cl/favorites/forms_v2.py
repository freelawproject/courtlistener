from django import forms

from cl.favorites.forms import NoteForm as V1NoteForm
from cl.lib import widgets


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
        widgets = {
            "content_type": forms.HiddenInput(),
            "object_id": forms.HiddenInput(),
            "name": widgets.TextInput(attrs={"maxlength": "100"}),
            "notes": widgets.Textarea(attrs={"maxlength": "500"}),
        }

    @property
    def has_hidden_field_errors(self) -> bool:
        """Whether content_type or object_id failed validation.

        Users can't correct those fields, so templates show one fixed notice
        instead of the field messages.
        """
        return any(field.errors for field in self.hidden_fields())
