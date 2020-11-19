import json
import re
from datetime import datetime
from glob import iglob
from typing import Optional, Dict, List, Tuple

from bs4 import BeautifulSoup as bs4
from django.db import transaction
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from reporters_db import REPORTERS

from cl.citations.find_citations import get_citations
from cl.citations.models import Citation as FoundCitation
from cl.citations.utils import map_reporter_db_cite_type
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_utils import trunc
from cl.search.models import Opinion, OpinionCluster, Docket, Citation
from cl.search.tasks import add_items_to_solr

cnt = CaseNameTweaker()


def find_cites(case_data: Dict[str, str]) -> List[FoundCitation]:
    """Extract citations from raw string.

    :param case_data: Case information from the anon 2020 db.
    :return: Citation objects found in the raw string.
    """
    found_citations = []
    cites = re.findall(
        r"\"(.*?)\"", case_data["lexis_ids_normalized"], re.DOTALL
    )
    for cite in cites:
        fc = get_citations(cite)
        if len(fc) > 0:
            found_citations.append(fc[0])
    return found_citations


def merge_or_add_opinions(
    cluster_id: int,
    html_str: str,
    data: Dict[str, Optional[str, int]],
    date_argued: datetime.date,
    date_filed: datetime.date,
    case_names: Dict[str, str],
    status: str,
    docket_number: str,
    found_citations: List[FoundCitation],
):
    """Merge opinions if applicable.

    If opinion not in system, merge or add to cluster.
    If opinion is on system came from harvard, add new opinion to cluster, else
    we merge new opinion data into scraped opinion.

    :param cluster_id: Opinion Cluster id.
    :param html_str: HTML opinion to add.
    :param data: Case data to import.
    :param date_argued: Date case was argued.
    :param date_filed: Date case was filed.
    :return: None.
    """
    does_exist = (
        Opinion.objects.filter(cluster_id=cluster_id)
        .exclude(html_anon_2020="")
        .exists()
    )
    if does_exist:
        logger.info(f"Opinion already in database at {cluster_id}")
        return

    logger.info(f"Starting merger of opinions in cluster {cluster_id}.")

    cluster = OpinionCluster.objects.get(pk=cluster_id)
    docket = cluster.docket

    # Dates are uniformly good in our dataset
    # validation and is_approx not needed

    # Merge docket information
    docket.source = docket.source + docket.ANON_2020
    docket.date_argued = date_argued or docket.date_argued
    docket.docket_number = docket_number or docket.docket_number
    docket.case_name_short = (
        case_names["case_name_short"] or docket.case_name_short
    )
    docket.case_name = case_names["case_name"] or docket.case_name
    docket.case_name_full = (
        case_names["case_name_full"] or docket.case_name_full
    )

    # Merge cluster information

    cluster.date_filed = date_filed or cluster.date_filed
    cluster.precedential_status = status or cluster.precedential_status
    cluster.attorneys = data["representation"] or cluster.attorneys
    cluster.disposition = data["summary_disposition"] or cluster.disposition
    cluster.summary = data["summary_court"] or cluster.summary
    cluster.history = data["history"] or cluster.history
    cluster.other_dates = data["date_standard"] or cluster.other_dates
    cluster.cross_reference = (
        data["history_docket_numbers"] or cluster.cross_reference
    )
    cluster.correction = data["publication_status_note"] or cluster.correction
    if data["judges"]:
        cluster.judges = (
            data["judges"].replace("{", "").replace("}", "") or cluster.judges
        )
    cluster.case_name_short = (
        case_names["case_name_short"] or cluster.case_name_short
    )
    cluster.case_name = case_names["case_name"] or cluster.case_name
    cluster.case_name_full = (
        case_names["case_name_full"] or cluster.case_name_full
    )

    docket.save()
    cluster.save()

    # Add citations to cluster if applicable
    for citation in found_citations:
        Citation.objects.get_or_create(
            volume=citation.volume,
            reporter=citation.reporter,
            page=citation.page,
            type=map_reporter_db_cite_type(
                REPORTERS[citation.canonical_reporter][0]["cite_type"]
            ),
            cluster_id=cluster.id,
        )

    # Merge with scrape or add opinion to cluster with harvard
    if OpinionCluster.objects.get(pk=cluster_id).source == "C":
        opinion = Opinion.objects.get(cluster_id=cluster_id)
        logger.info("Merge with Harvard data")
        opinion.html_anon_2020 = html_str
    else:
        op = Opinion(
            cluster_id=cluster.id,
            type=Opinion.COMBINED,
            html_anon_2020=html_str,
            extracted_by_ocr=False,
        )
        op.save()

    logger.info(f"Finished merging opinion in cluster {cluster_id}.")


