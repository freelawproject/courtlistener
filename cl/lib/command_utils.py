import logging
import os

from django.core.management import BaseCommand, CommandError

from cl.lib.juriscraper_utils import get_module_by_court_id

logger = logging.getLogger(__name__)


class VerboseCommand(BaseCommand):
    def handle(self, *args, **options):
        verbosity = options.get("verbosity")
        if not verbosity:
            logger.setLevel(logging.WARN)
        elif verbosity == 0:
            logger.setLevel(logging.WARN)
        elif verbosity == 1:  # default
            logger.setLevel(logging.INFO)
        elif verbosity > 1:
            logger.setLevel(logging.DEBUG)
            # This will make juriscraper's logger accept most logger calls.
            juriscraper_logger = logging.getLogger("juriscraper")
            juriscraper_logger.setLevel(logging.DEBUG)


class ScraperCommand(VerboseCommand):
    """Base class for cl.scrapers commands that use Juriscraper

    Implements the `--courts` argument to lookup for a Site object
    """

    # To be used on get_module_by_court_id
    # Defined by inheriting classes
    juriscraper_module_type = ""

    def add_arguments(self, parser):
        parser.add_argument(
            "--courts",
            dest="court_id",
            metavar="COURTID",
            type=lambda s: (
                s
                if "." in s
                else get_module_by_court_id(s, self.juriscraper_module_type)
            ),
            required=True,
            help=(
                "The court(s) to scrape and extract. One of: "
                "1. a python module or package import from the Juriscraper library, e.g."
                "'juriscraper.opinions.united_states.federal_appellate.ca1' "
                "or simply 'juriscraper.opinions' to do all opinions."
                ""
                "2. a court_id, to be used to lookup for a full module path"
                "An error will be raised if the `court_id` matches more than "
                "one module path. In that case, use the full path"
            ),
        )


class CommandUtils:
    """A mixin to give some useful methods to sub classes."""

    @staticmethod
    def ensure_file_ok(file_path):
        """Check to make sure that a file path exists and is valid."""
        if not os.path.exists(file_path):
            raise CommandError(f"Unable to find file at {file_path}")
        if not os.access(file_path, os.R_OK):
            raise CommandError(f"Unable to read file at {file_path}")
