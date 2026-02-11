from cl.celery_init import app
from cl.corpus_importer.tasks import merge_texas_docket, parse_texas_docket
from cl.lib.command_utils import CorpusImporterCommand


class Command(CorpusImporterCommand):
    help = "Import Texas dockets from S3 using an inventory CSV."

    compose_redis_key = "texas_docket_import:log"

    @staticmethod
    def parse_task() -> app.Task:
        return parse_texas_docket

    @staticmethod
    def merge_task() -> app.Task:
        return merge_texas_docket
