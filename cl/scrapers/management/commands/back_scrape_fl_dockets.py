"""Command to back-scrape Florida dockets"""

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import ClassVar
from uuid import UUID

import botocore.exceptions
from asgiref.sync import async_to_sync
from django.core.management import CommandParser
from httpx import Response
from juriscraper.state.florida import FloridaCase, FloridaScraper
from juriscraper.state.florida.courts import FloridaCourtID
from juriscraper.state.RequestManager import (
    ExponentialBackoff,
    RequestHandler,
    RequestManager,
    ScheduledRequest,
)

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import logger
from cl.lib.decorators import retry
from cl.lib.storage import S3GlacierInstantRetrievalStorage
from cl.scrapers.management.utils import (
    ScraperCheckpointTracker,
    StateBackScrapeCommand,
    _make_case_number_key,
    _parse_date,
)
from cl.scrapers.tasks import save_response_to_s3

S3_BASE = Path("responses/dockets/florida")


@dataclass
class S3Cache(RequestHandler):
    """Handler to use S3 as a (successful) response cache

    :ivar base: The prefix where cached values are stored
    :ivar save: Whether to archive responses
    :ivar load: Whether to intercept requests and load responses from S3 if available
    :ivar throttle: The celery throttle to use when adding responses to the queue
    :ivar queue_name: The celery queue to dispatch archive tasks to
    :ivar storage: The S3 storage backend to use for archiving and retrieval"""

    base: Path
    save: bool
    load: bool
    throttle: CeleryThrottle
    queue_name: str
    storage: S3GlacierInstantRetrievalStorage = field(
        default_factory=S3GlacierInstantRetrievalStorage
    )

    @retry(
        (
            botocore.exceptions.HTTPClientError,
            botocore.exceptions.ConnectionError,
        ),
        delay=1,
        backoff=2,
    )
    @lru_cache(512)
    def s3_key_exists(self, key: str) -> bool:
        """Cached check for whether a key exists in S3 with retries. Allows us to avoid an extra `storage.exists` call
        when `save` and `load` are both enabled."""
        if self.storage.exists(key):
            return True
        return False

    def make_s3_key(self, request: ScheduledRequest) -> str:
        url_path = request.url.path.lower().strip("/")
        url_params = "&".join(
            [f"{k}={v}" for k, v in sorted(request.url.params.items())]
        )
        method = request.method.upper()
        request_hash = hashlib.sha1(
            f"{method}|{url_path}|{url_params}".encode()
        ).hexdigest()
        return str(self.base / url_path / request_hash)

    def load_from_s3(self, request: ScheduledRequest) -> Response | None:
        key = self.make_s3_key(request)

        try:
            if not self.s3_key_exists(key):
                logger.info("Did not find %s in S3", request.url.path.lower())
                return None

            logger.info("Loading %s from S3", request.url.path.lower())

            with self.storage.open(key, "rb") as f:
                return Response(200, content=f.read())
        except Exception:
            logger.exception(
                "Failed to load response from archive for %s",
                request.url.path.lower(),
            )
            return None

    def save_to_s3(
        self, request: ScheduledRequest, response: Response
    ) -> None:
        key = self.make_s3_key(request)
        try:
            # Don't try to cache responses that we pulled from the cache
            if self.load and self.s3_key_exists(key):
                return
            self.throttle.maybe_wait()
            save_response_to_s3.si(key, response.content).set(
                queue=self.queue_name
            ).apply_async()
        except Exception:
            logger.exception(
                "Failed to queue archive response for %s", request.url
            )

    async def before_send(
        self, manager: RequestManager, request: ScheduledRequest
    ) -> None:
        if not self.load:
            return
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, self.load_from_s3, request)
        if response:
            request.response.set_result(response)

    async def listen(self, manager: RequestManager, request: ScheduledRequest):
        if not self.save:
            return

        try:
            response = await request.response
        except Exception:
            logger.exception(
                "Cache listener failed to get response for %s", request.url
            )
            return

        self.save_to_s3(request, response)

    def __hash__(self) -> int:
        return hash(id(self))


