import signal
import sys
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Union

from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from django.db import transaction
from django.utils.encoding import force_bytes
from eyecite.find import get_citations
from juriscraper.lib.importer import build_module_list
from juriscraper.lib.string_utils import CaseNameTweaker
from sentry_sdk import capture_exception

from cl.alerts.models import RealTimeQueue
from cl.citations.utils import map_reporter_db_cite_type
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1
from cl.lib.string_utils import trunc
from cl.people_db.lookup_utils import lookup_judges_by_messy_str
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.models import ErrorLog
from cl.scrapers.tasks import extract_doc_content
from cl.scrapers.utils import (
    get_binary_content,
    get_child_court,
    get_extension,
    signal_handler,
    update_or_create_docket,
)
from cl.search.models import (
    SEARCH_TYPES,
    SOURCES,
    Citation,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    OriginatingCourtInformation,
)

# for use in catching the SIGINT (Ctrl+4)
die_now = False
cnt = CaseNameTweaker()


def check_duplicated_content(
    download_url: str,
    site,
    court: Court,
    precedential_status: str,
    current_date: date,
    next_date: date | None,
    dup_checker: DupChecker,
) -> Tuple[bytes, str, bool]:
    """Downloads opinion's content and checks duplication via hash

    :param download_url: opinion's content URL
    :param site: a juriscraper scraper object
    :param court: a court object, used to decide duplication lookup query
    :param precedential_status: used to decide duplication lookup query
    :param current_date: used by dup checker
    :param next_date: used by dup checker

    :return: opinion's raw content, sha1 hash
            and `proceed` flag to continue parsing the record or skip it
    """
    court_str = court.id
    # Minnesota currently rejects Courtlistener and Juriscraper as a User Agent
    if court_str in ["minn", "minnctapp"]:
        headers = site.headers
    else:
        headers = {"User-Agent": "CourtListener"}

    msg, r = get_binary_content(
        download_url,
        site,
        headers,
        method=site.method,
    )
    if msg:
        logger.warning(msg)
        ErrorLog(log_level="WARNING", court=court, message=msg).save()
        return b"", "", False

    content = site.cleanup_content(r.content)

    # request.content is sometimes a str, sometimes unicode, so
    # force it all to be bytes, pleasing hashlib.
    sha1_hash = sha1(force_bytes(content))
    if (
        court_str == "nev" and precedential_status == "Unpublished"
    ) or court_str in ["neb"]:
        # Nevada's non-precedential cases have different SHA1 sums
        # every time.

        # Nebraska updates the pdf causing the SHA1 to not match
        # the opinions in CL causing duplicates. See CL issue #1452

        lookup_params = {
            "lookup_value": download_url,
            "lookup_by": "download_url",
        }
    else:
        lookup_params = {
            "lookup_value": sha1_hash,
            "lookup_by": "sha1",
        }

    proceed = dup_checker.press_on(
        Opinion, current_date, next_date, **lookup_params
    )
    return content, sha1_hash, proceed


def make_citation(
    cite_str: str, cluster: OpinionCluster, court_id: str
) -> Optional[Citation]:
    """Create and return a citation object for the input values."""
    citation_objs = get_citations(cite_str)
    if not citation_objs:
        logger.error(
            "Could not parse citation from court '%s'",
            court_id,
            extra=dict(
                cite=cite_str,
                cluster=cluster,
                fingerprint=[f"{court_id}-no-citation-found"],
            ),
        )
        return None
    # Convert the found cite type to a valid cite type for our DB.
    cite_type_str = citation_objs[0].all_editions[0].reporter.cite_type
    return Citation(
        cluster=cluster,
        volume=citation_objs[0].groups["volume"],
        reporter=citation_objs[0].corrected_reporter(),
        page=citation_objs[0].groups["page"],
        type=map_reporter_db_cite_type(cite_type_str),
    )


