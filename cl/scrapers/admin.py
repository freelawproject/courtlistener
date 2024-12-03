from django.contrib import admin
from django.db import models

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


class MVLatestOpinion(models.Model):
    """
    Model linked to materialized view for monitoring scrapers

    The SQL for creating the view is on it's migration file.

    Must use `REFRESH MATERIALIZED VIEW scrapers_mv_latest_opinion`
    periodically
    """

    # a django model must have a primary key
    court_id = models.TextField(primary_key=True)
    latest_creation_date = models.DateTimeField()
    time_since = models.TextField()
    view_last_updated = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "scrapers_mv_latest_opinion"


@admin.register(MVLatestOpinion)
class MVLatestOpinionAdmin(admin.ModelAdmin):
    """Admin page to look at the latest opinion for each court

    Use this to monitor silently failing scrapers
    """

    list_display = [
        "court_id",
        "latest_creation_date",
        "time_since",
        "view_last_updated",
    ]
