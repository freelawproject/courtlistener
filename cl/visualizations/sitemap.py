from datetime import datetime

from django.contrib.sitemaps import Sitemap
from django.db.models import QuerySet

from cl.visualizations.models import SCOTUSMap


class VizSitemap(Sitemap):
    changefreq = "yearly"
    priority = 0.4
    # limit = 1

    def items(self) -> QuerySet:
        return SCOTUSMap.objects.filter(
            deleted=False, published=True
        ).order_by("pk")

    def lastmod(self, obj: SCOTUSMap) -> datetime:
        return obj.date_modified
