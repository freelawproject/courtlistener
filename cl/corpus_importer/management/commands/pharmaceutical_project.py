import argparse
import csv

from django.conf import settings
from django.core.paginator import Paginator

from cl.corpus_importer.tasks import save_ia_docket_to_disk
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query_from_query_string

BULK_OUTPUT_DIRECTORY = '/sata/sample-data/pharma-dockets'


def query_dockets(query_string):
    """Identify the d_pks for all the dockets that we need to export

    :param query_string: The query to run as a URL-encoded string (typically starts
     with 'q='). E.g. 'q=foo&type=r&order_by=dateFiled+asc&court=dcd'
    :return: a set of docket PKs to export
    """
    main_query = build_main_query_from_query_string(
        query_string,
        {'fl': ['docket_id']},
        {'group': True, 'facet': False, 'highlight': False},
    )
    main_query['group.limit'] = 0
    main_query['sort'] = 'dateFiled asc'
    si = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode='r')
    search = si.query().add_extra(**main_query)
    page_size = 1000
    paginator = Paginator(search, page_size)
    d_pks = set()
    for page_number in paginator.page_range:
        page = paginator.page(page_number)
        for item in page:
            d_pks.add(item['groupValue'])
    logger.info("After %s pages, got back %s results.",
                len(paginator.page_range), len(d_pks))
    return d_pks


def get_query_from_link(url):
    """Convert a full link to just a query

    :param url: The URL to parse (cl.com/?q=foo)
    :return: The get param string
    """
    url, params = url.split('?', 1)
    return params


def query_and_export(options):
    """Iterate over the query list, place the queries, and then export results

    Our client has provided us with a spreadsheet chalk-full of queries. Our
    task is to take those queries, run them, identify the matched dockets, then
    serialize those dockets to disk as the deliverable for the client.

    :param options: The argparse options
    :return None
    """
    f = options['file']
    reader = csv.DictReader(f)
    d_pks = set()
    for i, row in enumerate(reader):
        if i < options['query_offset']:
            continue
        if i >= options['query_limit'] > 0:
            break
        query_params = get_query_from_link(row['Link'])
        logger.info('Doing query: %s', query_params)
        d_pks.update(query_dockets(query_params))

    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for i, d_pk in enumerate(d_pks):
        if i < options['offset']:
            continue
        if i >= options['limit'] > 0:
            break
        if i % 1000 == 0:
            logger.info("Doing item %s with pk %s", i, d_pk)
        throttle.maybe_wait()
        save_ia_docket_to_disk.apply_async(
            args=(d_pk, options['output_directory']),
            queue=q,
        )


class Command(VerboseCommand):
    help = "Look up dockets from a spreadsheet for a client and export them."

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
            '--query-offset',
            type=int,
            default=0,
            help="The number of queries to skip before beginning. Default is "
                 "to skip none.",
        )
        parser.add_argument(
            '--query-limit',
            type=int,
            default=0,
            help="After doing this number of queries, do no more and proceed "
                 "to generating dockets. This number is not additive with the "
                 "offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            '--file',
            type=argparse.FileType('r'),
            help="Where is the CSV that has the information about what to "
                 "download?",
            required=True,
        )
        parser.add_argument(
            '--output-directory',
            type=str,
            help="Where the bulk data will be output to. Note that if Docker "
                 "is used for Celery, this is a directory *inside* docker.",
            default=BULK_OUTPUT_DIRECTORY,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        query_and_export(options)
