from django.core.cache import cache

from cl.lib.command_utils import VerboseCommand, logger


class Command(VerboseCommand):
    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        cache.clear()
        logger.info('Cleared cache')
