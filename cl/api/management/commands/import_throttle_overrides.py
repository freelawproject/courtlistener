import sys
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError

from cl.api.models import APIThrottle, ThrottleType
from cl.lib.command_utils import VerboseCommand, logger

# Rates that indicate blocking (workarounds used before we had proper blocking)
BLOCKED_RATES = {"1/hour", "10/hour"}


class Command(VerboseCommand):
    """Import throttle overrides from settings into the database.

    This command reads the OVERRIDE_THROTTLE_RATES and
    CITATION_LOOKUP_OVERRIDE_THROTTLE_RATES settings and creates
    APIThrottle records in the database.

    Users with rates of "1/hour" or "10/hour" are treated as blocked,
    since these rates were historically used as workarounds for blocking.
    """

    help = (
        "Import throttle rate overrides from settings into the APIThrottle "
        "model. Should be run once during migration to the new system."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would be imported without making changes.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)
        self.options = options
        self.dry_run = options["dry_run"]

        if self.dry_run:
            sys.stdout.write(
                "**********************************\n"
                "* DRY RUN - NO CHANGES MADE      *\n"
                "**********************************\n\n"
            )

        api_overrides = settings.REST_FRAMEWORK.get(  # type: ignore[misc]
            "OVERRIDE_THROTTLE_RATES", {}
        )
        citation_overrides = settings.REST_FRAMEWORK.get(  # type: ignore[misc]
            "CITATION_LOOKUP_OVERRIDE_THROTTLE_RATES", {}
        )

        api_stats = self._import_overrides(
            api_overrides, ThrottleType.API, "API"
        )
        citation_stats = self._import_overrides(
            citation_overrides, ThrottleType.CITATION_LOOKUP, "Citation Lookup"
        )

        self._print_summary(api_stats, citation_stats)

    def _import_overrides(
        self,
        overrides: dict[str, str],
        throttle_type: int,
        type_name: str,
    ) -> dict[str, int]:
        """Import a set of throttle overrides.

        :param overrides: Dict mapping username to rate string.
        :param throttle_type: The ThrottleType value.
        :param type_name: Human-readable name for logging.
        :return: Stats dict with counts of created, blocked, skipped, etc.
        """
        stats = {
            "total": len(overrides),
            "created": 0,
            "blocked": 0,
            "rate_limited": 0,
            "user_not_found": 0,
            "already_exists": 0,
            "errors": 0,
        }

        logger.info(f"Processing {len(overrides)} {type_name} overrides...")

        for username, rate in overrides.items():
            result = self._process_override(username, rate, throttle_type)
            stats[result] += 1

        return stats

    def _process_override(
        self,
        username: str,
        rate: str,
        throttle_type: int,
    ) -> str:
        """Process a single throttle override.

        :param username: The username to create the override for.
        :param rate: The rate string (e.g., "1000/hour").
        :param throttle_type: The ThrottleType value.
        :return: Result category string for stats tracking.
        """
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            if self.dry_run:
                sys.stdout.write(f"  SKIP: User '{username}' not found\n")
            else:
                logger.warning(f"User '{username}' not found, skipping")
            return "user_not_found"

        is_blocked = rate in BLOCKED_RATES

        if self.dry_run:
            action = "BLOCK" if is_blocked else f"RATE={rate}"
            sys.stdout.write(
                f"  {action}: {username} ({ThrottleType(throttle_type).label})\n"
            )
            return "blocked" if is_blocked else "rate_limited"

        try:
            if is_blocked:
                APIThrottle.objects.create(
                    user=user,
                    throttle_type=throttle_type,
                    blocked=True,
                    rate="",
                    notes=f"Imported from settings. Original rate: {rate}",
                )
                return "blocked"
            else:
                APIThrottle.objects.create(
                    user=user,
                    throttle_type=throttle_type,
                    blocked=False,
                    rate=rate,
                    notes="Imported from settings.",
                )
                return "rate_limited"

        except IntegrityError:
            logger.warning(
                f"APIThrottle already exists for user '{username}' "
                f"and throttle_type {throttle_type}"
            )
            return "already_exists"
        except Exception as e:
            logger.error(f"Error creating APIThrottle for '{username}': {e}")
            return "errors"

    def _print_summary(
        self,
        api_stats: dict[str, int],
        citation_stats: dict[str, int],
    ) -> None:
        """Print a summary of the import operation.

        :param api_stats: Stats dict for API overrides.
        :param citation_stats: Stats dict for Citation overrides.
        """
        sys.stdout.write("\n" + "=" * 60 + "\n")
        sys.stdout.write("IMPORT SUMMARY\n")
        sys.stdout.write("=" * 60 + "\n\n")

        for name, stats in [
            ("API Throttles", api_stats),
            ("Citation Lookup Throttles", citation_stats),
        ]:
            sys.stdout.write(f"{name}:\n")
            sys.stdout.write(f"  Total in settings:    {stats['total']}\n")
            if self.dry_run:
                sys.stdout.write(
                    f"  Would block:          {stats['blocked']}\n"
                )
                sys.stdout.write(
                    f"  Would rate limit:     {stats['rate_limited']}\n"
                )
            else:
                created = stats["blocked"] + stats["rate_limited"]
                sys.stdout.write(
                    f"  Created (blocked):    {stats['blocked']}\n"
                )
                sys.stdout.write(
                    f"  Created (rate limit): {stats['rate_limited']}\n"
                )
                sys.stdout.write(
                    f"  Already exists:       {stats['already_exists']}\n"
                )
            sys.stdout.write(
                f"  User not found:       {stats['user_not_found']}\n"
            )
            if stats["errors"]:
                sys.stdout.write(
                    f"  Errors:               {stats['errors']}\n"
                )
            sys.stdout.write("\n")