def save_file_content(
    opinion: Opinion, cluster: OpinionCluster, content: bytes
) -> None:
    """Saves Opinion's file content and stores reference on Opinion object

    :param opinion: the opinion
    :param cluster: opinion's parent cluster
    :param content: file content
    """
    cf = ContentFile(content)
    extension = get_extension(content)
    file_name = trunc(cluster.case_name.lower(), 75) + extension
    opinion.file_with_date = cluster.date_filed
    opinion.local_path.save(file_name, cf, save=False)


@transaction.atomic
def make_objects(
    item: Dict[str, Union[str, Any]],
    court: Court,
    sha1_hash: str,
    content: bytes,
) -> Tuple[Docket, Opinion, OpinionCluster, List[Citation]]:
    """Takes the meta data from the scraper and associates it with objects.

    Returns the created objects.
    """
    blocked = item["blocked_statuses"]
    if blocked:
        date_blocked = date.today()
    else:
        date_blocked = None

    case_name_short = item.get("case_name_shorts") or cnt.make_case_name_short(
        item["case_names"]
    )

    docket = update_or_create_docket(
        item["case_names"],
        case_name_short,
        court.pk,
        item.get("docket_numbers", ""),
        item.get("source") or Docket.SCRAPER,
        blocked=blocked,
        date_blocked=date_blocked,
    )

    cluster = OpinionCluster(
        judges=item.get("judges", ""),
        date_filed=item["case_dates"],
        date_filed_is_approximate=item["date_filed_is_approximate"],
        case_name=item["case_names"],
        case_name_short=case_name_short,
        source=item.get("cluster_source") or SOURCES.COURT_WEBSITE,
        precedential_status=item["precedential_statuses"],
        nature_of_suit=item.get("nature_of_suit", ""),
        blocked=blocked,
        date_blocked=date_blocked,
        syllabus=item.get("summaries", ""),
    )

    cites = [item.get(key, "") for key in ["citations", "parallel_citations"]]
    citations = [
        make_citation(cite, cluster, court.id) for cite in cites if cite
    ]
    # Remove citations that did not parse correctly.
    citations = [cite for cite in citations if cite]

    url = item["download_urls"]
    if court.id == "tax":
        url = ""

    opinion = Opinion(
        type=Opinion.COMBINED,
        sha1=sha1_hash,
        download_url=url,
    )
    save_file_content(opinion, cluster, content)

    return docket, opinion, cluster, citations


@transaction.atomic
def make_validated_objects(
    docket_json: Dict[str, Union[str, Any]],
    contents: List[Tuple[bytes, str]],
    court: Court | str,
) -> Dict[
    str,
    Union[
        Docket,
        OpinionCluster,
        List[Opinion],
        List[Citation],
        OriginatingCourtInformation,
    ],
]:
    """Takes the meta data from the scraper and associates it with objects.
    :param docket_json: nested object scraped by scraper
    :param contents: opinion's file contents and hashes
    :param court: court string or object

    :return: dictionary of instantiated objects
    """
    items = {}

    # Unpack object
    d = docket_json["Docket"]
    oc = d.pop("OpinionCluster")
    op_json = oc.pop("Opinions")
    citation_strings = oc.pop("citation_strings", [])
    citations_json = oc.pop("Citations", [])
    oci = d.pop("OriginatingCourtInformation", {})

    if oci:
        items["originating_court_information"] = OriginatingCourtInformation(
            **oci
        )

    # Docket
    d["court_id"] = court.pk if isinstance(court, Court) else court
    docket = update_or_create_docket(**d)

    # OpinionCluster
    cluster = OpinionCluster(**oc)

    # Citations
    citations = []
    if citation_strings:
        for cite in citation_strings:
            if not cite:
                continue
            cite_obj = make_citation(cite, cluster, court.id)
            if cite_obj:
                citations.append(cite_obj)

    for cite_json in citations_json:
        citations.append(Citation(**cite_json))

    # Opinions
    opinions = []
    for opinion_json, (content, sha1_hash) in zip(op_json, contents):
        url = opinion_json["download_url"] if court.id != "tax" else ""
        opinion_json.update({"download_url": url, "sha1": sha1_hash})
        opinion = Opinion(**opinion_json)
        save_file_content(opinion, cluster, content)
        opinions.append(opinion)

    items.update(
        {
            "docket": docket,
            "opinion": opinions,
            "cluster": cluster,
            "citations": citations,
        }
    )
    return items


