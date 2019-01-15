import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.tasks import filter_docket_by_tags, \
    get_docket_by_pacer_case_id, get_pacer_case_id_and_title, \
    make_fjc_idb_lookup_params
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.constants import CIVIL_RIGHTS_OTHER, CIVIL_RIGHTS_VOTING, \
    CIVIL_RIGHTS_JOBS, CIVIL_RIGHTS_ACCOMMODATIONS, CIVIL_RIGHTS_WELFARE, \
    CIVIL_RIGHTS_ADA_EMPLOYMENT, CIVIL_RIGHTS_ADA_OTHER, \
    PRISONER_PETITIONS_VACATE_SENTENCE, PRISONER_PETITIONS_HABEAS_CORPUS, \
    PRISONER_PETITIONS_MANDAMUS_AND_OTHER, PRISONER_CIVIL_RIGHTS, \
    PRISONER_PRISON_CONDITION, PATENT, SOCIAL_SECURITY, CV_2017
from cl.recap.models import FjcIntegratedDatabase
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get('PACER_USERNAME', settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get('PACER_PASSWORD', settings.PACER_PASSWORD)

TAG = 'xITWtdtYjRbPeHQMftyS'
TAG_SAMPLE = 'QAKfjXAcxfjINeFsbtAI'


def get_fjc_rows():
    nos_exclusions = [
        CIVIL_RIGHTS_OTHER, CIVIL_RIGHTS_VOTING, CIVIL_RIGHTS_JOBS,
        CIVIL_RIGHTS_ACCOMMODATIONS, CIVIL_RIGHTS_WELFARE,
        CIVIL_RIGHTS_ADA_EMPLOYMENT, CIVIL_RIGHTS_ADA_OTHER,
        PRISONER_PETITIONS_VACATE_SENTENCE, PRISONER_PETITIONS_HABEAS_CORPUS,
        PRISONER_PETITIONS_MANDAMUS_AND_OTHER, PRISONER_CIVIL_RIGHTS,
        PRISONER_PRISON_CONDITION, PATENT, SOCIAL_SECURITY
    ]
    items = FjcIntegratedDatabase.objects.exclude(
        nature_of_suit__in=nos_exclusions,
    ).filter(
        date_filed__gte='2014-01-01',
        dataset_source=CV_2017,
    )
    return items


def get_everything_sample(options):
    items = get_fjc_rows()
    tags = [TAG, TAG_SAMPLE]
    sample_size = 10000  # See email dated 2019-01-06
    get_dockets(options, items, tags, sample_size)


def get_everything_full(options):
    items = get_fjc_rows()
    tags = [TAG]
    get_dockets(options, items, tags)


def get_dockets(options, items, tags, sample_size=0):
    """Download dockets from PACER.

    :param options: Options provided by argparse
    :param items: Items from our FJC IDB database
    :param tags: A list of tag names to associate with the purchased content.
    :param sample_size: The number of items to get. If 0, get them all. Else,
    get only this many and do it randomly.
    """

    if sample_size > 0:
        items = items.order_by('?')[:sample_size]

    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    for i, row in enumerate(items):
        if i < options['offset']:
            continue
        if i >= options['limit'] > 0:
            break

        if i % 5000 == 0:
            # Re-authenticate just in case the auto-login mechanism isn't
            # working.
            session = PacerSession(username=PACER_USERNAME,
                                   password=PACER_PASSWORD)
            session.login()

        # All tests pass. Get the docket.
        logger.info("Doing row %s: %s", i, row)

        throttle.maybe_wait()
        params = make_fjc_idb_lookup_params(row)
        chain(
            get_pacer_case_id_and_title.s(
                docket_number=row.docket_number,
                court_id=row.district_id,
                cookies=session.cookies,
                **params
            ).set(queue=q),
            filter_docket_by_tags.s(tags, row.district_id).set(queue=q),
            get_docket_by_pacer_case_id.s(
                court_id=row.district_id,
                cookies=session.cookies,
                tag_names=tags,
                **{
                    'show_parties_and_counsel': True,
                    'show_terminated_parties': True,
                    'show_list_of_member_cases': True
                }
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = "Purchase dockets from PACER"

    allowed_tasks = [
        'everything',
        'everything_sample',
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
        logger.info("Using PACER username: %s" % PACER_USERNAME)
        if options['task'] == 'everything':
            get_everything_full(options)
        elif options['task'] == 'everything_sample':
            get_everything_sample(options)
