from django import forms
from django.forms import ModelForm

from cl.favorites.models import Note


class NoteForm(ModelForm):
    class Meta:
        model = Note
        exclude = ("user",)
        fields = (
            "id",
            "audio_id",
            "cluster_id",
            "docket_id",
            "recap_doc_id",
            "name",
            "notes",
        )
        widgets = {
            "id": forms.HiddenInput(),
            "cluster_id": forms.HiddenInput(),
            "audio_id": forms.HiddenInput(),
            "docket_id": forms.HiddenInput(),
            "recap_doc_id": forms.HiddenInput(),
            "name": forms.TextInput(
                attrs={
                    "id": "save-note-name-field",
                    "class": "form-control",
                    "maxlength": "100",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "bottom form-control",
                    "id": "save-note-notes-field",
                    "maxlength": "600",
                }
            ),
        }
