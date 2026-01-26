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
from cl.lib.storage import S3GlacierInstantRetrievalStorage

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
    - Session management with default Juriscraper headers

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
            self.session.headers.update(
                {
                    "User-Agent": "Juriscraper",
                    "Cache-Control": "no-cache, max-age=0, must-revalidate",
                    "Pragma": "no-cache",
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
            sleep_time = self._min_interval - elapsed
            time.sleep(sleep_time)

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
                "Received 403 Forbidden for %s. Backing off for %d seconds (total: %d/%d)",
                url,
                backoff,
                total_wait,
                self.max_backoff_seconds,
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
) -> None:
    """Store docket scraper response content and headers in S3.

    Args:
        response: The HTTP response to save
        scraper_class_name: Name of the scraper class (e.g., "TAMESScraper")
        court_id: Court identifier extracted from response data
        case_meta: Optional metadata dict from the scraper (e.g., case_number,
            date_filed, etc.) to save alongside the response
    """
    storage = S3GlacierInstantRetrievalStorage()

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

    # Save case metadata if provided
    if case_meta is not None:
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
            "all_response_fn": save_search_response_factory(
                scraper_class_name
            ),
        }

        case_rm_args = {
            "requests_per_second": options["case_rate"],
            "max_backoff_seconds": options["max_backoff"],
            # We are manually processing the saves here since we can do it with a bit more info
        }

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

            case_count = 0
            for case in scraper.backfill(courts, (start_date, end_date)):
                case_url = case.get("case_url")
                if not case_url:
                    logger.warning("Case without case_url: %s", case)
                    continue

                # Extract court_id from case data if available
                court_id = case.get("court_code") or "unknown_court"
                # Fetch and save the case page
                try:
                    case_response = case_request_manager.get(case_url)
                    save_docket_response(
                        case_response,
                        scraper_class_name,
                        dict(case),
                        court_id,
                    )
                    case_count += 1

                    if case_count % 100 == 0:
                        logger.info("Processed %d cases", case_count)
                        # TAMES search defaults to descending by date
                        # checkpoint every 100/case-rate seconds
                        if auto_resume and not case.get("date_filed"):
                            logger.warning(
                                f"No case date, no checkpoint:{case}"
                            )
                        if auto_resume and case.get("date_filed"):
                            try:
                                latest_date = datetime.strptime(
                                    case.get("date_filed"), "%m/%d/%Y"
                                ).date()
                                set_last_checkpoint(latest_date)
                                logger.info("Checkpointed at %s", latest_date)
                            except ValueError:
                                logger.warning(
                                    "Failed to save checkpoint for (date_filed=%s). Using prior checkpoint.",
                                    case.get("date_filed"),
                                )

                except requests.RequestException as e:
                    logger.error(
                        "Failed to fetch case URL %s: %s", case_url, e
                    )

            logger.info(
                "Backfill complete. Processed %d cases total.", case_count
            )

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
