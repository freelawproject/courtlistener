"""Sitemaps of oral argument audio pages."""

from datetime import datetime, timedelta

from django.contrib import sitemaps
from django.db.models import QuerySet

from cl.audio.models import Audio


class AudioSitemap(sitemaps.Sitemap):
    """Sitemap of unblocked audio pages."""

    changefreq = "monthly"
    priority = 0.4
    limit = 50_000

    def items(self) -> QuerySet:
        """Get the unblocked audio files."""
        q = (
            Audio.objects.filter(blocked=False)
            .select_related("docket")
            .only("date_modified", "pk", "docket__slug")
            .order_by("pk")
        )
        return q

    def lastmod(self, obj: Audio) -> datetime:
        """Use the audio's modification date."""
        return obj.date_modified


class BlockedAudioSitemap(sitemaps.Sitemap):
    """Sitemap of audio pages blocked in the last 30 days."""

    changefreq = "daily"
    limit = 50_000
    priority = 0.6

    def items(self) -> QuerySet:
        """Get the audio files blocked in the last 30 days."""
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
        """Use the audio's modification date."""
        return obj.date_modified
