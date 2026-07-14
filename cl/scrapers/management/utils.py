import asyncio
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

import botocore.exceptions
from django.core.management import CommandError
from django.core.management.base import BaseCommand, CommandParser
from httpx import Response
from juriscraper.state.florida import FloridaScraper
from juriscraper.state.florida.courts import FloridaCourtID
from juriscraper.state.RequestManager import (
    ExponentialBackoff,
    RequestHandler,
    RequestManager,
    ScheduledRequest,
)
from redis import Redis

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import logger
from cl.lib.decorators import retry
from cl.lib.redis_utils import get_redis_interface
from cl.lib.storage import S3GlacierInstantRetrievalStorage
from cl.scrapers.tasks import save_response_to_s3


def _parse_date(date_str: str) -> date:
    """Parse a date string in various formats.

    Args:
        date_str: Date string (supports YYYY-MM-DD, MM/DD/YYYY, etc.)

    Returns:
        Parsed date object

    Raises:
        CommandError: If date cannot be parsed
    """
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    raise CommandError(
        f"Unable to parse date: {date_str}. "
        "Use format YYYY-MM-DD or MM/DD/YYYY"
    )


_INVALID_CASE_NUMBER_CHARS = re.compile(r"[^0-9a-zA-Z!_.*'()-]")


def _make_case_number_key(case_number: str) -> str:
    return _INVALID_CASE_NUMBER_CHARS.sub("_", case_number)


class ScraperCheckpointTracker:
    def __init__(self, key: str, *, redis: Redis | None = None):
        self.autoresume_key: str = f"scraper:{key}:end-date"
        self.redis: Redis = redis or get_redis_interface("CACHE")

    def get(self) -> date | None:
        stored_values = self.redis.hgetall(self.autoresume_key)
        if not stored_values:
            return None
        stored_checkpoint = stored_values.get("checkpoint")
        if not stored_checkpoint:
            return None
        latest_checkpoint = datetime.strptime(
            stored_checkpoint,
            "%Y-%m-%d",
        ).date()
        return latest_checkpoint

    def set(self, checkpoint: date) -> None:
        pipe = self.redis.pipeline()
        pipe.hgetall(self.autoresume_key)
        log_info: Mapping[str | bytes, int | str] = {
            "checkpoint": checkpoint.isoformat(),
            "checkpoint_time": datetime.now().isoformat(),
        }
        pipe.hset(self.autoresume_key, mapping=log_info)
        pipe.expire(self.autoresume_key, 60 * 60 * 24 * 28)  # 4 weeks
        pipe.execute()


class StateBackScrapeCommand(BaseCommand):
    checkpoint_tracker: ClassVar[ScraperCheckpointTracker]
    date_range_required: ClassVar[bool] = True

    def add_arguments(self, parser: CommandParser):
        super(StateBackScrapeCommand, self).add_arguments(parser)
        parser.add_argument(
            "--backscrape-start",
            dest="backscrape_start",
            help="Starting value for backscraper iterable creation. "
            "Each scraper handles the parsing of the argument,"
            "since the value may represent a year, a string, a date, etc.",
            required=self.date_range_required,
        )
        parser.add_argument(
            "--backscrape-end",
            dest="backscrape_end",
            help="End value for backscraper iterable creation.",
            required=self.date_range_required,
        )
        parser.add_argument(
            "--courts",
            dest="courts",
            help="Comma-separated list of court IDs to scrape (e.g., texas_cossup,texas_coa01). "
            "If not provided, all courts defined by the scraper will be used.",
            default="",
        )
        parser.add_argument(
            "--auto-resume",
            default=False,
            action="store_true",
            help="Auto resume the command using the last end-date stored in redis.",
        )


class StatePollCommand(BaseCommand):
    def add_arguments(self, parser: CommandParser):
        super(StatePollCommand, self).add_arguments(parser)
        parser.add_argument(
            "--polling-delay",
            type=int,
            default=60,
            help="Minutes to sleep between poll cycles.",
        )
        parser.add_argument(
            "--case-backfill-days",
            type=int,
            default=1,
            help="Number of days to look back for backfill.",
        )
        parser.add_argument(
            "--courts",
            default=None,
            help=(
                "Comma-separated list of court IDs to poll (e.g., texas_cossup,texas_coa01)."
            ),
        )


FL_COURT_ID_MAP: dict[str, FloridaCourtID] = {
    "fla": FloridaCourtID.SUPREME_COURT,
    "fladistctapp1": FloridaCourtID.FIRST_COA,
    "fladistctapp2": FloridaCourtID.SECOND_COA,
    "fladistctapp3": FloridaCourtID.THIRD_COA,
    "fladistctapp4": FloridaCourtID.FOURTH_COA,
    "fladistctapp5": FloridaCourtID.FIFTH_COA,
    "fladistctapp6": FloridaCourtID.SIXTH_COA,
}


class FLScrapeCommand(BaseCommand):
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

    def parse_court_ids(self, courts: str | None) -> list[FloridaCourtID]:
        if courts is None:
            courts = ""
        court_ids = [
            FL_COURT_ID_MAP[c.strip()] for c in courts.split(",") if c.strip()
        ]
        if not court_ids:
            logger.warning("No courts specified. Defaulting to all courts.")
            court_ids = list(FL_COURT_ID_MAP.values())
        return court_ids

    def throttle_and_scraper(
        self,
        rps: float,
        max_retries: int,
        backoff: float,
        backoff_growth: float,
        use_cache: bool,
        archive_responses: bool,
        queue: str,
        throttle_min_items: int,
        s3_base: Path,
    ) -> tuple[CeleryThrottle, FloridaScraper]:
        """Initializes a celery queue throttle and Florida scraper with the given parameters and returns them"""
        throttle = CeleryThrottle(
            queue_name=queue, min_items=throttle_min_items
        )

        scraper = FloridaScraper(
            rps=rps,
            retry=ExponentialBackoff(
                max_retries=max_retries,
                backoff=backoff,
                backoff_growth=backoff_growth,
            ),
            handlers=[
                S3Cache(
                    base=s3_base,
                    save=archive_responses,
                    load=use_cache,
                    throttle=throttle,
                    queue_name=queue,
                )
            ],
        )

        return throttle, scraper


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
