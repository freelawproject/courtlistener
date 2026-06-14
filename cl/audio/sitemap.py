from datetime import datetime, timedelta

from django.contrib import sitemaps
from django.db.models import QuerySet

from cl.audio.models import Audio
from cl.search.models import SEARCH_TYPES
from cl.sitemaps_infinite.base_sitemap import InfinitePaginatorSitemap


class AudioSitemap(InfinitePaginatorSitemap):
    changefreq = "monthly"
    priority = 0.4
    limit = 50_000

    @property
    def section(self) -> str:
        return SEARCH_TYPES.ORAL_ARGUMENT

    @property
    def ordering(self) -> tuple[str]:
        return ("pk",)

    def items(self) -> QuerySet:
        q = (
            Audio.objects.filter(blocked=False)
            .select_related("docket")
            .only("date_modified", "pk", "docket__slug")
        )
        return q

    def lastmod(self, obj: Audio) -> datetime:
        return obj.date_modified

    def get_latest_lastmod(self):
        latest_modified = self.items().order_by("-date_modified").first()
        return latest_modified.date_modified if latest_modified else None


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
