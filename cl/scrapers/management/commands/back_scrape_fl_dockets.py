"""Command to back-scrape Florida dockets"""

from datetime import date
from pathlib import Path

from asgiref.sync import async_to_sync
from django.core.management import CommandParser
from juriscraper.state.florida import FloridaCase, FloridaScraper
from juriscraper.state.florida.courts import FloridaCourtID

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import logger
from cl.scrapers.management.utils import (
    FLScrapeCommand,
    ScraperCheckpointTracker,
    StateBackScrapeCommand,
    _make_case_number_key,
    _parse_date,
)
from cl.scrapers.tasks import save_response_to_s3

S3_BASE = Path("responses/dockets/florida")


def save_case_to_s3(
    court_id: FloridaCourtID,
    case: FloridaCase,
    throttle: CeleryThrottle,
    queue_name: str,
):
    key = f"{S3_BASE}/parsed/{court_id.value}/{_make_case_number_key(case.docket_number)}.json"
    content = case.model_dump_json(ensure_ascii=True).encode("utf-8")

    throttle.maybe_wait()
    save_response_to_s3.si(key, content).set(queue=queue_name).apply_async()


async def _backfill(
    date_ranges: dict[FloridaCourtID, tuple[date, date]],
    full_scrape: bool,
    checkpoint_trackers: dict[FloridaCourtID, ScraperCheckpointTracker],
    scraper: FloridaScraper,
    throttle: CeleryThrottle,
    queue_name: str,
):
    logger.info("Starting Florida backfill...")
    try:
        for court_id, (start_date, end_date) in date_ranges.items():
            i = 0
            async for case in scraper.backfill(
                start_date,
                end_date,
                court_ids=[court_id],
                full_scrape=full_scrape,
            ):
                save_case_to_s3(court_id, case, throttle, queue_name)

                i += 1
                if i % 100 == 0:
                    logger.info(
                        "Updating checkpoint for %s to %s",
                        court_id,
                        case.date_filed,
                    )
                    checkpoint_trackers[court_id].set(case.date_filed)
    except Exception:
        logger.exception("Florida backfill failed.")
    else:
        logger.info("Florida backfill completed successfully!")


class Command(StateBackScrapeCommand, FLScrapeCommand):
    help: str = "Back-scrape Florida dockets"

    checkpoint_trackers: dict[FloridaCourtID, ScraperCheckpointTracker] = {
        FloridaCourtID.SUPREME_COURT: ScraperCheckpointTracker("acisflsc"),
        FloridaCourtID.FIRST_COA: ScraperCheckpointTracker("acisfl1ac"),
        FloridaCourtID.SECOND_COA: ScraperCheckpointTracker("acisfl2ac"),
        FloridaCourtID.THIRD_COA: ScraperCheckpointTracker("acisfl3ac"),
        FloridaCourtID.FOURTH_COA: ScraperCheckpointTracker("acisfl4ac"),
        FloridaCourtID.FIFTH_COA: ScraperCheckpointTracker("acisfl5ac"),
        FloridaCourtID.SIXTH_COA: ScraperCheckpointTracker("acisfl6ac"),
    }

    def add_arguments(self, parser: CommandParser):
        super(Command, self).add_arguments(parser)

        parser.add_argument(
            "--full-scrape",
            action="store_true",
            default=False,
            help="If set the scraper will fetch all docket metadata in addition to the list of dockets.",
        )
        parser.add_argument(
            "--use-cache",
            action="store_true",
            default=False,
            help="If set the scraper will use the cache to avoid re-downloading files. Useful when running a second pass with the --full-scrape option.",
        )

    def handle(
        self,
        *args,
        auto_resume: bool,
        rps: float,
        max_retries: int,
        backoff: float,
        backoff_growth: float,
        full_scrape: bool,
        use_cache: bool,
        archive_responses: bool,
        queue: str,
        throttle_min_items: int,
        backscrape_start: str,
        backscrape_end: str,
        courts: str | None,
        **options,
    ):
        logger.info("Setting up Florida back-scrape...")
        start = _parse_date(backscrape_start)
        end = _parse_date(backscrape_end)
        court_ids = self.parse_court_ids(courts)

        throttle, scraper = self.throttle_and_scraper(
            rps,
            max_retries,
            backoff,
            backoff_growth,
            use_cache,
            archive_responses,
            queue,
            throttle_min_items,
            S3_BASE,
        )

        if auto_resume:
            logger.info("Auto resume enabled. Getting checkpoints...")
            checkpoints = {
                cid: self.checkpoint_trackers[cid].get() for cid in court_ids
            }
        else:
            checkpoints = {}

        date_ranges = {
            cid: (checkpoints.get(cid) or start, end) for cid in court_ids
        }

        logger.info(
            "Date ranges to scrape are:\n%s",
            "\n- ".join(
                [
                    f"{cid.value}: {start}..{end}"
                    for cid, (start, end) in date_ranges.items()
                ]
            ),
        )

        async_to_sync(_backfill)(
            date_ranges=date_ranges,
            full_scrape=full_scrape,
            checkpoint_trackers=self.checkpoint_trackers,
            scraper=scraper,
            throttle=throttle,
            queue_name=queue,
        )
