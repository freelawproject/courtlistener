"""Management command for running BaseStateScraper backfill operations.

This command runs state-level docket scrapers that enumerate dockets across
multiple courts within a state, with rate limiting and retry support.
"""

import json
import re
import time
from collections.abc import Mapping
from datetime import date, datetime

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from juriscraper.lib.importer import build_module_list
from juriscraper.state.BaseStateScraper import BaseStateScraper

from cl.lib.command_utils import logger
from cl.lib.redis_utils import get_redis_interface
from cl.lib.storage import (
    S3GlacierInstantRetrievalStorage,
    clobbering_get_name,
)

REDIS_AUTORESUME_KEY = "scraper:TAMES:end-date"

REDIS = get_redis_interface("CACHE")


def get_last_checkpoint() -> date | None:
    stored_values = REDIS.hgetall(REDIS_AUTORESUME_KEY)
    if not (stored_values and stored_values.get("checkpoint")):
        return None
    latest_checkpoint = datetime.strptime(
        stored_values.get("checkpoint"),  # type: ignore [arg-type]
        "%Y-%m-%d",
    ).date()
    return latest_checkpoint


def set_last_checkpoint(checkpoint: date) -> None:
    pipe = REDIS.pipeline()
    pipe.hgetall(REDIS_AUTORESUME_KEY)
    log_info: Mapping[str | bytes, int | str] = {
        "checkpoint": checkpoint.isoformat(),
        "checkpoint_time": datetime.now().isoformat(),
    }
    pipe.hset(REDIS_AUTORESUME_KEY, mapping=log_info)
    pipe.expire(REDIS_AUTORESUME_KEY, 60 * 60 * 24 * 28)  # 4 weeks
    pipe.execute()


