from datetime import datetime

from django.contrib.sitemaps import Sitemap
from django.db.models import QuerySet

from cl.disclosures.models import FinancialDisclosure


class DisclosureSitemap(Sitemap):
    changefreq = "yearly"
    priority = 0.5

    def items(self) -> QuerySet:
        return FinancialDisclosure.objects.order_by(
            "person_id", "-year"
        ).distinct("person_id")

    def lastmod(self, obj: FinancialDisclosure) -> datetime:
        return obj.date_modified
