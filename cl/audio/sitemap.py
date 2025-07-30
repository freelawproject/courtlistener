from datetime import datetime, timedelta

from django.contrib import sitemaps
from django.db.models import QuerySet

from cl.audio.models import Audio


class AudioSitemap(sitemaps.Sitemap):
    changefreq = "monthly"
    priority = 0.4
    limit = 50_000

    def items(self) -> QuerySet:
        q = (
            Audio.objects.filter(blocked=False)
            .select_related("docket")
            .only("date_modified", "pk", "docket__slug")
            .order_by("pk")
        )
        return q

    def lastmod(self, obj: Audio) -> datetime:
        return obj.date_modified


class BlockedAudioSitemap(sitemaps.Sitemap):
    changefreq = "daily"
    limit = 50_000
    priority = 0.6

    def items(self) -> QuerySet:
        q = (
            Audio.objects.filter(
                blocked=True,
                date_blocked__gt=datetime.today() - timedelta(days=30),
            )
            .select_related("docket")
            .only("date_modified", "pk", "docket__slug")
            .order_by("pk")
        )
        return q

    def lastmod(self, obj: Audio) -> datetime:
        return obj.date_modified