@transaction.atomic
def save_everything(
    items: Dict[str, Any],
    index: bool = False,
    backscrape: bool = False,
) -> None:
    """Saves all the sub items and associates them as appropriate."""
    docket, cluster = items["docket"], items["cluster"]
    opinions, citations = items["opinion"], items["citations"]

    oci = items.get("originating_court_information")
    if oci:
        docket.originating_court_information = oci
        oci.save()

    if not isinstance(opinions, list):
        opinions = [opinions]

    docket.save()
    cluster.docket = docket
    cluster.save(index=False)  # Index only when the opinion is associated.

    for citation in citations:
        citation.cluster_id = cluster.pk
        citation.save()

    if cluster.judges:
        candidate_judges = async_to_sync(lookup_judges_by_messy_str)(
            cluster.judges, docket.court.pk, cluster.date_filed
        )
        if len(candidate_judges) == 1:
            for opinion in opinions:
                if not opinion.author:
                    opinion.author = candidate_judges[0]

        if len(candidate_judges) > 1:
            for candidate in candidate_judges:
                cluster.panel.add(candidate)

    for opinion in opinions:
        opinion.cluster = cluster
        opinion.save(index=index)
        if not backscrape:
            RealTimeQueue.objects.create(
                item_type=SEARCH_TYPES.OPINION, item_pk=opinion.pk
            )


