from collections.abc import Awaitable, Callable
from typing import Any

from asgiref.sync import sync_to_async
from django import forms
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.forms import ModelForm

from cl.favorites.models import Note
from cl.favorites.utils import get_note_for_target, resolve_legacy_object


class NoteForm(ModelForm):
    class Meta:
        model = Note
        exclude = ("user",)
        fields = (
            "id",
            "content_type",
            "object_id",
            "name",
            "notes",
        )
        widgets = {
            "id": forms.HiddenInput(),
            "content_type": forms.HiddenInput(),
            "object_id": forms.HiddenInput(),
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Prefill a legacy-shaped instance's hidden fields (#7725): read
        content_type/object_id from whichever legacy FK is set, so the
        form renders in the new shape.
        """
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        if not instance or not instance.pk or instance.content_type_id:
            return

        resolved = resolve_legacy_object(instance)
        if resolved:
            content_type, object_id = resolved
            self.initial["content_type"] = content_type.pk
            self.initial["object_id"] = object_id


async def get_note_form_for(
    obj: models.Model,
    user: AnonymousUser | User,
    name: str | Callable[[], Awaitable[str]],
) -> NoteForm:
    """Build a NoteForm for a noteable object: bound to the user's
    existing Note if one exists, else blank and pre-filled.

    :param obj: A noteable model instance (see NOTEABLE_MODELS).
    :param user: The user requesting the form, possibly anonymous.
    :param name: The suggested default value for the note's "name" field,
        used only when no existing Note is found. Pass an async callable
        instead of a plain string to defer computing it -- e.g. audio
        pages only know their case name via their parent Docket, so
        deferring means that extra query never runs when a Note already
        exists and the name ends up unused.
    :return: A NoteForm bound to the user's existing Note for obj, or an
        unsaved one pre-filled with obj's content_type/object_id.
    """
    note = await sync_to_async(get_note_for_target)(type(obj), obj.pk, user)
    if note is not None:
        return NoteForm(instance=note)

    resolved_name = await name() if callable(name) else name
    content_type = await sync_to_async(ContentType.objects.get_for_model)(
        type(obj)
    )
    return NoteForm(
        initial={
            "content_type": content_type.pk,
            "object_id": obj.pk,
            "name": resolved_name,
        }
    )
