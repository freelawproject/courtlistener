import time

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import (
    get_redis_interface,
)
from cl.search.docket_number_cleaner import (
    clean_docket_number_raw_and_update_redis_cache,
)
from cl.search.models import Docket


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
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            default=False,
            help="Auto resume the command using the last docket_id logged in Redis.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="The delay in seconds between processing each docket.",
        )
        parser.add_argument(
            "--test-mode",
            action="store_true",
            default=False,
            help="Run the command in test mode.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        court_ids = options.get("court_ids")
        auto_resume = options["auto_resume"]
        delay = options.get("delay")
        test_mode = options.get("test_mode")

        r = get_redis_interface("CACHE")
        redis_key = "docket_number_cleaning:last_docket_id"

        dockets = (
            Docket.objects.only(
                "id", "court_id", "docket_number_raw", "docket_number"
            )
            .filter(court_id__in=court_ids)
            .exclude(source=Docket.RECAP)
            .order_by("pk")
        )

        if auto_resume:
            start_id = r.get(redis_key)
            if start_id is not None:
                dockets = dockets.filter(id__gte=start_id)
                logger.info(
                    "Auto-resume enabled starting docket_number_cleaning for ID: %s for courts %s",
                    start_id,
                    court_ids,
                )
            else:
                logger.info(
                    "Auto-resume enabled but no last_docket_id found in Redis. Starting from beginning for courts %s",
                    court_ids,
                )

        logger.info("Getting count of dockets to process.")
        count = dockets.count()
        logger.info("Total dockets to process: %s", count)

        processed_count = 0
        for docket in dockets.iterator(chunk_size=1000):
            clean_docket_number_raw_and_update_redis_cache(docket, r)
            processed_count += 1

            if not processed_count % 100:
                # Log every 100 dockets processed.
                r.set(redis_key, docket.id, ex=60 * 60 * 24 * 28)  # 4 weeks
                logger.info(
                    "Processed %s/%s, (%s), last ID cleaned: %s",
                    processed_count,
                    count,
                    f"{processed_count * 1.0 / count:.0%}",
                    docket.id,
                )

            if not test_mode:
                # Throttle processing to avoid overwhelming the system.
                time.sleep(delay)

        logger.info(
            "Successfully cleaned docket_number_raw %s items for courts %s.",
            processed_count,
            court_ids,
        )
