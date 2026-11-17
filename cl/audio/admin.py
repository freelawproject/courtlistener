"""Django admin configuration for oral argument audio."""

from django.contrib import admin

from cl.audio.models import Audio


@admin.register(Audio)
class AudioAdmin(admin.ModelAdmin):
    """Admin for oral argument audio files."""

    raw_id_fields = (
        "docket",
        "panel",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )
