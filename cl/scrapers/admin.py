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


class MVLatestOpinions(models.Model):
    """
    Model linked to materialized view for monitoring scrapers

    Must use `REFRESH MATERIALIZED VIEW scrapers_mv_latest_opinion`
    periodically
    """

    query = """
    CREATE MATERIALIZED VIEW
        scrapers_mv_latest_opinion
    AS
    (
    SELECT
        court_id,
        max(so.date_created) as latest_creation_date,
        (now() - max(so.date_created))::text as time_since
    FROM
        (
            SELECT id, court_id
            FROM search_docket
            WHERE court_id IN (
                SELECT id
                FROM search_court
                /*
                    Only check courts with scrapers in use
                */
                WHERE
                    has_opinion_scraper
                    AND in_use
            )
        ) sd
    INNER JOIN
        (SELECT id, docket_id FROM search_opinioncluster) soc ON soc.docket_id = sd.id
    INNER JOIN
        search_opinion so ON so.cluster_id = soc.id
    GROUP BY
        sd.court_id
    HAVING
        /*
            Only return results for courts with no updates in a week
        */
        now() - max(so.date_created) > interval '7 days'
    ORDER BY
        2 DESC
    )
    """
    # a django model must have a primary key
    court_id = models.TextField(primary_key=True)
    latest_creation_date = models.DateField()
    time_since = models.TextField()

    class Meta:
        managed = False  # ignore this model in migrations
        db_table = "scrapers_mv_latest_opinion"


@admin.register(MVLatestOpinions)
class MVLatestOpinionsAdmin(admin.ModelAdmin):
    """Admin page to look at the latest opinion for each court

    Use this to monitor silently failing scrapers
    """

    list_display = ["court_id", "latest_creation_date", "time_since"]