class RateLimitedRequestManager:
    """Request manager with rate limiting and 403 retry with exponential backoff.

    This wraps HTTP request handling with:
    - Rate limiting (configurable requests per second)
    - Automatic retry on 403 Forbidden with exponential backoff
    - Session management with Chrome headers

    Attributes:
        session: The requests Session used for HTTP requests
        requests_per_second: Maximum request rate
        max_backoff_seconds: Maximum time to wait during exponential backoff
        all_response_fn: Optional callback invoked after every HTTP response
    """

    def __init__(
        self,
        requests_per_second: float = 1.0,
        max_backoff_seconds: int = 300,
        session: requests.Session | None = None,
        all_response_fn=None,
    ) -> None:
        """Initialize the rate-limited request manager.

        Args:
            requests_per_second: Maximum requests per second (default 1.0)
            max_backoff_seconds: Maximum backoff time for 403 retries (default 300)
            session: Optional requests Session. If not provided, a new session
                will be created with default Juriscraper headers.
            all_response_fn: Optional callback function invoked after every
                HTTP response. Receives the request manager and response.
        """
        if session is not None:
            self.session: requests.Session | None = session
        else:
            self.session = requests.Session()
            # Match more closely a chrome browser
            self.session.headers.update(
                {
                    "User-Agent": {
                        "User-Agent": "Juriscraper",
                        "Cache-Control": "no-cache, max-age=0, must-revalidate",
                        "Pragma": "no-cache",
                    },
                    "Accept": (
                        "text/html,application/xhtml+xml,"
                        "application/xml;q=0.9,image/avif,"
                        "image/webp,image/apng,*/*;q=0.8,"
                        "application/signed-exchange;v=b3;q=0.7"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "sec-ch-ua": ('"Chromium";v="145", "Not:A-Brand";v="99"'),
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "Upgrade-Insecure-Requests": "1",
                }
            )

        self.requests_per_second = requests_per_second
        self.max_backoff_seconds = max_backoff_seconds
        self.all_response_fn = all_response_fn
        self._last_request_time: float | None = None
        self._min_interval = (
            1.0 / requests_per_second if requests_per_second > 0 else 0
        )

    def __enter__(self) -> "RateLimitedRequestManager":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # Leave the logging to Sentry
        self.close()

    def __del__(self) -> None:
        """Close the session when the manager is garbage collected."""
        self.close()

    def close(self) -> None:
        """Close the HTTP session."""
        if self.session:
            self.session.close()
            self.session = None

    def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limiting."""
        if self._last_request_time is None:
            return

        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        """Make a request with exponential backoff retry on 403.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            **kwargs: Additional arguments passed to session.request()

        Returns:
            The requests Response object

        Raises:
            requests.HTTPError: If max backoff time exceeded on 403
        """
        kwargs.setdefault("timeout", 60)
        backoff = 1
        total_wait = 0

        while True:
            self._wait_for_rate_limit()
            self._last_request_time = time.monotonic()

            if not self.session:
                raise ValueError(
                    "RequestManager has no session, likely invoked after closed."
                )
            response = self.session.request(method, url, **kwargs)

            if response.status_code != 403:
                response.raise_for_status()
                return response

            # Handle 403 with exponential backoff
            if total_wait >= self.max_backoff_seconds:
                logger.error(
                    "Max backoff time (%d seconds) exceeded for URL: %s",
                    self.max_backoff_seconds,
                    url,
                )
                response.raise_for_status()

            logger.warning(
                "Received 403 Forbidden for %s. Backing off for %d seconds (total: %d/%d). "
                "Response headers: %s Body (first 500 chars): %s",
                url,
                backoff,
                total_wait,
                self.max_backoff_seconds,
                dict(response.headers),
                response.text[:500],
            )
            time.sleep(backoff)
            total_wait += backoff
            backoff = min(backoff * 2, self.max_backoff_seconds - total_wait)
            if backoff <= 0:
                backoff = 1

    def request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        """Make an HTTP request with rate limiting and 403 retry.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            **kwargs: Additional arguments passed to session.request()

        Returns:
            The requests Response object
        """
        response = self._request_with_retry(method, url, **kwargs)

        if self.all_response_fn:
            self.all_response_fn(response)

        return response

    def merge_headers(self, headers: dict[str, str]) -> None:
        """Merge additional headers into the session headers."""
        if not self.session:
            raise ValueError(
                "RequestManager has no session, likely invoked after closed."
            )
        self.session.headers.update(headers)

    def get(self, url: str, **kwargs) -> requests.Response:
        """Make a GET request. See request() for details."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        """Make a POST request. See request() for details."""
        return self.request("POST", url, **kwargs)


def save_docket_response(
    response: requests.Response,
    scraper_class_name: str,
    case_meta: dict,
    court_id: str = "unknown_court",
    skip_meta: bool = False,
) -> None:
    """Store docket scraper response content and headers in S3.

    Args:
        response: The HTTP response to save
        scraper_class_name: Name of the scraper class (e.g., "TAMESScraper")
        court_id: Court identifier extracted from response data
        case_meta: Optional metadata dict from the scraper (e.g., case_number,
            date_filed, etc.) to save alongside the response
    """
    storage = S3GlacierInstantRetrievalStorage(
        naming_strategy=clobbering_get_name
    )

    # Docket number with non-s3-safe characters replaced with a _
    case_number = re.sub(
        r"[^0-9a-zA-Z!_.*'()-]",
        "_",
        (case_meta.get("case_number")),  # type: ignore [arg-type]
    )
    base_name = (
        f"responses/dockets/{scraper_class_name}/{court_id}/{case_number}"
    )

    headers_json = json.dumps(dict(response.headers), indent=4)
    storage.save(f"{base_name}_headers.json", ContentFile(headers_json))

    # Save case metadata if provided (skipped when batching handles meta separately)
    if case_meta is not None and not skip_meta:
        meta_json = json.dumps(case_meta, indent=4, default=str)
        storage.save(f"{base_name}_meta.json", ContentFile(meta_json))

    content = response.content
    extension = "html"

    content_name = f"{base_name}.{extension}"
    storage.save(content_name, ContentFile(content))


def save_search_response_factory(scraper_class_name: str):
    storage = S3GlacierInstantRetrievalStorage()
    prefix = f"responses/dockets/{scraper_class_name}/searches/"

    def save_search_reponse(response: requests.Response):
        now_str = datetime.now().strftime("%Y/%m/%d/%H_%M_%S_%f")
        path = f"{prefix}{now_str}.html"
        storage.save(path, ContentFile(response.content))

    return save_search_reponse


def parse_date_filed(date_str: str | None) -> date | None:
    """Parse a date_filed string in '%m/%d/%Y' format to a date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%m/%d/%Y").date()
    except ValueError:
        logger.warning("Failed to parse date_filed: %s", date_str)
        return None


def save_batch_meta(
    cases: list[dict],
    scraper_class_name: str,
) -> str | None:
    """Save batch metadata as a JSONL file to S3, named by date range.

    Args:
        cases: List of case metadata dicts.
        scraper_class_name: Name of the scraper class.

    Returns:
        The S3 path where the file was saved, or None if cases is empty.
    """
    if not cases:
        return None

    storage = S3GlacierInstantRetrievalStorage(
        naming_strategy=clobbering_get_name
    )

    parsed_dates = [
        d for case in cases if (d := parse_date_filed(case.get("date_filed")))
    ]

    if parsed_dates:
        earliest = min(parsed_dates).isoformat()
        latest = max(parsed_dates).isoformat()
    else:
        earliest = "unknown"
        latest = "unknown"

    path = (
        f"responses/dockets/{scraper_class_name}/batches/"
        f"{earliest}_to_{latest}_meta.jsonl"
    )

    lines = [json.dumps(case, default=str) for case in cases]
    content = "\n".join(lines) + "\n"
    storage.save(path, ContentFile(content.encode("utf-8")))

    logger.info(
        "Saved batch meta (%d cases, %s to %s) to %s",
        len(cases),
        earliest,
        latest,
        path,
    )
    return path


class Command(BaseCommand):
    help = "Runs BaseStateScraper backfill operations for docket enumeration."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scraper",
            help="The module path of the scraper to run (e.g., juriscraper.state.texas.tames)",
            required=True,
        )
        parser.add_argument(
            "--backscrape-start",
            dest="backscrape_start",
            help="Starting value for backscraper iterable creation. "
            "Each scraper handles the parsing of the argument,"
            "since the value may represent a year, a string, a date, etc.",
        )
        parser.add_argument(
            "--backscrape-end",
            dest="backscrape_end",
            help="End value for backscraper iterable creation.",
        )
        parser.add_argument(
            "--courts",
            dest="courts",
            help="Comma-separated list of court IDs to scrape (e.g., texas_cossup,texas_coa01). "
            "If not provided, all courts defined by the scraper will be used.",
        )
        parser.add_argument(
            "--search-rate",
            type=float,
            default=0.2,
            help="Maximum requests per second for the search (default: 0.2)",
        )
        parser.add_argument(
            "--case-rate",
            type=float,
            default=2.0,
            help="Maximum requests per second for the search (default: 2.0)",
        )
        parser.add_argument(
            "--max-backoff",
            type=int,
            default=300,
            help="Maximum seconds to wait during exponential backoff on 403 errors (default: 300)",
        )
        parser.add_argument(
            "--auto-resume",
            default=False,
            action="store_true",
            help="Auto resume the command using the last end-date stored in redis. ",
        )
        parser.add_argument(
            "--sleep",
            default=10,
            type=int,
            help="After every 100 entries, pause for this many minutes",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of cases to collect before writing a batch meta JSONL file and fetching case pages (default: 100)",
        )

    def handle(self, *args, **options):
        scraper_module_path = options["scraper"]

        # Validate date range is provided
        if not options.get("backscrape_start") or not options.get(
            "backscrape_end"
        ):
            raise CommandError(
                "Both --backscrape-start and --backscrape-end are required"
            )

        # Build the module list and import
        module_strings = build_module_list(scraper_module_path)
        if not module_strings:
            raise CommandError(
                f"Unable to import module: {scraper_module_path}. Aborting."
            )

        if len(module_strings) > 1:
            raise CommandError(
                f"Expected single module, got {len(module_strings)}. "
                "Please specify a single scraper module."
            )

        package, module = module_strings[0].rsplit(".", 1)
        mod = __import__(f"{package}.{module}", globals(), locals(), [module])

        # Find the scraper class (subclass of BaseStateScraper)
        scraper_class = None
        scraper_class_name = None
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseStateScraper)
                and attr is not BaseStateScraper
            ):
                scraper_class = attr
                scraper_class_name = attr_name
                break

        if scraper_class is None or scraper_class_name is None:
            raise CommandError(
                f"No BaseStateScraper subclass found in module: {scraper_module_path}"
            )

        auto_resume = False
        end_date = self._parse_date(options["backscrape_end"])

        if options.get("auto_resume"):
            auto_resume = True
            saved_checkpoint = get_last_checkpoint()
            if saved_checkpoint:
                end_date = saved_checkpoint
                logger.info("Autoresuming with an end date of %s", end_date)
            else:
                logger.info(
                    "No checkpoints found, using %s as end date, will add checkpoints for further autoresume",
                    end_date,
                )

        logger.info(
            "Starting docket backfill with scraper: %s", scraper_class_name
        )

        search_rm_args = {
            "requests_per_second": options["search_rate"],
            "max_backoff_seconds": options["max_backoff"],
        }

        case_rm_args = {
            "requests_per_second": options["case_rate"],
            "max_backoff_seconds": options["max_backoff"],
            # We are manually processing the saves here since we can do it with a bit more info
        }

        sleep_minutes = options.get("sleep")
        with (
            RateLimitedRequestManager(
                **search_rm_args
            ) as search_request_manager,
            RateLimitedRequestManager(**case_rm_args) as case_request_manager,
        ):
            # Instantiate the scraper with our rate-limited search request manager
            scraper = scraper_class(request_manager=search_request_manager)

            # Parse start date
            start_date = self._parse_date(options["backscrape_start"])

            # Determine courts to scrape
            courts = (
                [c.strip() for c in options["courts"].split(",")]
                if options["courts"]
                else None
            )

            logger.info(
                "Backfilling %d courts from %s to %s",
                len(courts or scraper.COURT_IDS),
                start_date,
                end_date,
            )

            batch_size = options["batch_size"]
            case_count = 0
            current_batch: list[dict] = []

            for case in scraper.backfill(courts, (start_date, end_date)):
                if not case.get("case_url"):
                    logger.warning("Case without case_url: %s", case)
                    continue

                current_batch.append(dict(case))
                if len(current_batch) < batch_size:
                    continue

                case_count += self._process_batch(
                    current_batch,
                    scraper_class_name,
                    case_request_manager,
                    auto_resume,
                    sleep_minutes,
                    case_count,
                )
                self._checkpoint_and_sleep(
                    case_count, case, auto_resume, sleep_minutes
                )

                current_batch = []

            # Final partial batch
            if current_batch:
                case_count += self._process_batch(
                    current_batch,
                    scraper_class_name,
                    case_request_manager,
                    auto_resume,
                    sleep_minutes,
                    case_count,
                )

            logger.info(
                "Backfill complete. Processed %d cases total.", case_count
            )

    def _process_batch(
        self,
        batch: list[dict],
        scraper_class_name: str,
        case_request_manager: RateLimitedRequestManager,
        auto_resume: bool,
        sleep_minutes: int,
        case_count_before: int,
    ) -> int:
        """Save batch meta JSONL, then fetch and save each case's HTML + headers.

        Returns the number of cases successfully fetched.
        """
        # The following line can be uncommented to save batches of case meta.
        # save_batch_meta(batch, scraper_class_name)

        fetched = 0
        for case in batch:
            case_url = case.get("case_url")
            if not case_url:
                continue

            court_id = case.get("court_code") or "unknown_court"
            try:
                case_response = case_request_manager.get(case_url)
                save_docket_response(
                    case_response,
                    scraper_class_name,
                    case,
                    court_id,
                    skip_meta=False,
                )
                fetched += 1
                running_count = case_count_before + fetched
            except requests.RequestException as e:
                logger.error("Failed to fetch case URL %s: %s", case_url, e)
        return fetched

    def _checkpoint_and_sleep(
        self,
        case_count: int,
        case: dict,
        auto_resume: bool,
        sleep_minutes: int,
    ) -> None:
        """Checkpoint to Redis and sleep at every batch boundary."""

        logger.info("Processed %d cases", case_count)

        if auto_resume:
            if parsed := parse_date_filed(case.get("date_filed")):
                set_last_checkpoint(parsed)
                logger.info("Checkpointed at %s", parsed)
            else:
                logger.warning(
                    "No parseable date_filed, no checkpoint: %s", case
                )

        if sleep_minutes > 0:
            logger.info("Sleeping %d minutes", sleep_minutes)
            time.sleep(sleep_minutes * 60)

    def _parse_date(self, date_str: str) -> date:
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
