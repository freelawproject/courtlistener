from django.contrib import admin

from cl.recap_rss.models import RssFeedStatus


@admin.register(RssFeedStatus)
class RssFeedStatusAdmin(admin.ModelAdmin):
    list_filter = ('court',)
    list_display = ('__str__', 'court', 'status', 'is_sweep')
