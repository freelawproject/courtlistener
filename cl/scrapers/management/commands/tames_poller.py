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
from typing import Any, cast

import requests
from celery import chain
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from juriscraper.state.texas.tames import TAMESScraper
from lxml import etree

from cl.corpus_importer.tasks import (
    TAMES_PENDING_SUBSCRIPTIONS_KEY,
    texas_corpus_download_task,
    texas_ingest_docket_task,
)
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
CASEMAIL_MESSAGE_SPAN_XPATH = (
    "//span[@id='ctl00_ctl00_BaseContentPlaceHolder1"
    "_ContentPlaceHolder1_lblMessage']"
)
CASEMAIL_SUCCESS_MESSAGES = {
    "Case added successfully.",
    "Case not added because it's currently in your list.",
}
shutdown_requested = False


def verify_subscription_success(html: str) -> tuple[bool, str]:
    """Check whether a CaseMail CaseAdd response indicates success.

    Parses the response HTML and extracts the status message from the
    lblMessage span.  Both a fresh add and an idempotent "already in
    your list" response are treated as successful. Note that it is
    possible to subscribe successfully to cases that do not exist.

    :param html: Raw HTML from the CaseMail CaseAdd endpoint.
    :returns: ``(is_success, message_text)`` where *message_text* is the
        extracted message or a fallback description when no message is
        found.
    """
    tree = etree.fromstring(html, etree.HTMLParser())
    spans = cast(list[etree._Element], tree.xpath(CASEMAIL_MESSAGE_SPAN_XPATH))
    if not spans:
        return False, "No message element found"

    span = spans[0]
    # The message may be directly in the span or inside a <font> child.
    font_children = cast(list[etree._Element], span.xpath("font"))
    if font_children:
        message = font_children[0].text or ""
    else:
        message = span.text or ""
    message = message.strip()

    if not message:
        return False, "Empty message"

    return message in CASEMAIL_SUCCESS_MESSAGES, message


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
    hidden_elements = cast(
        list[etree._Element], tree.xpath("//input[@type='hidden']")
    )
    for input_tag in hidden_elements:
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


def subscribe_pending_cases(redis, tames_user: dict[str, str]) -> None:
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
            success, message = verify_subscription_success(resp.text)
            logger.info(
                "TAMES subscription for %s/%s: %s",
                court,
                case_number,
                message,
            )
            if not success:
                logger.warning(
                    "Subscription not confirmed for %s/%s: %s",
                    court,
                    case_number,
                    message,
                )
                continue
            time.sleep(1)
            successful_dates.add(
                datetime.strptime(case["date_filed"], "%m/%d/%Y").date()
            )
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
            "--case-backfill-days",
            type=int,
            default=1,
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

        if not settings.TAMES_USER:  # type: ignore[misc]
            raise CommandError("TAMES_USER must be set.")
        tames_user: dict[str, str] = json.loads(settings.TAMES_USER)  # type: ignore[misc]

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
        found_stop = False

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
            backfill_days = options["case_backfill_days"]

            backfill_start = today - timedelta(days=backfill_days)

            # Re-instantiate scraper for the backfill search to get a
            # fresh form state
            backfill_scraper = TAMESScraper(
                request_manager=search_request_manager
            )

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

                if case_url in cached_urls:
                    logger.info(
                        "Reached cached case %s. Stopping backfill.",
                        case_url,
                    )
                    found_stop = True
                    break

                court_code = case.get("court_code", "")
                try:
                    case_response = case_request_manager.get(case_url)
                    bucket, base_key = save_docket_response(
                        case_response,
                        SCRAPER_CLASS_NAME,
                        dict(case),
                        court_code or "unknown_court",
                    )
                except requests.RequestException:
                    logger.exception("Failed to fetch case URL %s", case_url)
                    continue

                subscription_data = json.dumps(
                    {
                        "court": court_code,
                        "case": case.get("case_number", ""),
                        "date_filed": case.get("date_filed", ""),
                    },
                    sort_keys=True,
                )
                chain(
                    texas_corpus_download_task.si(
                        (bucket, f"{base_key}.html"),
                        (bucket, f"{base_key}_meta.json"),
                    ),
                    texas_ingest_docket_task.s(
                        subscription_data=subscription_data,
                    ),
                ).apply_async()

                case_count += 1

                if case_count % 100 == 0:
                    logger.info("Dispatched %d cases", case_count)

            logger.info(
                "Backfill complete. Dispatched %d cases.",
                case_count,
            )
            if not found_stop:
                if cached_urls:
                    logger.error(
                        "Did not find known case when scraping. Likely gap."
                    )
                else:
                    logger.info(
                        "No cached_urls found, possible gap if this isn't the first run."
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
