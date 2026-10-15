"""Clears expired grants and tokens from the django-oauth-toolkit tables."""

import logging
import time
from typing import Any

from oauth2_provider.models import clear_expired

from cl.lib.command_utils import VerboseCommand

logger = logging.getLogger(__name__)


class Command(VerboseCommand):
    help = "Clear expired OAuth grants and tokens."

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)
        start = time.monotonic()
        clear_expired()
        logger.info(
            "clear_expired() finished in %.1fs.", time.monotonic() - start
        )
