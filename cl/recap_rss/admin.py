from django.contrib import admin

from cl.recap_rss.models import RssFeedData, RssFeedStatus, RssItemCache


@admin.register(RssFeedStatus)
class RssFeedStatusAdmin(admin.ModelAdmin):
    list_filter = ("court",)
    list_display = ("__str__", "court", "status", "is_sweep")


@admin.register(RssFeedData)
class RssFeedDataAdmin(admin.ModelAdmin):
    list_filter = ("court",)
    list_display = ("__str__", "court", "date_created")


admin.site.register(RssItemCache)
