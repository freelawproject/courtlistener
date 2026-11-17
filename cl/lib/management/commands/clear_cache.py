"""Clear the default Django cache."""

from typing import Any

from django.core.cache import cache

from cl.lib.command_utils import VerboseCommand, logger


class Command(VerboseCommand):
    """Clear the default Django cache."""

    def handle(self, *args: Any, **options: Any) -> None:
        """Clear the cache."""
        super().handle(*args, **options)
        cache.clear()
        logger.info("Cleared cache")
