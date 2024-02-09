import argparse
import csv

from cl.corpus_importer.bulk_utils import docket_pks_for_query
from cl.corpus_importer.tasks import save_ia_docket_to_disk
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger

BULK_OUTPUT_DIRECTORY = "/sata/sample-data/pharma-dockets"


def get_query_from_link(url):
    """Convert a full link to just a query

    :param url: The URL to parse (cl.com/?q=foo)
    :return: The get param string
    """
    url, params = url.split("?", 1)
    return params


def query_and_export(options):
    """Iterate over the query list, place the queries, and then export results

    Our client has provided us with a spreadsheet chalk-full of queries. Our
    task is to take those queries, run them, identify the matched dockets, then
    serialize those dockets to disk as the deliverable for the client.

    :param options: The argparse options
    :return None
    """
    # Get all PKs up front b/c there will be overlap between the queries
    f = options["file"]
    reader = csv.DictReader(f)
    d_pks = set()
    for i, row in enumerate(reader):
        if i < options["query_offset"]:
            continue
        if i >= options["query_limit"] > 0:
            break
        query_params = get_query_from_link(row["Link"])
        logger.info("Doing query: %s", query_params)
        d_pks.update(list(docket_pks_for_query(query_params)))

    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    for i, d_pk in enumerate(d_pks):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break
        if i % 1000 == 0:
            logger.info("Doing item %s with pk %s", i, d_pk)
        throttle.maybe_wait()
        save_ia_docket_to_disk.apply_async(
            args=(d_pk, options["output_directory"]), queue=q
        )


class Command(VerboseCommand):
    help = "Look up dockets from a spreadsheet for a client and export them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
            "skip none.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
            "with the offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            "--query-offset",
            type=int,
            default=0,
            help="The number of queries to skip before beginning. Default is "
            "to skip none.",
        )
        parser.add_argument(
            "--query-limit",
            type=int,
            default=0,
            help="After doing this number of queries, do no more and proceed "
            "to generating dockets. This number is not additive with the "
            "offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            "--file",
            type=argparse.FileType("r"),
            help="Where is the CSV that has the information about what to "
            "download?",
            required=True,
        )
        parser.add_argument(
            "--output-directory",
            type=str,
            help="Where the bulk data will be output to. Note that if Docker "
            "is used for Celery, this is a directory *inside* docker.",
            default=BULK_OUTPUT_DIRECTORY,
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        query_and_export(options)
