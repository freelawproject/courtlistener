"""Management command for running BaseStateScraper backfill operations.

This command runs state-level docket scrapers that enumerate dockets across
multiple courts within a state, with rate limiting and retry support.
"""

import json
import time
from datetime import date, datetime

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from juriscraper.lib.importer import build_module_list
from juriscraper.state.BaseStateScraper import BaseStateScraper

from cl.lib.command_utils import logger
from cl.lib.storage import S3GlacierInstantRetrievalStorage
from cl.scrapers.management.commands.cl_back_scrape_opinions import (
    add_backscraper_arguments,
)


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
            self.session = session
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

    def __del__(self) -> None:
        """Close the session when the manager is garbage collected."""
        self.close()

    def close(self) -> None:
        """Close the HTTP session."""
        if self.session:
            self.session.close()

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

            response = self.session.request(method, url, **kwargs)

            if response.status_code != 403:
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
            self.all_response_fn(self, response)

        return response

    def merge_headers(self, headers: dict[str, str]) -> None:
        """Merge additional headers into the session headers."""
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
    court_id: str = "unknown_court",
    case_meta: dict | None = None,
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

    now_str = datetime.now().strftime("%Y/%m/%d/%H_%M_%S_%f")
    base_name = f"responses/dockets/{scraper_class_name}/{court_id}/{now_str}"

    headers_json = json.dumps(dict(response.headers), indent=4)
    storage.save(f"{base_name}_headers.json", ContentFile(headers_json))

    # Save case metadata if provided
    if case_meta is not None:
        meta_json = json.dumps(case_meta, indent=4, default=str)
        storage.save(f"{base_name}_meta.json", ContentFile(meta_json))

    try:
        content: str | bytes = json.dumps(
            json.loads(response.content), indent=4
        )
        extension = "json"
    except (UnicodeDecodeError, json.decoder.JSONDecodeError):
        content = response.content
        extension = "html"

    content_name = f"{base_name}.{extension}"
    storage.save(content_name, ContentFile(content))


class Command(BaseCommand):
    help = "Runs BaseStateScraper backfill operations for docket enumeration."

    def add_arguments(self, parser):
        parser.add_argument(
            "court_id",
            help="The module path of the scraper to run (e.g., juriscraper.state.texas.tames)",
        )
        add_backscraper_arguments(parser)
        parser.add_argument(
            "--courts",
            dest="courts",
            help="Comma-separated list of court IDs to scrape (e.g., texas_cossup,texas_coa01). "
            "If not provided, all courts defined by the scraper will be used.",
        )
        parser.add_argument(
            "--rate",
            type=float,
            default=1.0,
            help="Maximum requests per second for the scraper (default: 1.0)",
        )
        parser.add_argument(
            "--max-backoff",
            type=int,
            default=300,
            help="Maximum seconds to wait during exponential backoff on 403 errors (default: 300)",
        )

    def handle(self, *args, **options):
        scraper_module_path = options["court_id"]

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

        logger.info(
            "Starting docket backfill with scraper: %s", scraper_class_name
        )

        # Create rate-limited request manager with response saving callback
        def save_scraper_response(manager, response):
            court_id = "unknown_court"
            save_docket_response(response, scraper_class_name, court_id)

        request_manager = RateLimitedRequestManager(
            requests_per_second=options["rate"],
            max_backoff_seconds=options["max_backoff"],
            all_response_fn=save_scraper_response,
        )

        try:
            # Instantiate the scraper with our rate-limited request manager
            scraper = scraper_class(request_manager=request_manager)

            # Parse date range
            start_date = self._parse_date(options["backscrape_start"])
            end_date = self._parse_date(options["backscrape_end"])

            # Determine courts to scrape
            if options.get("courts"):
                courts = [c.strip() for c in options["courts"].split(",")]
            elif (
                hasattr(scraper_class, "COURT_IDS") and scraper_class.COURT_IDS
            ):
                courts = scraper_class.COURT_IDS
            else:
                raise CommandError(
                    "No courts specified and scraper has no COURT_IDS defined"
                )

            logger.info(
                "Backfilling %d courts from %s to %s",
                len(courts),
                start_date,
                end_date,
            )

            # Create a separate session for fetching case URLs
            case_session = requests.Session()
            case_session.headers.update(
                {
                    "User-Agent": "Juriscraper",
                    "Cache-Control": "no-cache, max-age=0, must-revalidate",
                    "Pragma": "no-cache",
                }
            )

            case_count = 0
            try:
                for case in scraper.backfill(courts, (start_date, end_date)):
                    case_url = case.get("case_url")
                    if not case_url:
                        logger.warning("Case without case_url: %s", case)
                        continue

                    # Extract court_id from case data if available
                    court_id = case.get("court_code") or "unknown_court"

                    # Fetch and save the case page
                    try:
                        case_response = case_session.get(case_url, timeout=60)
                        save_docket_response(
                            case_response,
                            scraper_class_name,
                            court_id,
                            case_meta=dict(case),
                        )
                        case_count += 1

                        if case_count % 100 == 0:
                            logger.info("Processed %d cases", case_count)

                    except requests.RequestException as e:
                        logger.error(
                            "Failed to fetch case URL %s: %s", case_url, e
                        )

            finally:
                case_session.close()

            logger.info(
                "Backfill complete. Processed %d cases total.", case_count
            )

        finally:
            request_manager.close()

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
