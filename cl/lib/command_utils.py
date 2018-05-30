import logging
import os

from django.core.management import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class VerboseCommand(BaseCommand):
    def handle(self, *args, **options):
        verbosity = options.get('verbosity')
        if verbosity == 0:
            logger.setLevel(logging.WARN)
        elif verbosity == 1:  # default
            logger.setLevel(logging.INFO)
        elif verbosity > 1:
            logger.setLevel(logging.DEBUG)


class CommandUtils(object):
    """A mixin to give some useful methods to sub classes."""

    @staticmethod
    def ensure_file_ok(file_path):
        """Check to make sure that a file path exists and is valid."""
        if not os.path.exists(file_path):
            raise CommandError("Unable to find file at %s" % file_path)
        if not os.access(file_path, os.R_OK):
            raise CommandError("Unable to read file at %s" % file_path)
