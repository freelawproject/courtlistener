from django.contrib import admin

from cl.audio.models import Audio


@admin.register(Audio)
class AudioAdmin(admin.ModelAdmin):
    raw_id_fields = (
        "docket",
        "panel",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )
