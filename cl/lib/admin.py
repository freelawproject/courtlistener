from django.contrib.contenttypes.admin import GenericTabularInline

from cl.lib.models import Note


class AdminTweaksMixin:
    class Media:
        css = {
            "all": ("css/admin.css",),
        }


class NotesInline(GenericTabularInline):
    model = Note
    extra = 1
