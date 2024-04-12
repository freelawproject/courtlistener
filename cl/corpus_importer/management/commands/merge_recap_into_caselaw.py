import re
from typing import Optional

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


def fetch_start_date(court):
    """"""
    return (
        OpinionCluster.objects.filter(docket__court=court)
        .exclude(source=SOURCES.RECAP)
        .aggregate(most_recent=Max("date_filed"))["most_recent"]
    )


def identify_judge_string(description: str) -> Optional[str]:
    """"""
    pattern = r"(by) (Chief|Magistrate|District)? ?(Honorable|Judge)(.*?) on "
    n = re.search(pattern, description, re.IGNORECASE)
    if not n:
        # No judge evident in description
        return
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
        return
    return first_pass.strip(".")


def merge_recap_into_caselaw():
    """

    :return: None
    """
    for court in Court.objects.filter(jurisdiction="FD"):
        latest_date_filed = fetch_start_date(court)
        if latest_date_filed is None:
            # Just in case its a historical court
            continue
        # lets iterate over every docket from recap
        for docket in Docket.objects.filter(court=court, source=9).iterator():
            rds = RECAPDocument.objects.filter(
                docket_entry__docket=docket,
                is_available=True,
                is_free_on_pacer=True,
            )
            if rds.count() == 0:
                # If no free on pacer docuemnts - skip because we dont want to
                # even bother this round
                continue

            for rd in rds:
                if rd.docket_entry.date_filed <= latest_date_filed:
                    # Exclude documents entered before our date
                    # Its not ideal but the queries were killing my system and this
                    # works relatively well enough
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
                    # Do some simple parsing excluding transfered cases and rulings to avoid some mistakes
                    continue

                judge_str = identify_judge_string(rd.docket_entry.description)

                cluster = OpinionCluster(
                    judges=judge_str,
                    date_filed=rd.docket_entry.date_filed,
                    date_filed_is_approximate=False,
                    case_name_full=docket.case_name_full,
                    case_name=docket.case_name,
                    case_name_short=docket.case_name_short,
                    source=SOURCES.RECAP,
                    precedential_status=PRECEDENTIAL_STATUS.UNKNOWN,
                    blocked=False,
                    date_blocked=None,
                    docket=docket,
                )
                opinion = Opinion(
                    cluster=cluster,
                    type=Opinion.TRIAL_COURT,
                    author=judge_str,
                    page_count=rd.page_count,
                )
                opinion.save()
                cluster.save()


class Command(VerboseCommand):
    """ """

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        merge_recap_into_caselaw()
