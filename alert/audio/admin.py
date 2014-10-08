from alert.audio.models import Audio
from django.contrib import admin


class AudioAdmin(admin.ModelAdmin):
    raw_id_fields = ('docket',)


class CourtAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'short_name',
        'position',
        'in_use',
        'pk'
    )
    list_filter = (
        'jurisdiction',
        'in_use',
    )


admin.site.register(Audio, AudioAdmin)