def check_publication_status(found_cites: List[Citation]) -> str:
    """Identify if the opinion is published in a specific reporter.

    Check if one of the found citations matches published reporters.

    :param found_cites: List of found citations.
    :return: Opinion status.
    """
    for cite in found_cites:
        if cite.reporter == "B.T.A.":
            return "Published"
        if cite.reporter == "T.C.":
            return "Published"
        if cite.reporter == "T.C. No.":
            return "Published"
    return "Unpublished"


def attempt_cluster_lookup(citations: List[FoundCitation]) -> Optional[int]:
    """Check if the citation in our database.

    If citation in found citations in our database, return cluster ID.

    :param citations: Array of citations parsed from string.
    :return: Cluster id for citations.
    """
    for citation in citations:
        cite_exists = Citation.objects.filter(
            reporter=citation.reporter,
            page=citation.page,
            volume=citation.volume,
        ).exists()
        if cite_exists:
            citation = Citation.objects.get(
                reporter=citation.reporter,
                page=citation.page,
                volume=citation.volume,
            )
            return citation.cluster_id
    return None


def do_case_name(soup, data: Dict[str, Optional[str, int]]) -> Dict[str, str]:
    """Extract and normalize the case name

    :param soup: bs4 html object of opinion.
    :param data: The full json data dict
    :return: A dict of the case_name{short,full}, that can be put
    into the dockets and opinions.
    """
    case_name = harmonize(data["name"])
    return {
        "case_name_short": cnt.make_case_name_short(case_name),
        "case_name": case_name,
        "case_name_full": harmonize(
            soup.find("div", {"class": "fullcasename"}).decode_contents()
        ),
    }


def find_court_id(court_str: str) -> str:
    """Extract cl court id from court name

    :param court_str: The raw court name
    :return: The cl court id for associated tax court.
    """
    if court_str == "United States Board of Tax Appeals":
        return "bta"
    return "tax"


def process_dates(
    data: Dict[str, Optional[str, int]]
) -> Tuple[datetime.date, datetime.date()]:
    """Process date argued and date filed

    Dates in this dataset fall into two categories, argued and filed/decided.
    We use date standard as the key for filed and/or decided.
    :param data:
    :return:
    """
    date_argued = date_filed = None
    if data["date_argued"]:
        date_argued = datetime.strptime(data["date_argued"], "%Y-%m-%d").date()
    if data["date_standard"]:
        date_filed = datetime.strptime(
            data["date_standard"], "%Y-%m-%d"
        ).date()

    return date_argued, date_filed


