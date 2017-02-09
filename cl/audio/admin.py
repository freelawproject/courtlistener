from cl.audio.models import Audio
from django.contrib import admin


@admin.register(Audio)
class AudioAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'docket',
        'panel',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
    )
