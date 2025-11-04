from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Docket
from cl.search.signals import clean_docket_number_raw_and_update_redis_cache


class Command(VerboseCommand):
    help = "Clean docket_number_raw and send to LLM cleaning daemon if needed."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.throttle = None

    def add_arguments(self, parser):
        parser.add_argument(
            "--court-ids",
            nargs="+",
            type=str,
            help="The court IDs to filter Dockets to update, may be more than one.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        court_ids = options.get("court_ids")
        dockets = (
            Docket.objects.filter(court_id__in=court_ids)
            .exclude(source=Docket.RECAP)
            .order_by("pk")
        )

        logger.info("Getting count of dockets to process.")
        count = dockets.count()
        logger.info("Total dockets to process: %s", count)

        processed_count = 0
        for docket in dockets.iterator(chunk_size=1000):
            clean_docket_number_raw_and_update_redis_cache(docket)
            processed_count += 1

            if not processed_count % 1000:
                # Log every 1000 dockets processed.
                logger.info(
                    "Processed %s/%s, (%s), last ID cleaned: %s",
                    processed_count,
                    count,
                    f"{processed_count * 1.0 / count:.0%}",
                    docket.id,
                )

        logger.info(
            "Successfully requested for embedding %s items for courts %s.",
            processed_count,
            court_ids,
        )
