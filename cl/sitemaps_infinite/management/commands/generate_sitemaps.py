"""Generate the next chunk of pre-generated sitemap URLs."""

from django.core.management.base import CommandParser

from cl.lib.command_utils import VerboseCommand, logger
from cl.sitemaps_infinite.sitemap_generator import (
    generate_urls_chunk,
    reset_sitemaps_cursor,
)


class Command(VerboseCommand):
    """Generate the next chunk of sitemap URLs, continuing from the saved cursor."""

    help = """The command starts or continues the sitemap urls generation.
    The place where the generation was stopped last time is saved into the redis cache and then loaded when the command starts"""

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the force-regenerate flag."""
        parser.add_argument(
            "--force-regenerate",
            action="store_true",
            required=False,
            help="Force all cached pages to be regenerated",
        )

    def handle(self, *args, **options):
        """Generate a chunk of URLs, first resetting the cursor if forced."""
        if options["force_regenerate"]:
            reset_sitemaps_cursor()
            logger.info("Sitemaps cursor was reset successfully.")

        generate_urls_chunk(options["force_regenerate"])
