import os

from django.conf import settings
from juriscraper.pacer.http import PacerSession

from cl.corpus_importer.tasks import get_pacer_doc_id_with_show_case_doc_url
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import RECAPDocument, Court

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)


def get_pacer_doc_ids(options):
    """Get pacer_doc_ids for any item that needs them."""
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    row_pks = RECAPDocument.objects.filter(
        pacer_doc_id=None,
    ).exclude(
        document_number=None,
    ).exclude(
        docket_entry__docket__pacer_case_id=None
    ).exclude(
        docket_entry__docket__court__jurisdiction__in=Court.BANKRUPTCY_JURISDICTIONS,
    ).order_by('pk').values_list('pk', flat=True)
    completed = 0
    for row_pk in row_pks:
        if completed >= options['count'] > 0:
            break
        if row_pk < options['start_pk'] > 0:
            continue
        throttle.maybe_wait()
        if completed % 1000 == 0:
            session = PacerSession(username=PACER_USERNAME,
                                   password=PACER_PASSWORD)
            session.login()
            logger.info("Sent %s tasks to celery so far. Latest pk: %s" %
                        (completed, row_pk))
        get_pacer_doc_id_with_show_case_doc_url.apply_async(
            args=(row_pk, session.cookies),
            queue=q,
        )
        completed += 1


class Command(VerboseCommand):
    help = "Get pacer_doc_id values for any item that's missing them."

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--count',
            type=int,
            default=0,
            help="The number of items to do. Default is to do all of them.",
        )
        parser.add_argument(
            '--start-pk',
            type=int,
            default=0,
            help="Skip any primary keys lower than this value. (Useful for "
                 "restarts.)",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        get_pacer_doc_ids(options)
