import os

from celery.canvas import chain
from django.conf import settings
from juriscraper.pacer import PacerSession

from cl.corpus_importer.task_canvases import get_district_attachment_pages
from cl.corpus_importer.tasks import (
    filter_docket_by_tags,
    get_docket_by_pacer_case_id,
    get_pacer_case_id_and_title,
    make_fjc_idb_lookup_params,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.recap.constants import (
    AIRPLANE_PERSONAL_INJURY,
    AIRPLANE_PRODUCT_LIABILITY,
    ANTITRUST,
    APA_REVIEW_OR_APPEAL_OF_AGENCY_DECISION,
    ARBITRATION,
    ASBESTOS_PERSONAL_INJURY,
    ASSAULT_LIBEL_AND_SLANDER,
    BANKS_AND_BANKING,
    CABLE_SATELLITE_TV,
    CIVIL_RICO,
    CIVIL_RIGHTS_ACCOMMODATIONS,
    CIVIL_RIGHTS_ADA_EMPLOYMENT,
    CIVIL_RIGHTS_ADA_OTHER,
    CIVIL_RIGHTS_JOBS,
    CONSUMER_CREDIT,
    CONTRACT_FRANCHISE,
    CONTRACT_OTHER,
    CONTRACT_PRODUCT_LIABILITY,
    COPYRIGHT,
    EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT,
    ENVIRONMENTAL_MATTERS,
    FAIR_LABOR_STANDARDS_ACT_CV,
    FALSE_CLAIMS_ACT,
    FAMILY_AND_MEDICAL_LEAVE_ACT,
    FEDERAL_EMPLOYERS_LIABILITY,
    FORECLOSURE,
    FORFEITURE_AND_PENALTY_SUITS_OTHER,
    FRAUD_OTHER,
    FREEDOM_OF_INFORMATION_ACT_OF_1974,
    HEALTH_CARE_PHARM,
    INSURANCE,
    INTERSTATE_COMMERCE,
    IRS_3RD_PARTY_SUITS,
    LABOR_LITIGATION_OTHER,
    LABOR_MANAGEMENT_RELATIONS_ACT,
    LABOR_MANAGEMENT_REPORT_DISCLOSURE,
    MARINE_CONTRACT,
    MARINE_PERSONAL_INJURY,
    MARINE_PRODUCT_LIABILITY,
    MEDICAL_MALPRACTICE,
    MOTOR_VEHICLE_PERSONAL_INJURY,
    MOTOR_VEHICLE_PRODUCT_LIABILITY,
    NEGOTIABLE_INSTRUMENTS,
    PATENT,
    PERSONAL_INJURY_OTHER,
    PERSONAL_INJURY_PRODUCT_LIABILITY,
    PERSONAL_PROPERTY_DAMAGE_OTHER,
    PROPERTY_DAMAGE_PRODUCT_LIABILITY,
    RAILWAY_LABOR_ACT,
    REAL_PROPERTY_ACTIONS_OTHER,
    RENT_LEASE_EJECTMENT,
    SECURITIES_COMMODITIES_EXCHANGE,
    STATE_RE_APPORTIONMENT,
    STATUTORY_ACTIONS_OTHER,
    STOCKHOLDER_SUITS,
    TAX_SUITS,
    TORT_LAND,
    TORT_PRODUCT_LIABILITY,
    TRADEMARK,
    TRUTH_IN_LENDING,
)
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import RECAPDocument
from cl.search.tasks import add_or_update_recap_docket

PACER_USERNAME = os.environ.get("PACER_USERNAME", settings.PACER_USERNAME)
PACER_PASSWORD = os.environ.get("PACER_PASSWORD", settings.PACER_PASSWORD)

TAG_NOS_700 = "pQuGjNMncnYealSvVjwL"
TAG_SAMPLE = "KzulifmXjVaknYcKpFxz"
TAG_CAND = "fgnKcGohaYWvGCdmueCB"
TAG_CAND_SAMPLE = "HaWCdtXimxSfAgGKfJRe"


def get_nos_700_items():
    nos_codes = [
        LABOR_LITIGATION_OTHER,
        LABOR_MANAGEMENT_RELATIONS_ACT,
        LABOR_MANAGEMENT_REPORT_DISCLOSURE,
        FAIR_LABOR_STANDARDS_ACT_CV,
        RAILWAY_LABOR_ACT,
        FAMILY_AND_MEDICAL_LEAVE_ACT,
        EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT,
    ]
    items = FjcIntegratedDatabase.objects.filter(
        nature_of_suit__in=nos_codes,
        date_terminated__gt="2009-01-01",
        date_filed__gt="2009-01-01",
    )
    return items


def get_cand_items():
    # See email on 2018-12-05 for details
    nos_codes = {
        # Contract
        INSURANCE,
        MARINE_CONTRACT,
        NEGOTIABLE_INSTRUMENTS,
        STOCKHOLDER_SUITS,
        CONTRACT_OTHER,
        CONTRACT_PRODUCT_LIABILITY,
        CONTRACT_FRANCHISE,
        # Real Property
        FORECLOSURE,
        RENT_LEASE_EJECTMENT,
        TORT_LAND,
        TORT_PRODUCT_LIABILITY,
        REAL_PROPERTY_ACTIONS_OTHER,
        # Torts/Personal Injury
        AIRPLANE_PERSONAL_INJURY,
        AIRPLANE_PRODUCT_LIABILITY,
        ASSAULT_LIBEL_AND_SLANDER,
        FEDERAL_EMPLOYERS_LIABILITY,
        MARINE_PERSONAL_INJURY,
        MARINE_PRODUCT_LIABILITY,
        MOTOR_VEHICLE_PERSONAL_INJURY,
        MOTOR_VEHICLE_PRODUCT_LIABILITY,
        PERSONAL_INJURY_OTHER,
        MEDICAL_MALPRACTICE,
        PERSONAL_INJURY_PRODUCT_LIABILITY,
        HEALTH_CARE_PHARM,
        ASBESTOS_PERSONAL_INJURY,
        # Personal property
        FRAUD_OTHER,
        TRUTH_IN_LENDING,
        PERSONAL_PROPERTY_DAMAGE_OTHER,
        PROPERTY_DAMAGE_PRODUCT_LIABILITY,
        # Civil Rights
        CIVIL_RIGHTS_JOBS,
        CIVIL_RIGHTS_ACCOMMODATIONS,
        CIVIL_RIGHTS_ADA_EMPLOYMENT,
        CIVIL_RIGHTS_ADA_OTHER,
        # Forfeiture/Penalty
        FORFEITURE_AND_PENALTY_SUITS_OTHER,
        # Labor
        FAIR_LABOR_STANDARDS_ACT_CV,
        LABOR_MANAGEMENT_RELATIONS_ACT,
        RAILWAY_LABOR_ACT,
        FAMILY_AND_MEDICAL_LEAVE_ACT,
        LABOR_LITIGATION_OTHER,
        EMPLOYEE_RETIREMENT_INCOME_SECURITY_ACT,
        # Property Rights
        COPYRIGHT,
        PATENT,
        TRADEMARK,
        # Federal Tax Suits
        TAX_SUITS,
        IRS_3RD_PARTY_SUITS,
        # Other statutes
        FALSE_CLAIMS_ACT,
        STATE_RE_APPORTIONMENT,
        ANTITRUST,
        BANKS_AND_BANKING,
        INTERSTATE_COMMERCE,
        CIVIL_RICO,
        CONSUMER_CREDIT,
        CABLE_SATELLITE_TV,
        SECURITIES_COMMODITIES_EXCHANGE,
        STATUTORY_ACTIONS_OTHER,
        ENVIRONMENTAL_MATTERS,
        FREEDOM_OF_INFORMATION_ACT_OF_1974,
        ARBITRATION,
        APA_REVIEW_OR_APPEAL_OF_AGENCY_DECISION,
    }
    items = FjcIntegratedDatabase.objects.filter(
        district_id="cand",
        nature_of_suit__in=nos_codes,
        date_terminated__gt="2009-01-01",
        date_filed__gt="2009-01-01",
    )
    return items


def get_nos_700_docket_sample(options):
    sample_size = 1000
    items = get_nos_700_items()
    tags = [TAG_NOS_700, TAG_SAMPLE]
    get_dockets(options, items, tags, sample_size)


def get_nos_700_full(options):
    items = get_nos_700_items()
    tags = [TAG_NOS_700]
    get_dockets(options, items, tags)


def get_cand_docket_sample(options):
    sample_size = 654
    items = get_cand_items()
    tags = [TAG_CAND, TAG_CAND_SAMPLE]
    get_dockets(options, items, tags, sample_size)


def get_cand_full(options):
    items = get_cand_items()
    tags = [TAG_CAND]
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
        items = items.order_by("?")[:sample_size]

    q = options["queue"]
    throttle = CeleryThrottle(queue_name=q)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    for i, row in enumerate(items):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break

        if i % 5000 == 0:
            # Re-authenticate just in case the auto-login mechanism isn't
            # working.
            session = PacerSession(
                username=PACER_USERNAME, password=PACER_PASSWORD
            )
            session.login()

        # All tests pass. Get the docket.
        logger.info("Doing row %s: %s", i, row)

        throttle.maybe_wait()
        params = make_fjc_idb_lookup_params(row)
        chain(
            get_pacer_case_id_and_title.s(
                pass_through=None,
                docket_number=row.docket_number,
                court_id=row.district_id,
                cookies=session.cookies,
                **params,
            ).set(queue=q),
            filter_docket_by_tags.s(tags, row.district_id).set(queue=q),
            get_docket_by_pacer_case_id.s(
                court_id=row.district_id,
                cookies=session.cookies,
                tag_names=tags,
                **{
                    "show_parties_and_counsel": True,
                    "show_terminated_parties": True,
                    "show_list_of_member_cases": True,
                },
            ).set(queue=q),
            add_or_update_recap_docket.s().set(queue=q),
        ).apply_async()


def get_attachment_pages(options, tag):
    rd_pks = RECAPDocument.objects.filter(
        tags__name=tag, docket_entry__description__icontains="attachment"
    ).values_list("pk", flat=True)
    session = PacerSession(username=PACER_USERNAME, password=PACER_PASSWORD)
    session.login()
    get_district_attachment_pages(
        options=options, rd_pks=rd_pks, tag_names=[tag], session=session
    )


class Command(VerboseCommand):
    help = "Purchase dockets and attachment pages from PACER"

    allowed_tasks = [
        "dockets_nos_700_sample",
        "dockets_nos_700_all",
        "attachments_nos_700",
        "dockets_cand_sample",
        "dockets_cand_all",
        "attachments_cand",
    ]

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
        if options["task"] == "dockets_nos_700_sample":
            get_nos_700_docket_sample(options)
        elif options["task"] == "dockets_nos_700_all":
            get_nos_700_full(options)
        elif options["task"] == "attachments_nos_700":
            get_attachment_pages(options, TAG_NOS_700)
        elif options["task"] == "dockets_cand_sample":
            get_cand_docket_sample(options)
        elif options["task"] == "dockets_cand_all":
            get_cand_full(options)
        elif options["task"] == "attachments_cand":
            get_attachment_pages(options, TAG_CAND)
