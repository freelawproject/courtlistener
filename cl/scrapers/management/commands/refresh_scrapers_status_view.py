from django.db import connection

from cl.lib.command_utils import VerboseCommand, logger


class Command(VerboseCommand):
    help = """Refreshes the `scrapers_mv_latest_opinion` materialized view.

    Check the cl.scrapers.admin.py file for more info about the view
    """

    def handle(self, *args, **options):
        query = "REFRESH MATERIALIZED VIEW scrapers_mv_latest_opinion;"
        with connection.cursor() as cursor:
            cursor.execute(query)

        logger.info("View refresh completed successfully")
