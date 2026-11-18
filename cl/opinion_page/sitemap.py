"""Sitemaps of opinion cluster and docket pages."""

from datetime import datetime, timedelta

from django.contrib import sitemaps
from django.db.models import (
    CharField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, Concat

from cl.favorites.models import GenericCount
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Docket,
    OpinionCluster,
)
from cl.sitemaps_infinite.base_sitemap import InfinitePaginatorSitemap


class OpinionSitemap(sitemaps.Sitemap):
    """Sitemap of unblocked, published opinion clusters that are cited or recent."""

    changefreq = "yearly"
    priority = 0.5
    limit = 50_000

    def items(self) -> QuerySet[OpinionCluster]:
        """Get the published, unblocked clusters filed in the last 75 years that are cited or were filed in the last ten years."""
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
        """Use the cluster's modification date."""
        return obj.date_modified


class BlockedOpinionSitemap(sitemaps.Sitemap):
    """Mirrors the OpinionSitemap, but only for recently blocked cases.

    This ensures that they get crawled by search engines and removed from
    results.
    """

    changefreq = "daily"
    priority = 0.6
    limit = 50_000

    def items(self) -> QuerySet[OpinionCluster]:
        """Get the clusters blocked in the last 30 days."""
        return (
            OpinionCluster.objects.filter(
                blocked=True,
                date_blocked__gt=datetime.today() - timedelta(days=30),
            )
            .only("date_modified", "pk", "slug")
            .order_by("pk")
        )

    def lastmod(self, obj: OpinionCluster) -> datetime:
        """Use the cluster's modification date."""
        return obj.date_modified


class DocketSitemap(InfinitePaginatorSitemap):
    """Sitemap of unblocked RECAP dockets that are viewed often or were filed recently."""

    changefreq = "weekly"
    limit = 50_000

    @property
    def section(self) -> str:
        """The RECAP search type."""
        return SEARCH_TYPES.RECAP

    @property
    def ordering(self) -> tuple[str]:
        """Order dockets by primary key."""
        return ("pk",)

    def items(self) -> QuerySet[Docket]:
        """Get the unblocked RECAP dockets with more than ten views or filed in the last 30 days."""
        # Give items ten days to get some views.
        recent_date = datetime.today() - timedelta(days=30)

        view_count_subquery = Subquery(
            GenericCount.objects.filter(
                label=Concat(
                    Value("d."),
                    OuterRef("pk"),
                    Value(":view"),
                    output_field=CharField(),
                )
            ).values("value")[:1]
        )

        # Ordering should NOT be set here, define the ordering in the separate `ordering` property
        return (
            Docket.objects.filter(
                source__in=Docket.RECAP_SOURCES(),
                blocked=False,
            )
            .annotate(view_counter=Coalesce(view_count_subquery, Value(0)))
            .filter(Q(view_counter__gt=10) | Q(date_filed__gt=recent_date))
            .only("date_modified", "pk", "slug")
        )

    def lastmod(self, obj: Docket) -> datetime:
        """Use the docket's modification date."""
        return obj.date_modified

    def get_latest_lastmod(self) -> datetime | None:
        """Get the latest modification date among the sitemap's dockets, if there are any."""
        latest_modified = self.items().order_by("-date_modified").first()
        if latest_modified is None:
            return None
        return latest_modified.date_modified

    def priority(self, obj: Docket) -> float:
        """Rank the docket from 0.3 to 0.65 by its view count."""
        view_count = obj.view_counter
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
    """Sitemap of RECAP dockets blocked in the last 30 days."""

    changefreq = "daily"
    limit = 50_000
    priority = 0.6

    def items(self) -> QuerySet[Docket]:
        """Get the RECAP dockets blocked in the last 30 days."""
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
        """Use the docket's modification date."""
        return obj.date_modified
