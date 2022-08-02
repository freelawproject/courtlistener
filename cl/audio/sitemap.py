from datetime import datetime

from django.contrib import sitemaps
from django.db.models import QuerySet

from cl.audio.models import Audio


class AudioSitemap(sitemaps.Sitemap):
    changefreq = "monthly"
    priority = 0.4
    limit = 50_000

    def items(self) -> QuerySet:
        return Audio.objects.filter(blocked=False).order_by("pk")

    def lastmod(self, obj: Audio) -> datetime:
        return obj.date_modified