_COURT_ID_MAP: dict[str, FloridaCourtID] = {
    "fla": FloridaCourtID.SUPREME_COURT,
    "fladistctapp1": FloridaCourtID.FIRST_COA,
    "fladistctapp2": FloridaCourtID.SECOND_COA,
    "fladistctapp3": FloridaCourtID.THIRD_COA,
    "fladistctapp4": FloridaCourtID.FOURTH_COA,
    "fladistctapp5": FloridaCourtID.FIFTH_COA,
    "fladistctapp6": FloridaCourtID.SIXTH_COA,
}


async def _get_full_case(
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

        key = f"{S3_BASE}/parsed/{court_id.value}/{_make_case_number_key(case.docket_number)}.json"

        throttle.maybe_wait()
        save_response_to_s3.si(key, content).set(
            queue=queue_name
        ).apply_async()

        if i % 100 == 0:
            logger.info(
                "Completed scrape of %d/%d cases (%d.2%%)",
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
    storage: S3GlacierInstantRetrievalStorage,
    skip_parsed: bool,
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
                key = f"{S3_BASE}/parsed/{court_id.value}/{_make_case_number_key(case.docket_number)}.json"
                if skip_parsed and storage.exists(key):
                    continue
                if full_scrape and skip_parsed:
                    full_case = await _get_full_case(
                        court_id.value, str(case.case_uuid), scraper
                    )
                    if not full_case:
                        continue
                    case = full_case

                content = case.model_dump_json(ensure_ascii=True).encode(
                    "utf-8"
                )

                throttle.maybe_wait()
                save_response_to_s3.si(key, content).set(
                    queue=queue_name
                ).apply_async()

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


class Command(StateBackScrapeCommand):
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
        super().add_arguments(parser)

        parser.add_argument(
            "--rps",
            type=float,
            default=2.5,
            help="Requests per second limit for the scraper.",
        )
        parser.add_argument(
            "--max-retries",
            dest="max_retries",
            type=int,
            default=3,
            help="Maximum number of retries for failed requests.",
        )
        parser.add_argument(
            "--backoff",
            type=float,
            default=2.0,
            help="Base time to wait before retrying failed requests.",
        )
        parser.add_argument(
            "--backoff-growth",
            dest="backoff_growth",
            type=float,
            default=2.0,
            help="Growth factor for the delay between retries.",
        )
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
            help="Path to a CSV of Florida court IDs and case UUIDs for targeted rescraping. Overrides the --backscrape-start, --backscrape-end, --courts, and --use-cache options.",
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
        throttle = CeleryThrottle(
            queue_name=queue, min_items=throttle_min_items
        )

        storage = S3GlacierInstantRetrievalStorage()

        scraper = FloridaScraper(
            rps=rps,
            retry=ExponentialBackoff(
                max_retries=max_retries,
                backoff=backoff,
                backoff_growth=backoff_growth,
            ),
            handlers=[
                S3Cache(
                    base=S3_BASE,
                    save=archive_responses,
                    load=use_cache,
                    throttle=throttle,
                    queue_name=queue,
                    storage=storage,
                )
            ],
        )

        logger.info("Setting up Florida back-scrape...")
        if scrape_uuids:
            p = Path(scrape_uuids)
            with p.open() as f:
                cases = [
                    (
                        _COURT_ID_MAP[c.strip()],
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
        start = _parse_date(backscrape_start)
        end = _parse_date(backscrape_end)
        court_ids = [
            _COURT_ID_MAP[c.strip()] for c in courts.split(",") if c.strip()
        ]
        if not court_ids:
            logger.warning("No courts specified. Defaulting to all courts.")
            court_ids = list(_COURT_ID_MAP.values())

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
            storage=storage,
            skip_parsed=skip_parsed,
        )