class Command(VerboseCommand):
    help = "Runs the Juriscraper toolkit against one or many jurisdictions."

    def __init__(self, stdout=None, stderr=None, no_color=False):
        super().__init__(stdout=None, stderr=None, no_color=False)

    def add_arguments(self, parser):
        parser.add_argument(
            "--daemon",
            action="store_true",
            default=False,
            help=(
                "Use this flag to turn on daemon mode, in which all "
                "courts requested will be scraped in turn, "
                "nonstop, in a loop."
            ),
        )
        parser.add_argument(
            "--rate",
            type=int,
            default=30,
            help=(
                "The length of time in minutes it takes to crawl "
                "all requested courts. Particularly useful if it is "
                "desired to quickly scrape over all courts. Default "
                "is 30 minutes."
            ),
        )
        parser.add_argument(
            "--courts",
            type=str,
            dest="court_id",
            metavar="COURTID",
            required=True,
            help=(
                "The court(s) to scrape and extract. This should be "
                "in the form of a python module or package import "
                "from the Juriscraper library, e.g. "
                '"juriscraper.opinions.united_states.federal_appellate.ca1" '
                'or simply "opinions" to do all opinions.'
            ),
        )
        parser.add_argument(
            "--fullcrawl",
            dest="full_crawl",
            action="store_true",
            default=False,
            help="Disable duplicate aborting.",
        )

    def scrape_court(self, site, full_crawl=False, ocr_available=True):
        # Get the court object early for logging
        # opinions.united_states.federal.ca9_u --> ca9
        court_str = site.court_id.split(".")[-1].split("_")[0]
        court = Court.objects.get(pk=court_str)

        dup_checker = DupChecker(court, full_crawl=full_crawl)
        if dup_checker.abort_by_url_hash(site.url, site.hash):
            logger.debug("Aborting by url hash.")
            return

        if site.cookies:
            logger.info(f"Using cookies: {site.cookies}")
        logger.debug(f"#{len(site)} opinions found.")
        added = 0

        is_cluster_site = getattr(site, "is_cluster_site", False)

        for i, item in enumerate(site):
            if is_cluster_site:
                oc = item["Docket"]["OpinionCluster"]
                try:
                    next_oc = site[i + 1]["Docket"]["OpinionCluster"]
                    next_date = next_oc["date_filed"]
                except IndexError:
                    next_date = None
                download_urls = [op["download_url"] for op in oc["Opinions"]]
                current_date = oc["date_filed"]
                case_name = oc["case_name"].encode()
                precedential_status = oc["precedential_status"]
            else:
                download_urls = [item["download_urls"]]
                current_date = item["case_dates"]
                precedential_status = item["precedential_statuses"]
                case_name = item["case_names"].encode()
                try:
                    next_date = site[i + 1]["case_dates"]
                except IndexError:
                    next_date = None

            opinion_contents = []
            for download_url in download_urls:
                content, sha1_hash, proceed = check_duplicated_content(
                    download_url,
                    site,
                    court,
                    precedential_status,
                    current_date,
                    next_date,
                    dup_checker,
                )
                opinion_contents.append((content, sha1_hash))

                if dup_checker.emulate_break:
                    logger.debug("Emulate break triggered.")
                    break
                if not proceed:
                    logger.debug("Skipping opinion.")
                    continue
                # Not a duplicate, carry on
                logger.info(
                    "Adding new document found at: %s", download_url.encode()
                )
                dup_checker.reset()

            if not opinion_contents:
                # When all opinions in a cluster have already been downloaded
                continue

            child_court = get_child_court(
                item.get("child_courts", ""), court.id
            )

            if is_cluster_site:
                items = make_validated_objects(
                    item, opinion_contents, child_court or court
                )
            else:
                # OpinionSite and OpinionSiteLinear scrapers support
                # a single opinion per scraped item
                docket, opinion, cluster, citations = make_objects(
                    item, child_court or court, sha1_hash, content
                )
                items = {
                    "docket": docket,
                    "opinion": opinion,
                    "cluster": cluster,
                    "citations": citations,
                }

            save_everything(items=items, index=False)

            opinions = items.get("opinion")
            for opinion in (
                opinions if isinstance(opinions, list) else [opinions]
            ):
                extract_doc_content.delay(
                    opinion.pk,
                    ocr_available=ocr_available,
                    citation_jitter=True,
                )
                logger.info(
                    "Successfully added opinion %s: %s", opinion.pk, case_name
                )

            added += len(opinion_contents)

        # Update the hash if everything finishes properly.
        logger.debug(
            f"{site.court_id}: Successfully crawled {added}/{len(site)} opinions."
        )
        if not full_crawl:
            # Only update the hash if no errors occurred.
            dup_checker.update_site_hash(site.hash)

    def parse_and_scrape_site(self, mod, full_crawl):
        site = mod.Site().parse()
        self.scrape_court(site, full_crawl)

    def handle(self, *args, **options):
        super().handle(*args, **options)
        global die_now

        # this line is used for handling SIGTERM (CTRL+4), so things can die
        # safely
        signal.signal(signal.SIGTERM, signal_handler)

        module_strings = build_module_list(options["court_id"])
        if not len(module_strings):
            raise CommandError("Unable to import module or package. Aborting.")

        logger.info("Starting up the scraper.")
        num_courts = len(module_strings)
        wait = (options["rate"] * 60) / num_courts
        i = 0
        while i < num_courts:
            # this catches SIGTERM, so the code can be killed safely.
            if die_now:
                logger.info("The scraper has stopped.")
                sys.exit(1)

            package, module = module_strings[i].rsplit(".", 1)

            mod = __import__(
                f"{package}.{module}", globals(), locals(), [module]
            )
            module_string = mod.Site().court_id
            court_id = module_string.split(".")[-1].split("_")[0]
            if not Court.objects.get(id=court_id).has_opinion_scraper:
                logger.info(f"{court_id} is currently disabled.")
                i += 1
                continue
            try:
                self.parse_and_scrape_site(mod, options["full_crawl"])
            except Exception as e:
                capture_exception(
                    e, fingerprint=[module_string, "{{ default }}"]
                )
            last_court_in_list = i == (num_courts - 1)
            daemon_mode = options["daemon"]
            if last_court_in_list:
                if not daemon_mode:
                    break
                else:
                    logger.info(
                        "All jurisdictions done. Looping back to "
                        "the beginning because daemon mode is enabled."
                    )
                    i = 0
            else:
                i += 1
            time.sleep(wait)

        logger.info("The scraper has stopped.")
