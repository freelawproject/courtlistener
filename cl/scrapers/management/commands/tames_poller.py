"""Daemon that polls TAMES for new cases and backfills when changes detected.

Combines the daemon loop pattern from cl_scrape_opinions with the TAMES
backfill infrastructure from back_scrape_dockets. Each cycle:
1. Fetches the 25 most recent cases and compares to a Redis snapshot (first page of results)
2. If new cases are found, backfills by count or date window
3. Saves case HTML pages to S3
4. Updates the Redis snapshot and sleeps
"""

import json
import time
from datetime import date, timedelta
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError
from juriscraper.state.texas import (
    TexasCourtOfCriminalAppealsScraper,
    TexasSupremeCourtScraper,
)
from juriscraper.state.texas.court_of_appeals import (
    TexasCourtOfAppealsScraper,
)
from juriscraper.state.texas.tames import TAMESScraper

from cl.corpus_importer.tasks import MergeResult, merge_texas_docket
from cl.lib.command_utils import logger
from cl.lib.redis_utils import get_redis_interface
from cl.scrapers.management.commands.back_scrape_dockets import (
    RateLimitedRequestManager,
    save_docket_response,
)
from cl.scrapers.tasks import subscribe_to_tames_cases

REDIS_KEY = "tames:polling:last_seen_cases"
REDIS_TTL = 60 * 60 * 24 * 28  # 4 weeks
FRESHNESS_CHECK_COUNT = 25
SCRAPER_CLASS_NAME = "TAMESScraper"

shutdown_requested = False


def parse_and_merge_texas_docket(
    html_content: str, court_code: str
) -> MergeResult:
    """Parse a Texas docket HTML page and merge it into the database.

    :param html_content: The HTML content of the docket page.
    :param court_code: The TAMES court code (e.g., "cossup", "coscca",
        "coa01").
    :return: The result of the merge operation.
    """
    match court_code:
        case "cossup":
            parser = TexasSupremeCourtScraper()
        case "coscca":
            parser = TexasCourtOfCriminalAppealsScraper()
        case code if code.startswith("coa"):
            parser = TexasCourtOfAppealsScraper(court_code)
        case _:
            logger.error(
                "Unrecognized Texas court code %s. Cannot parse docket.",
                court_code,
            )
            return MergeResult.failed()

    try:
        parser._parse_text(html_content)
    except Exception:
        logger.exception(
            "Error parsing Texas docket with court code %s", court_code
        )
        return MergeResult.failed()

    return merge_texas_docket(parser.data)


