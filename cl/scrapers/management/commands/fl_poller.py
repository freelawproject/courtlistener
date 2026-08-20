import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from asgiref.sync import async_to_sync
from django.core.management import CommandParser
from juriscraper.state.florida import FloridaScraper
from juriscraper.state.florida.cases import FloridaCase, FloridaCourtID
from juriscraper.state.florida.common import (
    FloridaPaginatedResults,
    FloridaPaginatedResultsParser,
)
from juriscraper.state.florida.scraper import CourtMetadata, PaginationFailed
from pydantic import AliasPath, BaseModel, ConfigDict, Field
from pydantic.types import UUID4

from cl.corpus_importer.tasks import fl_ingest_docket_task
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import logger
from cl.scrapers.management.commands.back_scrape_fl_dockets import (
    save_case_to_s3,
)
from cl.scrapers.management.utils import (
    FLScrapeCommand,
    ScraperCheckpointTracker,
    StatePollCommand,
)


class FloridaUpdate(BaseModel):
    # Frozen so instances are hashable for deduplication
    model_config = ConfigDict(frozen=True)

    case_uuid: UUID4 = Field(
        validation_alias=AliasPath("caseHeader", "caseInstanceUUID")
    )
    court_external_id: int = Field(
        validation_alias=AliasPath("caseHeader", "courtID")
    )


S3_BASE = Path("responses/dockets/florida")

DE_DOC_ENDPOINT = (
    "https://acis-api.flcourts.gov/courts/cms/docketentrydocuments"
)
DOCKET_ENDPOINT = "https://acis-api.flcourts.gov/courts/cms/cases"


class FloridaDocumentPollParser(FloridaPaginatedResultsParser[FloridaUpdate]):
    def parse_full(self, i: str) -> FloridaPaginatedResults[FloridaUpdate]:
        return FloridaPaginatedResults[FloridaUpdate].model_validate_json(i)


