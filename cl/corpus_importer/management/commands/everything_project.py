import os

from celery.canvas import chain
from django.conf import settings

from cl.corpus_importer.tasks import (
    filter_docket_by_tags,
    get_docket_by_pacer_case_id,
    get_pacer_case_id_and_title,
    make_fjc_idb_lookup_params,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer_session import ProxyPacerSession, SessionData
from cl.recap.constants import (
    CIVIL_RIGHTS_ACCOMMODATIONS,
    CIVIL_RIGHTS_ADA_EMPLOYMENT,
    CIVIL_RIGHTS_ADA_OTHER,
    CIVIL_RIGHTS_JOBS,
    CIVIL_RIGHTS_OTHER,
    CIVIL_RIGHTS_VOTING,
    CIVIL_RIGHTS_WELFARE,
    CV_2017,
    CV_2020,
    PATENT,
    PRISONER_CIVIL_RIGHTS,
    PRISONER_PETITIONS_HABEAS_CORPUS,
    PRISONER_PETITIONS_MANDAMUS_AND_OTHER,
    PRISONER_PETITIONS_VACATE_SENTENCE,
    PRISONER_PRISON_CONDITION,
    SOCIAL_SECURITY,
)
from cl.recap.models import FjcIntegratedDatabase

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)

TAG = "xITWtdtYjRbPeHQMftyS"
TAG_SAMPLE = "QAKfjXAcxfjINeFsbtAI"

NOS_EXCLUSIONS = [
    CIVIL_RIGHTS_OTHER,
    CIVIL_RIGHTS_VOTING,
    CIVIL_RIGHTS_JOBS,
    CIVIL_RIGHTS_ACCOMMODATIONS,
    CIVIL_RIGHTS_WELFARE,
    CIVIL_RIGHTS_ADA_EMPLOYMENT,
    CIVIL_RIGHTS_ADA_OTHER,
    PRISONER_PETITIONS_VACATE_SENTENCE,
    PRISONER_PETITIONS_HABEAS_CORPUS,
    PRISONER_PETITIONS_MANDAMUS_AND_OTHER,
    PRISONER_CIVIL_RIGHTS,
    PRISONER_PRISON_CONDITION,
    PATENT,
    SOCIAL_SECURITY,
]


def get_fjc_rows():
    items = FjcIntegratedDatabase.objects.exclude(
        nature_of_suit__in=NOS_EXCLUSIONS,
    ).filter(
        date_filed__gte="2014-01-01", dataset_source__in=[CV_2017, CV_2020]
    )
    return items


def get_everything_sample(options, sample_size):
    items = get_fjc_rows()
    tags = [TAG, TAG_SAMPLE]
    get_dockets(options, items, tags, sample_size)


def price_sample(options, de_upper_bound):
    items = get_fjc_rows()
    tags = [TAG, TAG_SAMPLE]
    get_dockets(
        options, items, tags, sample_size=50, doc_num_end=de_upper_bound
    )


def get_content_by_year(options, year):
    items = get_fjc_rows()
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    items = items.filter(date_filed__gte=start, date_filed__lte=end)
    tags = [TAG]
    get_dockets(options, items, tags)


def get_everything_full(options):
    items = get_fjc_rows()
    tags = [TAG]
    get_dockets(options, items, tags)


def get_dockets(options, items, tags, sample_size=0, doc_num_end=""):
    """Download dockets from PACER.

    :param options: Options provided by argparse
    :param items: Items from our FJC IDB database
    :param tags: A list of tag names to associate with the purchased content.
    :param sample_size: The number of items to get. If 0, get them all. Else,
    get only this many and do it randomly.
    :param doc_num_end: Only get docket numbers up to this value to constrain
    costs. If set to an empty string, no constraints are applied. Note that
    applying this value means no unnumbered entries will be retrieved by PACER.
    """

    if sample_size > 0:
        items = items.order_by("?")[:sample_size]

    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = ProxyPacerSession(
        username=PACER_USERNAME, password=PACER_PASSWORD
    )
    session.login()
    for i, row in enumerate(items):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break

        if i % 5000 == 0:
            # Re-authenticate just in case the auto-login mechanism isn't
            # working.
            session = ProxyPacerSession(
                username=PACER_USERNAME, password=PACER_PASSWORD
            )
            session.login()

        # All tests pass. Get the docket.
        logger.info("Doing row %s: %s", i, row)

        throttle.maybe_wait()
        params = make_fjc_idb_lookup_params(row)
        session_data = SessionData(session.cookies, session.proxy_address)
        chain(
            get_pacer_case_id_and_title.s(
                pass_through=None,
                docket_number=row.docket_number,
                court_id=row.district_id,
                session_data=session_data,
                **params,
            ).set(queue=q),
            filter_docket_by_tags.s(tags, row.district_id).set(queue=q),
            get_docket_by_pacer_case_id.s(
                court_id=row.district_id,
                session_data=session_data,
                tag_names=tags,
                **{
                    "show_parties_and_counsel": True,
                    "show_terminated_parties": True,
                    "show_list_of_member_cases": False,
                    "doc_num_end": doc_num_end,
                },
            ).set(queue=q),
        ).apply_async()


class Command(VerboseCommand):
    help = "Purchase dockets from PACER"

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
            "--task",
            type=str,
            required=True,
            help="What task are we doing at this point?",
        )

    def handle(self, *args, **options):
        logger.info(f"Using PACER username: {PACER_USERNAME}")
        if options["task"] == "everything":
            get_everything_full(options)
        elif options["task"] == "everything_sample_50":
            get_everything_sample(options, 50)
        elif options["task"] == "everything_sample_10000":
            # See email dated 2019-01-06
            get_everything_sample(options, 10000)
        elif options["task"] == "price_sample_30":
            price_sample(options, "30")
        elif options["task"] == "price_sample_40":
            price_sample(options, "40")
        elif options["task"] == "price_sample_50":
            price_sample(options, "50")
        elif options["task"] == "2018_only":
            # Goes through to 2019-09-30
            get_content_by_year(options, 2018)
        elif options["task"] == "2017_only":
            # Done and billed.
            get_content_by_year(options, 2017)
        elif options["task"] == "2016_only":
            # Done and billed.
            get_content_by_year(options, 2016)
        else:
            print(f"Unknown task: {options['task']}")