class Command(BaseCommand):
    help = (
        "Continuously polls TAMES for new cases and backfills "
        "when changes are detected."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--polling-delay",
            type=int,
            default=60,
            help="Minutes to sleep between poll cycles.",
        )
        parser.add_argument(
            "--case-backfill-count",
            type=int,
            default=None,
            help="Maximum number of cases to backfill per cycle.",
        )
        parser.add_argument(
            "--case-backfill-days",
            type=int,
            default=3,
            help="Number of days to look back for backfill.",
        )
        parser.add_argument(
            "--poll-window-days",
            type=int,
            default=7,
            help=(
                "Window size for polling search query in days (default: 7)."
            ),
        )
        parser.add_argument(
            "--courts",
            default=None,
            help=(
                "Comma-separated list of TAMES court IDs to poll "
                "(e.g., texas_cossup,texas_coa01). "
                "Defaults to all TAMES courts."
            ),
        )
        parser.add_argument(
            "--search-rate",
            type=float,
            default=0.2,
            help="Maximum search requests per second (default: 0.2).",
        )
        parser.add_argument(
            "--case-rate",
            type=float,
            default=2.0,
            help="Maximum case-page requests per second (default: 2.0).",
        )
        parser.add_argument(
            "--max-backoff",
            type=int,
            default=300,
            help=(
                "Maximum seconds to wait during exponential backoff "
                "on 403 errors (default: 300)."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        global shutdown_requested

        if (
            options["case_backfill_count"] is None
            and options["case_backfill_days"] is None
        ):
            raise CommandError(
                "At least one of --case-backfill-count or "
                "--case-backfill-days must be specified."
            )

        redis = get_redis_interface("CACHE")
        courts = (
            [c.strip() for c in options["courts"].split(",")]
            if options["courts"]
            else None
        )
        polling_delay_seconds = options["polling_delay"] * 60

        logger.info(
            "TAMES poller starting. Polling every %d minutes.",
            options["polling_delay"],
        )

        while not shutdown_requested:
            self._poll_cycle(options, redis, courts)

            logger.info(
                "Sleeping %d minutes before next poll.",
                options["polling_delay"],
            )
            try:
                time.sleep(polling_delay_seconds)
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt received. Shutting down...")
                shutdown_requested = True

        logger.info("TAMES poller stopped.")

    def _poll_cycle(
        self,
        options: dict[str, Any],
        redis,
        courts: list[str] | None,
    ) -> None:
        today = date.today()
        poll_start = today - timedelta(days=options["poll_window_days"])

        cached_raw = redis.get(REDIS_KEY)
        cached_urls: set[str] = (
            set(json.loads(cached_raw)) if cached_raw else set()
        )

        with (
            RateLimitedRequestManager(
                requests_per_second=options["search_rate"],
                max_backoff_seconds=options["max_backoff"],
            ) as search_request_manager,
            RateLimitedRequestManager(
                requests_per_second=options["case_rate"],
                max_backoff_seconds=options["max_backoff"],
            ) as case_request_manager,
        ):
            scraper = TAMESScraper(request_manager=search_request_manager)
            fresh_cases = []
            for case in scraper.backfill(
                courts or scraper.COURT_IDS, (poll_start, today)
            ):
                fresh_cases.append(case)
                if len(fresh_cases) >= FRESHNESS_CHECK_COUNT:
                    break

            fresh_urls = {c["case_url"] for c in fresh_cases}

            if cached_urls and fresh_urls == cached_urls:
                logger.info("No new cases detected. Skipping backfill.")
                return

            logger.info(
                "Change detected (%d new URLs). Starting backfill.",
                len(fresh_urls - cached_urls),
            )

            # -- Backfill ------------------------------------------------------
            backfill_count = options["case_backfill_count"]
            backfill_days = options["case_backfill_days"]

            if backfill_days is not None:
                backfill_start = today - timedelta(days=backfill_days)
            else:
                # Wide range; we'll stop after backfill_count cases
                backfill_start = scraper.FIRST_RECORD_DATE

            # Re-instantiate scraper for the backfill search to get a
            # fresh form state
            backfill_scraper = TAMESScraper(
                request_manager=search_request_manager
            )

            new_cases_for_subscription: list[dict[str, str]] = []
            case_count = 0
            for case in backfill_scraper.backfill(
                courts or backfill_scraper.COURT_IDS,
                (backfill_start, today),
            ):
                if shutdown_requested:
                    break

                case_url = case.get("case_url")
                if not case_url:
                    logger.warning("Case without case_url: %s", case)
                    continue

                court_code = case.get("court_code", "")
                try:
                    case_response = case_request_manager.get(case_url)
                    save_docket_response(
                        case_response,
                        SCRAPER_CLASS_NAME,
                        dict(case),
                        court_code or "unknown_court",
                    )
                except requests.RequestException:
                    logger.exception("Failed to fetch case URL %s", case_url)
                    continue

                try:
                    result = parse_and_merge_texas_docket(
                        case_response.text, court_code
                    )
                except Exception:
                    logger.exception("Failed to merge case %s", case_url)
                else:
                    if result.create and result.pk is not None:
                        new_cases_for_subscription.append(
                            {
                                "court": court_code,
                                "case": case.get("case_number", ""),
                                "date_filed": case.get("date_filed", ""),
                            }
                        )
                case_count += 1

                if case_count % 100 == 0:
                    logger.info("Processed %d cases", case_count)

                if backfill_count is not None and case_count >= backfill_count:
                    break

            logger.info(
                "Backfill complete. Processed %d cases (%d new).",
                case_count,
                len(new_cases_for_subscription),
            )

        if new_cases_for_subscription:
            subscribe_to_tames_cases.delay(new_cases_for_subscription)
            logger.info(
                "Queued subscription for %d new cases.",
                len(new_cases_for_subscription),
            )

        # -- Update Redis ------------------------------------------------------
        redis.set(
            REDIS_KEY,
            json.dumps(list(fresh_urls)),
            ex=REDIS_TTL,
        )
        logger.info(
            "Updated Redis key %s with %d URLs.", REDIS_KEY, len(fresh_urls)
        )
