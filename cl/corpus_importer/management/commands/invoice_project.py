import os

from celery.canvas import chain
from django.conf import settings
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import make_attachment_pq_object, \
    get_attachment_page_by_rd
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query_from_query_string
from cl.recap.tasks import process_recap_attachment

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'hDResWFzUBzlAOKP'


def get_attachment_pages(options):
    """Find docket entries that look like invoices and get their attachment
    pages.
    """
    page_size = 100
    query_string = 'q=document_type%3A"PACER+Document"+description%3Ainvoice&type=r&order_by=score+desc'
    main_query = build_main_query_from_query_string(
        query_string,
        {'rows': page_size, 'fl': ['id', 'docket_id']},
        {'group': False, 'facet': False},
    )
    si = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode='r')
    results = si.query().add_extra(**main_query)

    q = options['queue']
    recap_user = User.objects.get(username='recap')
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    paginator = Paginator(results, page_size)
    i = 0
    for page_number in range(1, paginator.num_pages + 1):
        paged_results = paginator.page(page_number)
        for result in paged_results.object_list:
            if i < options['offset']:
                i += 1
                continue
            if i >= options['limit'] > 0:
                break

            logger.info("Doing row %s: rd: %s, docket: %s", i, result['id'],
                        result['docket_id'])
            throttle.maybe_wait()
            chain(
                # Query the attachment page and process it
                get_attachment_page_by_rd.s(
                    result['id'], session.cookies).set(queue=q),
                # Take that in a new task and make a PQ object
                make_attachment_pq_object.s(
                    result['id'], recap_user.pk).set(queue=q),
                # And then process that using the normal machinery.
                process_recap_attachment.s(tag_name=TAG).set(queue=q),
            ).apply_async()
            i += 1
        else:
            # Inner loop exited normally (didn't "break")
            continue
        # Inner loop broke. Break outer loop too.
        break


def get_documents(options):
    """Download documents from PACER if we don't already have them."""
    pass


class Command(VerboseCommand):
    help = "Get lots of invoices and their attachment pages."

    allowed_tasks = [
        'attachment_pages',
        'documents',
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--offset',
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
                 "skip none.",
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
                 "with the offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            '--task',
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        if options['task'] == 'attachment_pages':
            get_attachment_pages(options)
        elif options['task'] == 'documents':
            get_documents(options)
