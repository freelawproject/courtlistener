"""Command to back-scrape Florida dockets"""

from datetime import date
from pathlib import Path
from typing import ClassVar
from uuid import UUID

from asgiref.sync import async_to_sync
from django.core.management import CommandParser
from juriscraper.state.florida import FloridaCase, FloridaScraper
from juriscraper.state.florida.courts import FloridaCourtID

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import logger
from cl.scrapers.management.utils import (
    FL_COURT_ID_MAP,
    FLScrapeCommand,
    S3Cache,
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
    key = _make_case_key(court_id, case.docket_number)
    content = case.model_dump_json(ensure_ascii=True).encode("utf-8")
    throttle.maybe_wait()
    save_response_to_s3.si(key, content).set(queue=queue_name).apply_async()


def _make_case_key(court_id: FloridaCourtID, docket_number: str) -> str:
    return f"{S3_BASE}/parsed/{court_id.value}/{_make_case_number_key(docket_number)}.html"


async def _get_full_case(  # type: ignore[return]
    court_id: str, case_uuid: str, scraper: FloridaScraper
) -> FloridaCase | None:
    """Attempt to fetch the full case data for a given case, returning `None` if any error occurred."""
    match await scraper.fetch_case_data(case_uuid, court_id):
        case Exception() as e:
            logger.error(
                "Failed to fetch full case data for %s: %s",
                case_uuid,
                e,
            )
            return None
        case (_, errors) if errors:
            logger.error(
                "Failed to fetch full case data for %s: %r",
                case_uuid,
                errors,
            )
            return None
        case (full_case, _):
            return full_case


async def _backfill_targeted(
    cases: list[tuple[FloridaCourtID, UUID]],
    throttle: CeleryThrottle,
    queue_name: str,
    scraper: FloridaScraper,
):
    logger.info("Starting targeted backfill of %d cases...", len(cases))
    for i, (court_id, case_uuid) in enumerate(cases):
        logger.info("Fetching case %s for %s", case_uuid, court_id)
        case = await _get_full_case(court_id.value, str(case_uuid), scraper)
        if case is None:
            continue

        content = case.model_dump_json(ensure_ascii=True).encode("utf-8")

        key = _make_case_key(court_id, case.docket_number)

        throttle.maybe_wait()
        save_response_to_s3.si(key, content).set(
            queue=queue_name
        ).apply_async()

        if i % 10 == 0:
            logger.info(
                "Completed scrape of %d/%d cases (%.2f%%)",
                i + 1,
                len(cases),
                (i + 1) / len(cases) * 100,
            )


async def _backfill(
    date_ranges: dict[FloridaCourtID, tuple[date, date]],
    full_scrape: bool,
    checkpoint_trackers: dict[FloridaCourtID, ScraperCheckpointTracker],
    scraper: FloridaScraper,
    throttle: CeleryThrottle,
    queue_name: str,
    skip_parsed: bool,
    cache: S3Cache,
):
    logger.info("Starting Florida backfill...")
    full_scrape_loop = full_scrape and not skip_parsed
    try:
        for court_id, (start_date, end_date) in date_ranges.items():
            i = 0
            async for case in scraper.backfill(
                start_date,
                end_date,
                court_ids=[court_id],
                full_scrape=full_scrape_loop,
            ):
                key = _make_case_key(court_id, case.docket_number)
                if skip_parsed and cache.s3_key_exists(key):
                    continue
                if full_scrape and skip_parsed:
                    full_case = await _get_full_case(
                        court_id.value, str(case.case_uuid), scraper
                    )
                    if not full_case:
                        continue
                    case = full_case

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
    date_range_required: ClassVar[bool] = False

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
        parser.add_argument(
            "--archive-responses",
            action="store_true",
            default=False,
            help="If set the scraper will archive responses to S3.",
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue to dispatch S3 archive tasks to.",
        )
        parser.add_argument(
            "--throttle-min-items",
            dest="throttle_min_items",
            type=int,
            default=50,
            help="CeleryThrottle min queue depth; the throttle keeps the "
            "queue between this and 2x this value.",
        )
        parser.add_argument(
            "--skip-parsed",
            dest="skip_parsed",
            action="store_true",
            help="Whether to skip items which already have parsed files saved in S3.",
        )
        parser.add_argument(
            "--scrape-uuids",
            dest="scrape_uuids",
            type=str,
            default="",
            help="Path to a CSV of Florida court IDs and case UUIDs for targeted rescraping. Overrides the --backscrape-start, --backscrape-end, and --courts options.",
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
        backscrape_start: str = "",
        backscrape_end: str = "",
        courts: str,
        skip_parsed: bool,
        scrape_uuids: str,
        **options,
    ):
        logger.info("Setting up Florida back-scrape...")
        start = _parse_date(backscrape_start)
        end = _parse_date(backscrape_end)
        court_ids = self.parse_court_ids(courts)

        throttle, scraper, cache = self.throttle_scraper_and_cache(
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

        if scrape_uuids:
            p = Path(scrape_uuids)
            with p.open() as f:
                cases = [
                    (
                        FL_COURT_ID_MAP[c.strip()],
                        UUID(case_uuid.strip()),
                    )
                    for c, case_uuid in (line.split(",") for line in f)
                ]
            async_to_sync(_backfill_targeted)(
                cases=cases,
                throttle=throttle,
                queue_name=queue,
                scraper=scraper,
            )
            return

        if not backscrape_start or not backscrape_end:
            logger.error(
                "Both --backscrape-start and --backscrape-end are required."
            )
            return

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
            skip_parsed=skip_parsed,
            cache=cache,
        )
