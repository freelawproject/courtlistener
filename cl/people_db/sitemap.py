from datetime import datetime

from django.contrib import sitemaps
from django.db.models import QuerySet

from cl.people_db.models import Person


class PersonSitemap(sitemaps.Sitemap):
    changefreq = "monthly"
    limit = 50_000
    priority = 0.5

    def items(self) -> QuerySet:
        return Person.objects.filter(is_alias_of=None).order_by("pk")

    def lastmod(self, obj: Person) -> datetime:
        return obj.date_modified
