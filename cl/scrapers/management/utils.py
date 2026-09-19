import re
from abc import ABC
from collections.abc import Mapping
from datetime import date, datetime
from typing import ClassVar

from django.core.management import CommandError
from django.core.management.base import BaseCommand, CommandParser
from redis import Redis

from cl.lib.redis_utils import get_redis_interface


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


class StateBackScrapeCommand(ABC, BaseCommand):
    checkpoint_tracker: ClassVar[ScraperCheckpointTracker]
    date_range_required: ClassVar[bool] = True

    def add_arguments(self, parser: CommandParser):
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
            help="Auto resume the command using the last end-date stored in redis. ",
        )
