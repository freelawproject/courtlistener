import csv
import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import get_pacer_case_id_and_title, \
    get_docket_by_pacer_case_id, get_appellate_docket_by_docket_number, \
    do_case_query_by_pacer_case_id
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import CommandUtils
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

PROJECT_TAG_NAME = 'cmSyHgaaCIFnUOop'


def download_dockets(options):
    """Download dockets listed in the spreadsheet."""
    f = open(options['input_file'], 'r')
    dialect = csv.Sniffer().sniff(f.read(2048))
    f.seek(0)
    reader = csv.DictReader(f, dialect=dialect)
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q,
                              min_items=options['queue_length'])
    session = PacerSession(username=PACER_USERNAME,
                           password=PACER_PASSWORD)
    session.login()
    for i, row in enumerate(reader):
        if i < options['offset']:
            continue
        if i >= options['limit'] > 0:
            break

        throttle.maybe_wait()
        logger.info("Doing row %s: %s", i, row)

        row_tag = '%s-%s' % (PROJECT_TAG_NAME, row['id'])
        if not row['district_ct']:
            chain(
                get_appellate_docket_by_docket_number.s(
                    docket_number=row['docket_no1'],
                    court_id=row['cl_court'],
                    cookies=session.cookies,
                    tag_names=[PROJECT_TAG_NAME, row_tag],
                    # Do not get the docket entries for now. We're only
                    # interested in the date terminated. If it's an open case,
                    # we'll handle that later.
                    **{
                        'show_docket_entries': False,
                        'show_orig_docket': False,
                        'show_prior_cases': False,
                        'show_associated_cases': False,
                        'show_panel_info': True,
                        'show_party_atty_info': True,
                        'show_caption': True,
                    }
                ).set(queue=q),
                add_or_update_recap_docket.s().set(queue=q),
            ).apply_async()
        else:
            chain(
                get_pacer_case_id_and_title.s(
                    docket_number=row['docket_no1'],
                    court_id=row['cl_court'],
                    cookies=session.cookies,
                    case_name=row['name'],
                ).set(queue=q),
                do_case_query_by_pacer_case_id.s(
                    court_id=row['cl_court'],
                    cookies=session.cookies,
                    tag_names=[PROJECT_TAG_NAME, row_tag],
                ).set(queue=q),
                get_docket_by_pacer_case_id.s(
                    court_id=row['cl_court'],
                    cookies=session.cookies,
                    tag_names=[PROJECT_TAG_NAME, row_tag],
                    **{
                        # No docket entries
                        'doc_num_start': 10000,
                        'doc_num_end': 10000,
                        'show_parties_and_counsel': True,
                        'show_terminated_parties': True,
                        'show_list_of_member_cases': True,
                    }
                ).set(queue=q),
                add_or_update_recap_docket.s().set(queue=q),
            ).apply_async()

    f.close()


class Command(VerboseCommand, CommandUtils):
    help = "Download dockets and metadata for the David Adelman project"

    allowed_tasks = [
        'download_dockets',
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--queue-length',
            default=100,
            type=int,
            help="The number of items to queue up in Celery at one time. Use "
                 "a smaller value here to slow down the download. For "
                 "example, if you have 40 celery workers, any value above "
                 "that will keep all 40 going non-stop. Values below that "
                 "will only do that many tasks simultaneously.",
        )
        parser.add_argument(
            '--input-file',
            help="The CSV file containing the data to analyze.",
            required=True,
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
        self.ensure_file_ok(options['input_file'])
        download_dockets(options)
