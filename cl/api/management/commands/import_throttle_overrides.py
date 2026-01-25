import sys
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError

from cl.api.models import APIThrottle, ThrottleType
from cl.lib.command_utils import VerboseCommand, logger

# Rates that indicate blocking (workarounds used before we had proper blocking)
BLOCKED_RATES = {"1/hour", "10/hour"}

# Stats tracking for import operations
STATS = {
    "total": 0,
    "blocked": 0,
    "rate_limited": 0,
    "user_not_found": 0,
    "already_exists": 0,
    "errors": 0,
}


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

        self._import_overrides(api_overrides, ThrottleType.API, "API")

        self._import_overrides(
            citation_overrides, ThrottleType.CITATION_LOOKUP, "Citation Lookup"
        )
        self._print_summary()

    def _import_overrides(
        self,
        overrides: dict[str, str],
        throttle_type: int,
        type_name: str,
    ) -> None:
        """Import a set of throttle overrides.

        :param overrides: Dict mapping username to rate string.
        :param throttle_type: The ThrottleType value.
        :param type_name: Human-readable name for logging.
        """
        STATS["total"] += len(overrides)
        logger.info(f"Processing {len(overrides)} {type_name} overrides...")

        for username, rate in overrides.items():
            self._process_override(username, rate, throttle_type)

    def _process_override(
        self,
        username: str,
        rate: str,
        throttle_type: int,
    ) -> None:
        """Process a single throttle override.

        :param username: The username to create the override for.
        :param rate: The rate string (e.g., "1000/hour").
        :param throttle_type: The ThrottleType value.
        """
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            if self.dry_run:
                sys.stdout.write(f"  SKIP: User '{username}' not found\n")
            else:
                logger.warning(f"User '{username}' not found, skipping")
            STATS["user_not_found"] += 1
            return

        is_blocked = rate in BLOCKED_RATES

        if self.dry_run:
            action = "BLOCK" if is_blocked else f"RATE={rate}"
            sys.stdout.write(
                f"  {action}: {username} ({ThrottleType(throttle_type).label})\n"
            )
            STATS["blocked" if is_blocked else "rate_limited"] += 1
            return

        try:
            if is_blocked:
                APIThrottle.objects.create(
                    user=user,
                    throttle_type=throttle_type,
                    blocked=True,
                    rate="",
                    notes=f"Imported from settings. Original rate: {rate}",
                )
                STATS["blocked"] += 1
            else:
                APIThrottle.objects.create(
                    user=user,
                    throttle_type=throttle_type,
                    blocked=False,
                    rate=rate,
                    notes="Imported from settings.",
                )
                STATS["rate_limited"] += 1

        except IntegrityError:
            logger.warning(
                f"APIThrottle already exists for user '{username}' "
                f"and throttle_type {throttle_type}"
            )
            STATS["already_exists"] += 1
        except Exception as e:
            logger.error(f"Error creating APIThrottle for '{username}': {e}")
            STATS["errors"] += 1

    def _print_summary(
        self
    ) -> None:
        """Print a summary of the import operation."""
        sys.stdout.write("\n" + "=" * 60 + "\n")
        sys.stdout.write("IMPORT SUMMARY\n")
        sys.stdout.write("=" * 60 + "\n\n")

        sys.stdout.write(f"  Total in settings:    {STATS['total']}\n")
        if self.dry_run:
            sys.stdout.write(
                f"  Would block:          {STATS['blocked']}\n"
            )
            sys.stdout.write(
                f"  Would rate limit:     {STATS['rate_limited']}\n"
            )
        else:
            sys.stdout.write(
                f"  Created (blocked):    {STATS['blocked']}\n"
            )
            sys.stdout.write(
                f"  Created (rate limit): {STATS['rate_limited']}\n"
            )
            sys.stdout.write(
                f"  Already exists:       {STATS['already_exists']}\n"
            )
        sys.stdout.write(
            f"  User not found:       {STATS['user_not_found']}\n"
        )
        if STATS["errors"]:
            sys.stdout.write(
                f"  Errors:               {STATS['errors']}\n"
            )
        sys.stdout.write("\n")
