from django.contrib.contenttypes.admin import GenericTabularInline

from cl.lib.models import Note


class AdminTweaksMixin(object):
    class Media:
        css = {
            "all": ("css/admin.css",),
        }
        js = ("js/admin.js",)


class NotesInline(GenericTabularInline):
    model = Note
    extra = 1
