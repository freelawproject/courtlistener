from django.contrib import admin

from cl.scrapers.models import (
    PACERFreeDocumentLog,
    PACERFreeDocumentRow,
    UrlHash,
)


@admin.register(PACERFreeDocumentLog)
class PACERFreeDocumentLogAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "court_id",
        "status",
        "date_started",
        "date_completed",
        "date_queried",
    )
    list_filter = ("status", "court__jurisdiction")
    list_editable = ("status",)
    ordering = ("-date_started",)


@admin.register(PACERFreeDocumentRow)
class PACERFreeDocumentRowAdmin(admin.ModelAdmin):
    list_display = ("__str__", "court_id", "docket_number", "error_msg")
    list_filter = ("court_id",)


admin.site.register(UrlHash)
