"""Command to back-scrape Florida dockets"""

import asyncio
import queue
from dataclasses import dataclass
from datetime import date

from asgiref.sync import async_to_sync
from django.core.management import CommandParser
from httpx import Response
from juriscraper.state.florida import FloridaScraper
from juriscraper.state.florida.courts import FloridaCourtID
from juriscraper.state.RequestManager import (
    RequestHandler,
    RequestManager,
    ScheduledRequest,
)

from cl.lib.command_utils import logger
from cl.lib.storage import (
    S3GlacierInstantRetrievalStorage,
    clobbering_get_name,
)
from cl.scrapers.management.utils import (
    ScraperCheckpointTracker,
    StateBackScrapeCommand,
    _make_case_number_key,
)

S3_BASE = "responses/dockets/florida"


def make_s3_key(request: ScheduledRequest) -> str:
    url_path = request.url.path.lower()
    url_params = "&".join(
        [f"{k}={v}" for k, v in sorted(request.url.params.items())]
    )
    method = request.method.upper()
    return hex(hash((method, url_path, url_params)))


@dataclass
class S3Cache(RequestHandler):
    """Handler to use S3 as a (successful) response cache

    :ivar base: The prefix where cached values are stored
    :ivar save: Whether to archive responses
    :ivar load: Whether to intercept requests and load responses from S3 if available"""

    base: str
    save: bool
    load: bool
    save_queue: queue.Queue[tuple[str, bytes]]

    def load_from_s3(self, request: ScheduledRequest) -> Response | None:
        storage = S3GlacierInstantRetrievalStorage(
            naming_strategy=clobbering_get_name
        )
        key = f"{self.base}/{make_s3_key(request)}"

        if not storage.exists(key):
            return None

        with storage.open(key, "rb") as f:
            return Response(200, content=f.read())

    def save_to_s3(self, response: Response) -> None:
        storage = S3GlacierInstantRetrievalStorage()
        key = f"{self.base}/{response.url.path}"
        # Don't try to cache responses that we pulled from the cache
        if self.load and storage.exists(key):
            return
        logger.info(f"Archiving {key}")
        self.save_queue.put((key, response.content))

    async def before_send(
        self, manager: RequestManager, request: ScheduledRequest
    ) -> None:
        if not self.load:
            return
        loop = asyncio.get_running_loop()
        if response := await loop.run_in_executor(
            None, self.load_from_s3, request
        ):
            request.response.set_result(response)

    async def listen(self, manager: RequestManager, request: ScheduledRequest):
        if not self.save:
            return

        try:
            response = await request.response
        except Exception:
            return

        loop = asyncio.get_running_loop()
        _ = loop.run_in_executor(None, self.save_to_s3, response)


def _archive_loop(responses: queue.Queue[tuple[str, bytes]]) -> None:
    storage = S3GlacierInstantRetrievalStorage(
        naming_strategy=clobbering_get_name
    )

    while True:
        try:
            key, content = responses.get()
        except queue.ShutDown:
            break

        with storage.open(key, "wb") as f:
            f.write(content)

        responses.task_done()
        logger.info(f"Archived {key} to {storage.bucket_name}")


_COURT_ID_MAP: dict[str, FloridaCourtID] = {
    "fla": FloridaCourtID.SUPREME_COURT,
    "fladistctapp1": FloridaCourtID.FIRST_COA,
    "fladistctapp2": FloridaCourtID.SECOND_COA,
    "fladistctapp3": FloridaCourtID.THIRD_COA,
    "fladistctapp4": FloridaCourtID.FOURTH_COA,
    "fladistctapp5": FloridaCourtID.FIFTH_COA,
    "fladistctapp6": FloridaCourtID.SIXTH_COA,
}


async def _backfill(
    date_ranges: dict[FloridaCourtID, tuple[date, date]],
    full_scrape: bool,
    checkpoint_trackers: dict[FloridaCourtID, ScraperCheckpointTracker],
    scraper: FloridaScraper,
    save_queue: queue.Queue[tuple[str, bytes]],
):
    archive_loop = asyncio.to_thread(_archive_loop, save_queue)

    for court_id, (start_date, end_date) in date_ranges.items():
        i = 0
        async for case in scraper.backfill(
            start_date, end_date, court_ids=[court_id], full_scrape=full_scrape
        ):
            key = f"{S3_BASE}/parsed/{_make_case_number_key(case.docket_number)}.json"
            content = case.model_dump_json(ensure_ascii=True).encode("utf-8")
            save_queue.put((key, content))
            i += 1
            if i % 100 == 0:
                checkpoint_trackers[court_id].set(case.date_filed)

    save_queue.join()
    save_queue.shutdown()
    await archive_loop


class Command(StateBackScrapeCommand):
    help = "Back-scrape Florida dockets"

    checkpoint_trackers = {
        FloridaCourtID.SUPREME_COURT: ScraperCheckpointTracker("acisflsc"),
        FloridaCourtID.FIRST_COA: ScraperCheckpointTracker("acisfl1ac"),
        FloridaCourtID.SECOND_COA: ScraperCheckpointTracker("acisfl2ac"),
        FloridaCourtID.THIRD_COA: ScraperCheckpointTracker("acisfl3ac"),
        FloridaCourtID.FOURTH_COA: ScraperCheckpointTracker("acisfl4ac"),
        FloridaCourtID.FIFTH_COA: ScraperCheckpointTracker("acisfl5ac"),
        FloridaCourtID.SIXTH_COA: ScraperCheckpointTracker("acisfl6ac"),
    }

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
        backscrape_start: date,
        backscrape_end: date,
        courts: str,
        **options,
    ):
        court_ids = [_COURT_ID_MAP[c.strip()] for c in courts.split(",")]
        save_queue: queue.Queue[tuple[str, bytes]] = queue.Queue(maxsize=2048)
        scraper = FloridaScraper(
            rps=rps,
            max_retries=max_retries,
            backoff=backoff,
            backoff_growth=backoff_growth,
            handlers=[
                S3Cache(
                    base=S3_BASE,
                    save=archive_responses,
                    load=use_cache,
                    save_queue=save_queue,
                )
            ],
        )

        if auto_resume:
            checkpoints = {
                cid: self.checkpoint_trackers[cid].get() for cid in court_ids
            }
        else:
            checkpoints = {}

        date_ranges = {
            cid: (checkpoints.get(cid) or backscrape_start, backscrape_end)
            for cid in court_ids
        }

        async_to_sync(_backfill)(
            date_ranges=date_ranges,
            full_scrape=full_scrape,
            checkpoint_trackers=self.checkpoint_trackers,
            scraper=scraper,
            save_queue=save_queue,
        )