class Command(FLScrapeCommand, StatePollCommand):
    help = "Continuously polls Florida ACIS for new cases and backfills when new entries are detected."

    checkpoint_tracker: ClassVar[ScraperCheckpointTracker] = (
        ScraperCheckpointTracker("flacis")
    )

    def add_arguments(self, parser: CommandParser):
        super().add_arguments(parser)

        parser.add_argument(
            "--no-download-attachments",
            type=bool,
            default=False,
            help="Set to download attachments for newly discovered dockets.",
        )
        parser.add_argument(
            "--auto-resume",
            type=bool,
            default=False,
            help="Set to resume polling from the last saved checkpoint.",
        )

    def handle(
        self,
        *args,
        rps: float,
        max_retries: int,
        backoff: float,
        backoff_growth: float,
        archive_responses: bool,
        queue: str,
        throttle_min_items: int,
        polling_delay: int,
        case_backfill_days: int,
        no_download_attachments: bool,
        courts: str | None,
        auto_resume: bool,
        **options,
    ):
        court_ids = self.parse_court_ids(courts)

        throttle, scraper, _ = self.throttle_scraper_and_cache(
            rps,
            max_retries,
            backoff,
            backoff_growth,
            # Since we're fetching updates, pulling from the cache would be counterproductive
            False,
            # But we still want to save responses in case there's a parsing failure
            archive_responses,
            queue,
            throttle_min_items,
            S3_BASE,
        )

        checkpoint = None
        if auto_resume:
            checkpoint = self.checkpoint_tracker.get()
            if not checkpoint:
                logger.warning(
                    "No checkpoint found. Falling back to --case-backfill-days=%d",
                    case_backfill_days,
                )
        if checkpoint:
            start = datetime(
                year=checkpoint.year,
                month=checkpoint.month,
                day=checkpoint.day,
            )
        else:
            start = datetime.now(UTC) - timedelta(days=case_backfill_days)

        async_to_sync(self.poll)(
            throttle,
            scraper,
            court_ids,
            polling_delay,
            start,
            queue,
            not no_download_attachments,
        )

    def send_merge_task(
        self,
        case: FloridaCase,
        throttle: CeleryThrottle,
        queue_name: str,
        download_attachments: bool,
    ):
        throttle.maybe_wait()
        self.checkpoint_tracker.set(case.date_filed)
        fl_ingest_docket_task.si(case, download_attachments).set(
            queue=queue_name
        ).apply_async()

    async def poll(
        self,
        throttle: CeleryThrottle,
        scraper: FloridaScraper,
        courts: list[FloridaCourtID],
        polling_delay: int,
        start: datetime,
        queue_name: str,
        download_attachments: bool,
    ):
        scraper_courts = await scraper.courts
        external_id_map = {
            metadata.court.external_identifier: court
            for court, metadata in scraper_courts.items()
        }
        last_polled = start
        while True:
            # Add a little overlap between segments to make extra sure we don't miss anything
            now = datetime.now(UTC) - timedelta(minutes=1)
            logger.info(
                "Looking for new and updated cases from %s to %s",
                last_polled,
                now,
            )
            seen = set()
            async for update in self.gather_all(
                scraper, scraper_courts, courts, last_polled
            ):
                logger.info("Got update: %s", update)
                if update in seen:
                    logger.info("Duplicate update. Skipping.")
                    continue
                seen.add(update)
                court_id = external_id_map[update.court_external_id]
                try:
                    maybe_case = await scraper.fetch_case_data(
                        str(update.case_uuid),
                        court_id.value,
                    )
                except Exception:
                    logger.exception(
                        "Failed to fetch case data for %s",
                        update.case_uuid,
                    )
                    continue
                if isinstance(maybe_case, Exception):
                    logger.error(
                        "Failed to fetch case data for %s: %r",
                        update.case_uuid,
                        maybe_case,
                    )
                    continue
                case, errors = maybe_case
                if errors:
                    logger.error(
                        "Failed to fetch case data for %s: %r",
                        update.case_uuid,
                        errors,
                    )
                    continue
                save_case_to_s3(
                    court_id,
                    case,
                    throttle,
                    queue_name,
                )
                self.send_merge_task(
                    case, throttle, queue_name, download_attachments
                )
            last_polled = now
            await asyncio.sleep(polling_delay * 60)

    async def gather_all(
        self,
        scraper: FloridaScraper,
        scraper_courts: dict[FloridaCourtID, CourtMetadata],
        courts: list[FloridaCourtID],
        start: datetime,
    ) -> AsyncGenerator[FloridaUpdate]:
        async for update in self.gather_updated(
            scraper, scraper_courts, courts, start
        ):
            yield update
        async for update in self.gather_new(
            scraper, scraper_courts, courts, start
        ):
            yield update

    async def gather_new(
        self,
        scraper: FloridaScraper,
        scraper_courts: dict[FloridaCourtID, CourtMetadata],
        courts: list[FloridaCourtID],
        start: datetime,
    ) -> AsyncGenerator[FloridaUpdate]:
        logger.info("Checking for cases since %s", start)
        for court_id in courts:
            parser = FloridaDocumentPollParser(court_id=court_id.value)
            async for page in scraper._enumerate_pages(
                DOCKET_ENDPOINT,
                parser,
                {
                    "caseHeader.courtID": str(
                        scraper_courts[court_id].court.resource_id
                    ),
                    "caseHeader.filedDateFrom": start.strftime(
                        "%Y-%m-%dT%H:%M:%S.000Z"
                    ),
                    "sort": "caseHeader.filedDate,asc",
                },
            ):
                match page:
                    case PaginationFailed() as e:
                        logger.error("Failed to get page: %r", e)
                    case FloridaPaginatedResults(results=results):
                        for result in results:
                            yield result

    async def gather_updated(
        self,
        scraper: FloridaScraper,
        scraper_courts: dict[FloridaCourtID, CourtMetadata],
        courts: list[FloridaCourtID],
        start: datetime,
    ) -> AsyncGenerator[FloridaUpdate]:
        parser = FloridaDocumentPollParser(court_id="fl")
        logger.info(
            "Checking docketentrydocuments endpoint for new entries since %s",
            start,
        )
        for court_id in courts:
            async for page in scraper._enumerate_pages(
                DE_DOC_ENDPOINT,
                parser,
                {
                    "sort": "docketEntryHeader.filedDate,asc",
                    "caseHeader.courtID": str(
                        scraper_courts[court_id].court.resource_id
                    ),
                    "docketEntryHeader.docketEntryFiledDateFrom": start.strftime(
                        "%Y-%m-%dT%H:%M:%S.000Z"
                    ),
                },
            ):
                match page:
                    case PaginationFailed() as e:
                        logger.error("Failed to get page: %r", e)
                    case FloridaPaginatedResults(results=results):
                        for result in results:
                            yield result
