from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from cl.search.models import SearchQuery


class Command(BaseCommand):
    help = "Deletes SearchQuery records older than 12 weeks."

    def handle(self, *args, **options):
        cutoff_date = timezone.now() - timedelta(weeks=12)
        old_queries = SearchQuery.objects.filter(date_created__lt=cutoff_date)
        record_count, details = old_queries.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {record_count} SearchQuery records older than 12 weeks."
            )
        )