def import_anon_2020_db(
    import_dir: str,
    skip_until: Optional[str],
    make_searchable: Optional[bool],
) -> None:
    """Import data from anon 2020 DB into our system.

    Iterate over thousands of directories each containing a tax case
    containing case json and a preprocessed HTML object. Check if we have
    a copy of this opinion in our system and either add the opinion to a
    case we already have or create a new docket, cluster, citations and opinion
    to our database.

    :param import_dir: Location of directory of import data.
    :param skip_until: ID for case we should begin processing, if any.
    :param make_searchable: Should we add content to SOLR.
    :return: None.
    """
    directories = iglob(f"{import_dir}/*/????-*.json")
    for dir in directories:
        logger.info(f"Importing case id: {dir.split('/')[-2]}")
        if skip_until:
            if skip_until in dir:
                skip_until = False
            continue

        # Prepare data and html
        with open(dir, "rb") as f:
            data = json.load(f)
        with open(dir.replace("json", "html"), "rb") as f:
            soup = bs4(f.read(), "html.parser")

        case_names = do_case_name(soup, data)
        court_id = find_court_id(data["court"])
        date_argued, date_filed = process_dates(data)
        docket_number = trunc(
            data["docket_number"],
            length=5000,
            ellipsis="...",
        )
        html_str = soup.find("div", {"class": "container"}).decode_contents()
        found_cites = find_cites(data)
        status = check_publication_status(found_cites)

        if found_cites is not None:
            cluster_id = attempt_cluster_lookup(found_cites)
            if cluster_id is not None:
                merge_or_add_opinions(
                    cluster_id,
                    html_str,
                    data,
                    date_argued,
                    date_filed,
                    case_names,
                    status,
                    docket_number,
                    found_cites,
                )
                continue
        with transaction.atomic():
            logger.info(
                "Creating docket for: %s", found_cites[0].base_citation()
            )

            docket = Docket.objects.create(
                **case_names,
                docket_number=docket_number,
                court_id=court_id,
                source=Docket.ANON_2020,
                ia_needs_upload=False,
                date_argued=date_argued,
            )

            logger.info("Add cluster for: %s", found_cites[0].base_citation())
            judges = data["judges"] or ""
            cluster = OpinionCluster(
                **case_names,
                precedential_status=status,
                docket_id=docket.id,
                source=docket.ANON_2020,
                date_filed=date_filed,
                attorneys=data["representation"] or "",
                disposition=data["summary_disposition"] or "",
                summary=data["summary_court"] or "",
                history=data["history"] or "",
                other_dates=data["date_standard"] or "",
                cross_reference=data["history_docket_numbers"] or "",
                correction=data["publication_status_note"] or "",
                judges=judges.replace("{", "").replace("}", "") or "",
            )
            cluster.save(index=False)

            for citation in found_cites:
                logger.info(
                    "Adding citation for: %s", citation.base_citation()
                )
                Citation.objects.get_or_create(
                    volume=citation.volume,
                    reporter=citation.reporter,
                    page=citation.page,
                    type=map_reporter_db_cite_type(
                        REPORTERS[citation.canonical_reporter][0]["cite_type"]
                    ),
                    cluster_id=cluster.id,
                )

            op = Opinion(
                cluster_id=cluster.id,
                type=Opinion.COMBINED,
                html_anon_2020=html_str,
                extracted_by_ocr=False,
            )
            op.save()

            if make_searchable:
                add_items_to_solr.delay([op.pk], "search.Opinion")
        logger.info(
            f"Finished importing cluster {cluster.id}; {found_cites[0].base_citation()}"
        )


class Command(VerboseCommand):
    help = "Import anon 2020 DB."

    def add_arguments(self, parser):

        parser.add_argument(
            "--make-searchable",
            action="store_true",
            help="Add items to solr as we create opinions. "
            "Items are not searchable unless flag is raised.",
        )
        parser.add_argument(
            "--import-dir",
            default="cl/assets/media/x-db/all_dir/",
            required=False,
            help="Path to our directory of import files.",
        )

        parser.add_argument(
            "--skip-until",
            type=str,
            help="Skip processing until we reach the path supplied"
            "at this location is encountered.",
        )

    def handle(self, *args, **options):
        skip_until = options["skip_until"]
        import_dir = options["import_dir"]
        make_searchable = options["make_searchable"]
        import_anon_2020_db(import_dir, skip_until, make_searchable)
