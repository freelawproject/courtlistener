from alert.audio.models import Audio
from django.contrib import admin


class AudioAdmin(admin.ModelAdmin):
    raw_id_fields = ('docket',)
    readonly_fields = (
        'time_retrieved',
        'date_modified',
    )

admin.site.register(Audio, AudioAdmin)

