import json
import re
from datetime import datetime
from glob import iglob
from typing import Optional, Tuple, Dict, List

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


def validate_dt(date_str: str) -> Tuple[datetime.date, bool]:
    """Validate datetime string.

    Check if the date string is only year-month or year.
    If partial date string, make date string the first of the month
    and mark the date as an estimate.

    If unable to validate date return an empty string, True tuple.

    :param date_str: a date string we receive from the harvard corpus.
    :returns: Tuple of date obj or date obj estimate.
    and boolean indicating estimated date or actual date.
    """
    date_approx = False
    add_ons = ["", "-15", "-07-01"]
    for add_on in add_ons:
        try:
            date_obj = datetime.strptime(date_str + add_on, "%Y-%m-%d").date()
            break
        except ValueError:
            # Failed parsing at least once, ∴ an approximate date
            date_approx = True
    return date_obj, date_approx


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


def should_we_add_opinion(cluster_id: int) -> bool:
    """Check if we previously added this document.

    If we find the citation in our system, we check if the anon-2020 DB html
    has been added to the system previously.

    :param cluster_id: ID of any cluster opinion found.
    :return: Should we had the opinion to found cluster.
    """
    ops = Opinion.objects.filter(cluster_id=cluster_id).exclude(
        html_anon_2020=""
    )
    if len(ops) == 0:
        return True
    return False


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


def add_only_opinion(soup, cluster_id) -> None:
    """Add opinion to the cluster object.

    This is only run if we are already in the system and just need
    to add the anon 2020 db html to our cluster.

    :param soup: bs4 html object of opinion.
    :param cluster_id: Cluster ID for the opinion to save.
    :return:None.
    """
    html_str = str(soup.find("div", {"class": "container"}).decode_contents())
    op = Opinion(
        cluster_id=cluster_id,
        type=Opinion.COMBINED,
        html_anon_2020=html_str,
        extracted_by_ocr=False,
    )
    op.save()


def attempt_cluster_lookup(citations: List[FoundCitation]) -> Optional[int]:
    """Check if the citation in our database.

    If citation in found citations in our database, return cluster ID.

    :param citations: Array of citations parsed from string.
    :return: Cluster id for citations.
    """
    for citation in citations:
        cite_query = Citation.objects.filter(
            reporter=citation.reporter,
            page=citation.page,
            volume=citation.volume,
        )
        if len(cite_query) > 0:
            return cite_query[0].cluster_id
    return None


def import_x_db(
    import_dir: str, skip_until: Optional[str], make_searchable: Optional[bool]
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
        try:
            logger.info(f"Importing case at: {dir}")
            if skip_until:
                if skip_until in dir:
                    continue
                skip_until = False
            with open(dir, "rb") as f:
                data = json.load(f)

            with open(dir.replace("json", "html"), "rb") as f:
                soup = bs4(f.read(), "html.parser")
            case_name_full = str(
                soup.find("div", {"class": "fullcasename"}).decode_contents()
            )
            found_cites = find_cites(data)

            if found_cites is not None:
                cluser_id = check_if_new(found_cites)
                if cluser_id is not None:
                    add_opinion = should_we_add_opinion(cluser_id)
                    if add_opinion:
                        logger.info(f"Adding opinion to cluster {cluser_id}.")
                        add_only_opinion(soup, cluser_id)
                    else:
                        logger.info(f"Opinion in system at {cluser_id}.")
                    continue

            case_name = harmonize(data["name"])
            case_name_short = cnt.make_case_name_short(case_name)
            case_name_full = harmonize(case_name_full)
            if data["court"] == "United States Tax Court":
                court_id = "tax"
            else:
                court_id = "bta"
            with transaction.atomic():
                logger.info(
                    "Creating docket for: %s", found_cites[0].base_citation()
                )
                try:
                    date_argued, is_approximate = validate_dt(
                        data["date_argued"]
                    )
                except:
                    date_argued, is_approximate = None, None

                docket = Docket(
                    case_name=case_name,
                    case_name_short=case_name_short,
                    case_name_full=case_name_full,
                    docket_number=data["docket_number"],
                    court_id=court_id,
                    source=Docket.ANON_2020,
                    ia_needs_upload=False,
                    date_argued=date_argued,
                )
                try:
                    with transaction.atomic():
                        docket.save()
                except OperationalError as e:
                    if "exceeds maximum" in str(e):
                        docket.docket_number = (
                            "%s, See Corrections for full Docket Number"
                            % trunc(
                                data["docket_number"],
                                length=5000,
                                ellipsis="...",
                            )
                        )
                        docket.save()
                try:
                    date_filed, is_approximate = validate_dt(
                        data["date_filed"]
                    )
                except:
                    date_filed, is_approximate = validate_dt(
                        data["date_standard"]
                    )
                logger.info(
                    "Add cluster for: %s", found_cites[0].base_citation()
                )
                status = check_publication_status(found_cites)
                cluster = OpinionCluster(
                    case_name=case_name,
                    case_name_short=case_name_short,
                    case_name_full=case_name_full,
                    precedential_status=status,
                    docket_id=docket.id,
                    source=docket.ANON_2020,
                    date_filed=date_filed,
                    date_filed_is_approximate=is_approximate,
                    attorneys=data["representation"]
                    if data["representation"] is not None
                    else "",
                    disposition=data["summary_disposition"]
                    if data["summary_disposition"] is not None
                    else "",
                    summary=data["summary_court"]
                    if data["summary_court"] is not None
                    else "",
                    history=data["history"]
                    if data["history"] is not None
                    else "",
                    other_dates=data["date_standard"]
                    if data["date_standard"] is not None
                    else "",
                    cross_reference=data["history_docket_numbers"]
                    if data["history_docket_numbers"] is not None
                    else "",
                    correction=data["publication_status_note"]
                    if data["publication_status_note"] is not None
                    else "",
                    judges=data["judges"].replace("{", "").replace("}", "")
                    if data["judges"] is not None
                    else "",
                )
                cluster.save(index=False)

                for citation in found_cites:
                    logger.info(
                        "Adding citation for: %s", citation.base_citation()
                    )
                    Citation.objects.create(
                        volume=citation.volume,
                        reporter=citation.reporter,
                        page=citation.page,
                        type=map_reporter_db_cite_type(
                            REPORTERS[citation.canonical_reporter][0][
                                "cite_type"
                            ]
                        ),
                        cluster_id=cluster.id,
                    )
                if len(str(soup)) < 10:
                    logger.info(f"Failed: HTML is empty at {dir}")
                    raise MissingDocumentError("Missing HTML content")

                html_str = str(
                    soup.find("div", {"class": "container"}).decode_contents()
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
            logger.info("Finished: %s", found_cites[0].base_citation())

        except MissingDocumentError:
            logger.info(f"HTML was missing/empty for {dir}")
        except Exception as e:
            logger.info(f"Failed to save {dir} to database.  Err msg {str(e)}")


class MissingDocumentError(Exception):
    """The document could not be opened or was empty."""

    def __init__(self, message):
        Exception.__init__(self, message)


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
