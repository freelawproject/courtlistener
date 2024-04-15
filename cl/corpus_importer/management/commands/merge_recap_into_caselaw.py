import logging
import re
from typing import Optional

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models import Max, Q
from eyecite.find import get_citations

from cl.lib.command_utils import VerboseCommand
from cl.people_db.lookup_utils import lookup_judge_by_full_name
from cl.people_db.models import Person
from cl.recap.models import RECAPDocument
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SOURCES,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
)


def disable_logging():
    """"""
    logger = logging.getLogger("django.db.backends")
    logger.setLevel(logging.WARNING)


def fetch_start_date(court: Court) -> str:
    """Fetch start date of opinions for a court

    This function fetches the last date a federal district court received an
    opinion (most likely from the Harvard import).

    :param court: Court object
    :return: the most recent date for this court
    """
    return (
        OpinionCluster.objects.filter(docket__court=court)
        .exclude(source=SOURCES.RECAP)
        .aggregate(most_recent=Max("date_filed"))["most_recent"]
    )


def identify_judge_string(description: str) -> str:
    """Find judge in description

    :param description: Docket entry description
    :return: Judge string if found otherwise an empty string
    """
    pattern = r"(by) (Chief|Magistrate|District)? ?(Honorable|Judge)(.*?) on "
    n = re.search(pattern, description, re.IGNORECASE)
    if not n:
        # No judge found easily in description
        return ""
    first_pass = n.group(4)
    delimiters = [
        "(",
        "Granting",
        "Denying",
        "denying",
        "granting",
        ";",
        " for ",
        "Associated Cases",
        "Habeas Answer",
    ]
    for delimiter in delimiters:
        first_pass = first_pass.split(delimiter)[0].strip()
    if len(first_pass) < 3 or len(first_pass) > 60:
        # Likely a failed parse of the judge so dont add it
        return ""
    return first_pass.strip(".")


def find_status(docket_entry: str) -> str:
    """Find precedential status

    :param docket_entry: Docket entry text
    :return: Published or unknown
    """
    if "(Order Published)" in docket_entry:
        return PRECEDENTIAL_STATUS.PUBLISHED
    else:
        return PRECEDENTIAL_STATUS.UNKNOWN


def lookup_judge_from_entry(
    judge_str: str, docket: Docket
) -> Optional[Person]:
    """Find Judge object in DB if available

    :param rd: The RecapDocument object
    :param docket: The associated Docket
    :return: The Judge in the DB if any
    """
    author = async_to_sync(lookup_judge_by_full_name)(
        judge_str, docket.court.id, None, require_living_judge=False
    )
    if author:
        return author
    elif docket.assigned_to.name_last in judge_str:
        # Assume that if they found just has the same last name - its the
        # current ID'd judge.
        return docket.assigned_to
    return None


def merge_recap_into_caselaw(skip_until: int) -> None:
    """Merge Recap documents into Case Law DB

    :param skip_until: Docket ID to skip until if available
    :return: None
    """
    skip_until_position = None
    court_query = Court.objects.filter(
        Q(jurisdiction=Court.FEDERAL_DISTRICT) & ~Q(id="dcd"), in_use=True
    ).order_by("position")

    if skip_until:
        # Filter our previously done courts
        skip_until_position = Docket.objects.get(pk=skip_until).court.position
        court_query.filter(position__gte=skip_until_position)

    # Iterate over each federal district court, excluding DCD
    for court in court_query:
        if (latest_date_filed := fetch_start_date(court)) is None:
            continue
        logging.info(f"Starting court: {court.id}")

        docket_query = Docket.objects.filter(
            court=court,
            source__in=[
                Docket.RECAP,
                Docket.RECAP_AND_IDB,
                Docket.RECAP_AND_SCRAPER,
            ],
        ).order_by("id")

        if skip_until and court.position == skip_until_position:
            # This skips the dockets already processed on our first court
            # if it contains skip until
            docket_query = docket_query.filter(id__gte=skip_until)

        for docket in docket_query.iterator():
            if "cr" in docket.docket_number:
                # Exclude criminal cases until we reprocess them
                continue

            rds = RECAPDocument.objects.filter(
                docket_entry__docket=docket,
                is_available=True,
                is_free_on_pacer=True,
                docket_entry__date_filed__gt=latest_date_filed,
            )

            for rd in rds:
                if Opinion.objects.filter(sha1=rd.sha1).exists():
                    logging.warning(
                        f"Skipping document: {rd} as previously processed"
                    )
                    continue

                # Check for citations - now that we know its an opinion
                citations = get_citations(rd.plain_text)
                if len(citations) == 0:
                    # if no citations are found simply skip it.
                    continue

                if (
                    "Transferred" in rd.docket_entry.description
                    or "TRANSFER ORDER" in rd.docket_entry.description
                ):
                    # Exclude transfers from our mergers
                    continue

                p_status = find_status(
                    docket_entry=rd.docket_entry.description
                )
                judge_str = identify_judge_string(rd.docket_entry.description)
                judge = lookup_judge_from_entry(judge_str, docket=docket)

                try:
                    with transaction.atomic():
                        cluster = OpinionCluster(
                            judges=judge_str,
                            date_filed=rd.docket_entry.date_filed,
                            date_filed_is_approximate=False,
                            case_name_full=docket.case_name_full,
                            case_name=docket.case_name,
                            case_name_short=docket.case_name_short,
                            source=SOURCES.RECAP,
                            precedential_status=p_status,
                            blocked=False,
                            date_blocked=None,
                            docket=docket,
                        )
                        opinion = Opinion(
                            cluster=cluster,
                            type=Opinion.TRIAL_COURT,
                            author_str=judge_str,
                            page_count=rd.page_count,
                            sha1=rd.sha1,
                        )
                        if judge_str is not None:
                            opinion.author = judge
                        cluster.save()
                        opinion.save()
                        logging.warning(
                            f"New Opinion: {opinion.id}, for cluster: {cluster.id} on docket: {docket.id}"
                        )
                except ValueError as e:
                    logging.warning(f"Error saving new opinion {str(e)}")


class Command(VerboseCommand):
    help = "Merge recap opinions into CaseLaw db"

    def __init__(self):
        super(Command, self).__init__(stdout=None, stderr=None, no_color=False)

    def add_arguments(self, parser):
        parser.add_argument(
            "--disable-logging",
            help="Flag to disable debug logging",
            action="store_true",
        )
        parser.add_argument(
            "--skip-until",
            help=("Docket number to skip until"),
            default=None,
            required=False,
            type=int,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        skip_until = options["skip_until"]
        if options["disable_logging"]:
            disable_logging()
        merge_recap_into_caselaw(skip_until=skip_until)
