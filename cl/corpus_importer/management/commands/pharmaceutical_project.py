import argparse
import csv

from django.conf import settings

from cl.corpus_importer.tasks import save_ia_docket_to_disk
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query_from_query_string

BULK_OUTPUT_DIRECTORY = '/sata/sample-data/pharma-dockets'


def query_dockets(query_string):
    """Identify the d_pks for all the dockets that we need to export

    :param query: The query to run as a URL-encoded string (typically starts
     with 'q='). E.g. 'q=foo&type=r&order_by=dateFiled+asc&court=dcd'
    :return: a list of docket PKs to export
    """
    page_size = 50000
    main_query = build_main_query_from_query_string(
        query_string,
        {'rows': page_size, 'fl': ['docket_id']},
        {'group': False, 'facet': False},
    )
    si = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode='r')
    results = si.query().add_extra(**main_query).execute()
    logger.info("Got %s search results for query %s",
                results.result.numFound, query_string)
    assert results.result.numFound != page_size, \
        "Got %s results. Page size too small." % page_size
    d_pks = set()
    for result in results:
        d_pks.add(result['id'])
    return list(d_pks)


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
    q = options['queue']
    offset = options['offset'] # XXX
    throttle = CeleryThrottle(queue_name=q)
    f = options['file']
    reader = csv.DictReader(f)
    for row in reader:
        query_params = get_query_from_link(row['Link'])
        logger.info('Doing query: %s', query_params)
        d_pks = query_dockets(query_params)
        for i, d_pk in enumerate(d_pks):
            if i >= options['limit'] > 0:
                break
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
            '--file',
            type=argparse.FileType('r'),
            help="Where is the CSV that has the information about what to "
                 "download?",
            required=False,
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
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        query_and_export(options)
