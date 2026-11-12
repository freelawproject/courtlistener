"""Django admin configuration for PACER RSS feed statuses, data, and item cache."""

from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin

from cl.recap_rss.models import RssFeedData, RssFeedStatus, RssItemCache


@admin.register(RssFeedStatus)
class RssFeedStatusAdmin(CursorPaginatorAdmin):
    """Admin for RSS feed crawl statuses."""

    list_filter = (
        "status",
        "is_sweep",
        "court",
    )
    list_display = ("__str__", "court", "status", "is_sweep")


@admin.register(RssFeedData)
class RssFeedDataAdmin(CursorPaginatorAdmin):
    """Admin for stored RSS feed data."""

    list_filter = ("court",)
    list_display = ("__str__", "court", "date_created")


admin.site.register(RssItemCache)
