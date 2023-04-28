import signal
import sys
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Union

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
)

# for use in catching the SIGINT (Ctrl+4)
die_now = False
cnt = CaseNameTweaker()


def make_citation(
    cite_str: str,
    cluster: OpinionCluster,
) -> Optional[Citation]:
    """Create and return a citation object for the input values."""
    citation_objs = get_citations(cite_str)
    if not citation_objs:
        logger.error(
            f"Could not parse citation",
            extra=dict(cite=cite_str, cluster=cluster),
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
    citations = [make_citation(cite, cluster) for cite in cites if cite]
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

    cf = ContentFile(content)
    extension = get_extension(content)
    file_name = trunc(item["case_names"].lower(), 75) + extension
    opinion.file_with_date = cluster.date_filed
    opinion.local_path.save(file_name, cf, save=False)

    return docket, opinion, cluster, citations


@transaction.atomic
def save_everything(
    items: Dict[str, Any],
    index: bool = False,
    backscrape: bool = False,
) -> None:
    """Saves all the sub items and associates them as appropriate."""
    docket, cluster = items["docket"], items["cluster"]
    opinion, citations = items["opinion"], items["citations"]
    docket.save()
    cluster.docket = docket
    cluster.save(index=False)  # Index only when the opinion is associated.

    for citation in citations:
        citation.cluster_id = cluster.pk
        citation.save()

    if cluster.judges:
        candidate_judges = lookup_judges_by_messy_str(
            cluster.judges, docket.court.pk, cluster.date_filed
        )
        if len(candidate_judges) == 1:
            opinion.author = candidate_judges[0]

        if len(candidate_judges) > 1:
            for candidate in candidate_judges:
                cluster.panel.add(candidate)

    opinion.cluster = cluster
    opinion.save(index=index)
    if not backscrape:
        RealTimeQueue.objects.create(
            item_type=SEARCH_TYPES.OPINION, item_pk=opinion.pk
        )


class Command(VerboseCommand):
    help = "Runs the Juriscraper toolkit against one or many jurisdictions."

    def __init__(self, stdout=None, stderr=None, no_color=False):
        super(Command, self).__init__(stdout=None, stderr=None, no_color=False)

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
            logger.debug(f"Aborting by url hash.")
            return

        if site.cookies:
            logger.info(f"Using cookies: {site.cookies}")
        logger.debug(f"#{len(site)} opinions found.")
        added = 0
        for i, item in enumerate(site):
            msg, r = get_binary_content(
                item["download_urls"],
                site.cookies,
                method=site.method,
            )
            if msg:
                logger.warning(msg)
                ErrorLog(log_level="WARNING", court=court, message=msg).save()
                continue

            content = site.cleanup_content(r.content)

            current_date = item["case_dates"]
            try:
                next_date = site[i + 1]["case_dates"]
            except IndexError:
                next_date = None

            # request.content is sometimes a str, sometimes unicode, so
            # force it all to be bytes, pleasing hashlib.
            sha1_hash = sha1(force_bytes(content))
            if (
                court_str == "nev"
                and item["precedential_statuses"] == "Unpublished"
            ) or court_str in ["neb"]:
                # Nevada's non-precedential cases have different SHA1 sums
                # every time.

                # Nebraska updates the pdf causing the SHA1 to not match
                # the opinions in CL causing duplicates. See CL issue #1452

                lookup_params = {
                    "lookup_value": item["download_urls"],
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
            if dup_checker.emulate_break:
                logger.debug("Emulate break triggered.")
                break
            if not proceed:
                logger.debug("Skipping opinion.")
                continue

            # Not a duplicate, carry on
            logger.info(
                f"Adding new document found at: {item['download_urls'].encode()}"
            )
            dup_checker.reset()

            docket, opinion, cluster, citations = make_objects(
                item, court, sha1_hash, content
            )

            save_everything(
                items={
                    "docket": docket,
                    "opinion": opinion,
                    "cluster": cluster,
                    "citations": citations,
                },
                index=False,
            )
            extract_doc_content.delay(
                opinion.pk, ocr_available=ocr_available, citation_jitter=True
            )

            logger.info(
                f"Successfully added opinion {opinion.pk}: "
                f"{item['case_names'].encode()}"
            )
            added += 1

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
        super(Command, self).handle(*args, **options)
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
            try:
                self.parse_and_scrape_site(mod, options["full_crawl"])
            except Exception as e:
                capture_exception(e)
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
