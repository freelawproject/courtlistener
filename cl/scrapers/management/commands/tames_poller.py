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
from datetime import date, datetime, timedelta
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from juriscraper.state.texas import (
    TexasCourtOfCriminalAppealsScraper,
    TexasSupremeCourtScraper,
)
from juriscraper.state.texas.court_of_appeals import (
    TexasCourtOfAppealsScraper,
)
from juriscraper.state.texas.tames import TAMESScraper
from lxml import etree

from cl.corpus_importer.tasks import MergeResult, merge_texas_docket
from cl.lib.command_utils import logger
from cl.lib.exceptions import SubscriptionFailure
from cl.lib.redis_utils import get_redis_interface
from cl.scrapers.management.commands.back_scrape_dockets import (
    RateLimitedRequestManager,
    save_docket_response,
)
from cl.scrapers.models import AccountSubscription, Scraper

REDIS_KEY = "tames:polling:last_seen_cases"
REDIS_TTL = 60 * 60 * 24 * 28  # 4 weeks
FRESHNESS_CHECK_COUNT = 25
SCRAPER_CLASS_NAME = "TAMESScraper"

CASEMAIL_LOGIN_URL = "https://casemail.txcourts.gov/login.aspx"
CASEMAIL_CASE_ADD_URL = "https://casemail.txcourts.gov/CaseAdd.aspx"
CASEMAIL_MESSAGE_XPATH = (
    "//span[@id='ctl00_ctl00_BaseContentPlaceHolder1"
    "_ContentPlaceHolder1_lblMessage']/font"
)
TAMES_PENDING_SUBSCRIPTIONS_KEY = "tames:pending_subscriptions"

shutdown_requested = False


def _login_tames(
    session: requests.Session, tames_user: dict[str, str]
) -> None:
    """Log in to the TAMES CaseMail system.

    Fetches the login page, extracts ASP.NET hidden fields, and POSTs
    credentials.

    :param session: A requests session to authenticate.
    :param tames_user: Dict with "username" and "password" keys.
    :raises SubscriptionFailure: If login fails.
    :raises requests.RequestException: If the login request fails.
    """
    resp = session.get(CASEMAIL_LOGIN_URL, timeout=30)
    resp.raise_for_status()

    tree = etree.fromstring(resp.text, etree.HTMLParser())
    payload: dict[str, str] = {}
    for input_tag in tree.xpath("//input[@type='hidden']"):
        if name := input_tag.get("name"):
            payload[name] = input_tag.get("value", "")

    payload.update(
        {
            "ctl00$ctl00$BaseContentPlaceHolder1$ContentPlaceHolder1$txtUserName": tames_user[
                "username"
            ],
            "ctl00$ctl00$BaseContentPlaceHolder1$ContentPlaceHolder1$txtPassword": tames_user[
                "password"
            ],
            "ctl00$ctl00$BaseContentPlaceHolder1$ContentPlaceHolder1$cmdLogon": "Logon",
        }
    )

    resp = session.post(CASEMAIL_LOGIN_URL, data=payload, timeout=30)
    resp.raise_for_status()
    if (
        "ctl00_ctl00_BaseContentPlaceHolder1_ContentPlaceHolder1_gvCaseWatch"
        not in resp.text
    ):
        raise SubscriptionFailure("Login failed.")


def subscribe_pending_cases(
    redis, tames_user: dict[str, str]
) -> None:
    """Subscribe to all pending TAMES cases in the Redis SET.

    Logs in once, iterates through every member of the pending-subscriptions
    SET, attempts to subscribe, and removes successful cases. Failed cases
    remain in the SET for the next poll cycle.

    :param redis: Redis interface (CACHE).
    :param tames_user: Dict with "username", "password", "email" keys.
    """
    pending_members = redis.smembers(TAMES_PENDING_SUBSCRIPTIONS_KEY)
    if not pending_members:
        return

    logger.info(
        "Attempting subscription for %d pending cases.",
        len(pending_members),
    )

    session = requests.Session()
    session.headers.update({"User-Agent": "Free Law Project"})

    try:
        _login_tames(session, tames_user)
    except (requests.RequestException, SubscriptionFailure):
        logger.warning(
            "TAMES CaseMail login failed. %d cases remain pending.",
            len(pending_members),
        )
        return

    html_parser = etree.HTMLParser()
    succeeded: list[str] = []
    successful_dates: set[date] = set()

    for member in pending_members:
        case = json.loads(member)
        court = case["court"]
        case_number = case["case"]
        try:
            resp = session.get(
                CASEMAIL_CASE_ADD_URL,
                params={
                    "coa": court,
                    "FullCaseNumber": case_number,
                    "cID": court,
                },
                timeout=30,
            )
            resp.raise_for_status()
            tree = etree.fromstring(resp.text, html_parser)
            messages = tree.xpath(CASEMAIL_MESSAGE_XPATH)
            message = "No message found"
            if isinstance(messages, list) and messages:
                first_msg = messages[0]
                if isinstance(first_msg, etree._Element):
                    message = first_msg.text or message
            logger.info(
                "TAMES subscription for %s/%s: %s",
                court,
                case_number,
                message,
            )
            date_filed = datetime.strptime(
                case["date_filed"], "%m/%d/%Y"
            ).date()
            successful_dates.add(date_filed)
            succeeded.append(member)
        except Exception:
            logger.exception(
                "Failed to subscribe to TAMES case %s/%s",
                court,
                case_number,
            )

    if succeeded:
        redis.srem(TAMES_PENDING_SUBSCRIPTIONS_KEY, *succeeded)

    if successful_dates:
        subscription_tracker, _created = (
            AccountSubscription.objects.get_or_create(
                scraper=Scraper.TAMES,
                user_name=tames_user["username"],
                defaults={
                    "email": tames_user["email"],
                    "first_subscription": min(successful_dates),
                    "last_subscription": max(successful_dates),
                },
            )
        )
        subscription_tracker.include_subscriptions(successful_dates)

    still_pending = len(pending_members) - len(succeeded)
    logger.info(
        "Subscription complete: %d succeeded, %d still pending.",
        len(succeeded),
        still_pending,
    )


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

        if not settings.TAMES_USER:  # type: ignore[misc]
            raise CommandError("TAMES_USER must be set.")
        tames_user: dict[str, str] = json.loads(settings.TAMES_USER)

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
            self._poll_cycle(options, redis, courts, tames_user)

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
        tames_user: dict[str, str],
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
                subscribe_pending_cases(redis, tames_user)
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

            new_case_count = 0
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
                        redis.sadd(
                            TAMES_PENDING_SUBSCRIPTIONS_KEY,
                            json.dumps(
                                {
                                    "court": court_code,
                                    "case": case.get(
                                        "case_number", ""
                                    ),
                                    "date_filed": case.get(
                                        "date_filed", ""
                                    ),
                                },
                                sort_keys=True,
                            ),
                        )
                        new_case_count += 1
                case_count += 1

                if case_count % 100 == 0:
                    logger.info("Processed %d cases", case_count)

                if backfill_count is not None and case_count >= backfill_count:
                    break

            logger.info(
                "Backfill complete. Processed %d cases (%d new).",
                case_count,
                new_case_count,
            )

        subscribe_pending_cases(redis, tames_user)

        # -- Update Redis ------------------------------------------------------
        redis.set(
            REDIS_KEY,
            json.dumps(list(fresh_urls)),
            ex=REDIS_TTL,
        )
        logger.info(
            "Updated Redis key %s with %d URLs.", REDIS_KEY, len(fresh_urls)
        )
