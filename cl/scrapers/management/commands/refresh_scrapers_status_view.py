"""Refresh the materialized view used to monitor scrapers."""

from django.db import connection

from cl.lib.command_utils import VerboseCommand, logger


class Command(VerboseCommand):
    """Refresh the ``scrapers_mv_latest_opinion`` materialized view."""

    help = """Refreshes the `scrapers_mv_latest_opinion` materialized view.

    Check the cl.scrapers.admin.py file for more info about the view
    """

    def handle(self, *args, **options):
        """Refresh the view."""
        query = "REFRESH MATERIALIZED VIEW scrapers_mv_latest_opinion;"
        with connection.cursor() as cursor:
            cursor.execute(query)

        logger.info("View refresh completed successfully")
