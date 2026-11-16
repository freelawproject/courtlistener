"""Delete search queries older than the privacy policy cutoff."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from cl.search.models import SearchQuery


class Command(BaseCommand):
    """Delete search queries older than the privacy policy cutoff."""

    help = "Deletes SearchQuery records older than the privacy cut off."

    def handle(self, *args, **options):
        """Delete search queries created more than ``PRIVACY_POLICY_CUTOFF_DAYS - 1`` days ago."""
        # Do cutoff minus one so that we do not have
        # queries older than the cutoff.
        # See: https://github.com/freelawproject/courtlistener/pull/6510#pullrequestreview-3430758461
        cutoff_date = (
            timezone.now()
            - timedelta(days=settings.PRIVACY_POLICY_CUTOFF_DAYS)
            + timedelta(days=1)
        )
        old_queries = SearchQuery.objects.filter(date_created__lt=cutoff_date)
        record_count, details = old_queries.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {record_count} SearchQuery records older than {settings.PRIVACY_POLICY_CUTOFF_DAYS} days."
            )
        )
