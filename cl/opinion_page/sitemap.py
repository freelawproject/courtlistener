from datetime import datetime, timedelta

from django.contrib import sitemaps
from django.db.models import Q, QuerySet

from cl.search.models import PRECEDENTIAL_STATUS, Docket, OpinionCluster


class OpinionSitemap(sitemaps.Sitemap):
    changefreq = "yearly"
    priority = 0.5
    limit = 50_000

    def items(self) -> QuerySet:
        # Unblocked precedential cases that are published in the last 75 years
        # and that have at least one citation, or that were published in the
        # last ten years and not yet cited.
        new_or_popular = Q(citation_count__gte=1) | Q(
            date_filed__gt=datetime.today() - timedelta(days=365 * 10)
        )
        return (
            OpinionCluster.objects.filter(
                new_or_popular,
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                blocked=False,
                date_filed__gt=datetime.today() - timedelta(days=365 * 75),
            )
            .only("date_modified", "pk", "slug")
            .order_by("pk")
        )

    def lastmod(self, obj: OpinionCluster) -> datetime:
        return obj.date_modified


class BlockedOpinionSitemap(sitemaps.Sitemap):
    """Mirrors the OpinionSitemap, but only for recently blocked cases.

    This ensures that they get crawled by search engines and removed from
    results.
    """

    changefreq = "daily"
    priority = 0.6
    limit = 50_000

    def items(self) -> QuerySet:
        return (
            OpinionCluster.objects.filter(
                blocked=True,
                date_blocked__gt=datetime.today() - timedelta(days=30),
            )
            .only("date_modified", "pk", "slug")
            .order_by("pk")
        )

    def lastmod(self, obj: OpinionCluster) -> datetime:
        return obj.date_modified


class DocketSitemap(sitemaps.Sitemap):
    changefreq = "weekly"
    limit = 50_000

    def items(self) -> QuerySet:
        # Give items ten days to get some views.
        new_or_popular = Q(view_count__gt=10) | Q(
            date_filed__gt=datetime.today() - timedelta(days=30)
        )
        return (
            Docket.objects.filter(
                new_or_popular,
                source__in=Docket.RECAP_SOURCES(),
                blocked=False,
            )
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


class BlockedDocketSitemap(sitemaps.Sitemap):
    changefreq = "daily"
    limit = 50_000
    priority = 0.6

    def items(self) -> QuerySet:
        return (
            Docket.objects.filter(
                source__in=Docket.RECAP_SOURCES(),
                blocked=True,
                date_blocked__gt=datetime.today() - timedelta(days=30),
            )
            .order_by("pk")
            .only("view_count", "date_modified", "pk", "slug")
        )

    def lastmod(self, obj: Docket) -> datetime:
        return obj.date_modified
