from datetime import datetime

from django.contrib import sitemaps
from django.db.models import QuerySet

from cl.search.models import OpinionCluster, Docket


class OpinionSitemap(sitemaps.Sitemap):
    changefreq = "yearly"
    priority = 0.5
    limit = 50_000

    def items(self) -> QuerySet:
        return OpinionCluster.objects.only(
            "date_modified", "pk", "slug"
        ).order_by("pk")

    def lastmod(self, obj: OpinionCluster) -> datetime:
        return obj.date_modified


class DocketSitemap(sitemaps.Sitemap):
    changefreq = "weekly"
    limit = 50_000

    def items(self) -> QuerySet:
        return (
            Docket.objects.filter(source__in=Docket.RECAP_SOURCES)
            .order_by("pk")
            .only("view_count", "date_modified", "pk", "slug")
        )

    def lastmod(self, obj: Docket) -> datetime:
        return obj.date_modified

    def priority(self, obj: Docket) -> float:
        view_count = obj.view_count
        priority = 0.5
        if view_count <= 1:
            priority = 0.3
        elif 1 < view_count <= 10:
            priority = 0.4
        elif 10 < view_count <= 100:
            priority = 0.5
        elif 100 < view_count <= 1_000:
            priority = 0.55
        elif view_count > 1_000:
            priority = 0.65
        return priority
