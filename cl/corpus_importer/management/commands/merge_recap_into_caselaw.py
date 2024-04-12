import logging
import re

from django.db import transaction
from django.db.models import Max
from eyecite.find import get_citations

from cl.lib.command_utils import VerboseCommand
from cl.recap.models import RECAPDocument
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SOURCES,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
)


def fetch_start_date(court: Court) -> str:
    """Fetch start date

    :param court:
    :return:
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
        # No judge evident in description
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


def merge_recap_into_caselaw(
    first_docket_id: int, min_date_str: str, max_date_str: str
) -> None:
    """Merge Recap documents into Case Law DB

    :return: None
    """
    if first_docket_id != None:
        # find court to begin with - and wait til you get to that court to begin
        starting_court = Docket.objects.get(pk=first_docket_id).court
        start = False
    else:
        start = True

    for court in Court.objects.filter(jurisdiction="FD"):
        if start == False:
            if court.id != starting_court.id:
                continue

        latest_date_filed = fetch_start_date(court)
        if latest_date_filed is None:
            # Just in case its a historical court
            logging.warning(f"Skipping court: {court.id}")
            continue

        logging.warning(f"Starting court: {court.id}")
        # lets iterate over every docket from recap
        for docket in Docket.objects.filter(court=court, source=9).iterator():
            if start == False:
                if docket.id != first_docket_id:
                    continue
                else:
                    start = True
            rds = RECAPDocument.objects.filter(
                docket_entry__docket=docket,
                is_available=True,
                is_free_on_pacer=True,
            )
            if rds.count() == 0:
                # If no free on pacer documents - skip because we dont want to
                # even bother this round
                continue

            for rd in rds:
                if rd.docket_entry.date_filed <= latest_date_filed:
                    # Exclude documents entered before our date
                    # Its not ideal but the queries were killing my system and this
                    # works relatively well enough
                    continue
                if Opinion.objects.filter(sha1=rd.sha1).exists():
                    logging.warning(
                        f"Skipping document: {rd} as previously processed"
                    )
                    continue
                # Lets test our document for citations - now that we know its an opinion
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

                judge_str = identify_judge_string(rd.docket_entry.description)
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
                            precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
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
                        cluster.save()
                        opinion.save()
                        logging.warning(
                            f"New op {opinion.id}, cluster: {cluster.id} for docket {docket.id}"
                        )
                except ValueError as e:
                    logging.warning(f"Error saving transaction {str(e)}")


class Command(VerboseCommand):
    """ """

    def __init__(self, stdout=None, stderr=None, no_color=False):
        super(Command, self).__init__(stdout=None, stderr=None, no_color=False)

    def add_arguments(self, parser):
        parser.add_argument(
            "--docket",
            help=("Docket to start after"),
            default=None,
            required=False,
            type=int,
        )
        parser.add_argument(
            "--min-date",
            help=("Min Date range to process - yyyy-mm-dd format"),
            default=None,
            required=False,
            type=str,
        )
        parser.add_argument(
            "--max-date",
            help=("Max Date to Process if not current - yyyy-mm-dd"),
            default=None,
            required=False,
            type=str,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        first_docket_id = options["docket"]

        # to implement for future back scraping
        min_date_str = options["min_date"]
        max_date_str = options["max_date"]

        merge_recap_into_caselaw(
            first_docket_id=first_docket_id,
            min_date_str=min_date_str,
            max_date_str=max_date_str,
        )
