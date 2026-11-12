"""Sitemap of people pages."""

from datetime import datetime

from django.contrib import sitemaps
from django.db.models import QuerySet

from cl.people_db.models import Person


class PersonSitemap(sitemaps.Sitemap):
    """Sitemap of the pages of people who aren't aliases."""

    changefreq = "monthly"
    limit = 50_000
    priority = 0.5

    def items(self) -> QuerySet:
        """Get the people who aren't aliases."""
        return Person.objects.filter(is_alias_of=None).order_by("pk")

    def lastmod(self, obj: Person) -> datetime:
        """Use the person's modification date."""
        return obj.date_modified
