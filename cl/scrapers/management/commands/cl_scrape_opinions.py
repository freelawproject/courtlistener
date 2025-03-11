import signal
import sys
import time
import traceback
from datetime import date
from typing import Any, Dict, List, Tuple, Union

from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from django.db import transaction
from django.utils.encoding import force_bytes
from juriscraper.lib.exceptions import InvalidDocumentError
from juriscraper.lib.importer import build_module_list
from juriscraper.lib.string_utils import CaseNameTweaker
from sentry_sdk import capture_exception

from cl.alerts.models import RealTimeQueue
from cl.lib.command_utils import ScraperCommand, logger
from cl.lib.crypto import sha1
from cl.lib.string_utils import trunc
from cl.people_db.lookup_utils import lookup_judges_by_messy_str
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.exceptions import (
    BadContentError,
    ConsecutiveDuplicatesError,
    SingleDuplicateError,
)
from cl.scrapers.tasks import extract_doc_content
from cl.scrapers.utils import (
    get_binary_content,
    get_child_court,
    get_extension,
    make_citation,
    save_response,
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


@transaction.atomic
def make_objects(
    item: Dict[str, Union[str, Any]],
    court: Court,
    sha1_hash: str,
    content: bytes,
) -> Tuple[Docket, Opinion, OpinionCluster, List[Citation]]:
    """Takes the meta data from the scraper and associates it with objects.

    The keys returned by juriscraper scrapers are defined by `self._all_attrs`
    on OpinionSite and OralArgumentSite, where the legacy convention is to use
    plural names.

    However, this function is also used by importers and user pages, that
    may not respect this convention, thus the duplication of singular and
    plural names, like in
    `item.get("disposition") or item.get("dispositions", "")`

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
        court,
        item.get("docket_numbers", ""),
        item.get("source") or Docket.SCRAPER,
        from_harvard=False,
        blocked=blocked,
        date_blocked=date_blocked,
        appeal_from_str=item.get("lower_courts", ""),
    )

    # Note that if opinion.author_str has no value, and cluster.judges find
    # a single judge, opinion.author will be populated with that Person object
    # Check `save_everything`

    # For a discussion on syllabus vs summary, check
    # https://github.com/freelawproject/juriscraper/issues/66
    cluster = OpinionCluster(
        date_filed=item["case_dates"],
        date_filed_is_approximate=item["date_filed_is_approximate"],
        case_name=item["case_names"],
        case_name_short=case_name_short,
        source=item.get("cluster_source") or SOURCES.COURT_WEBSITE,
        precedential_status=item["precedential_statuses"],
        blocked=blocked,
        date_blocked=date_blocked,
        judges=item.get("judges", ""),
        nature_of_suit=item.get("nature_of_suit", ""),
        disposition=item.get("disposition") or item.get("dispositions", ""),
        other_dates=item.get("other_dates", ""),
        summary=item.get("summary", ""),
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
        type=item.get("types", Opinion.COMBINED),
        sha1=sha1_hash,
        download_url=url,
        joined_by_str=item.get("joined_by", ""),
        per_curiam=item.get("per_curiam", False),
        author_str=item.get("author_str") or item.get("authors", ""),
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
    backscrape: bool = False,
) -> None:
    """Saves all the sub items and associates them as appropriate."""
    docket, cluster = items["docket"], items["cluster"]
    opinion, citations = items["opinion"], items["citations"]
    docket.save()
    cluster.docket = docket
    cluster.save()

    for citation in citations:
        citation.cluster_id = cluster.pk
        citation.save()

    if opinion.author_str:
        candidate = async_to_sync(lookup_judges_by_messy_str)(
            opinion.author_str, docket.court.pk, cluster.date_filed
        )
        if len(candidate) == 1:
            opinion.author = candidate[0]

    if cluster.judges:
        candidate_judges = async_to_sync(lookup_judges_by_messy_str)(
            cluster.judges, docket.court.pk, cluster.date_filed
        )

        if len(candidate_judges) == 1 and not opinion.author_str:
            opinion.author = candidate_judges[0]
        elif len(candidate_judges) > 1:
            for candidate in candidate_judges:
                cluster.panel.add(candidate)

    opinion.cluster = cluster
    opinion.save()
    if not backscrape:
        RealTimeQueue.objects.create(
            item_type=SEARCH_TYPES.OPINION, item_pk=opinion.pk
        )


class Command(ScraperCommand):
    help = "Runs the Juriscraper toolkit against one or many jurisdictions."
    juriscraper_module_type = "opinions"
    scrape_target_descr = "opinions"  # for logging purposes

    def __init__(self, stdout=None, stderr=None, no_color=False):
        super().__init__(stdout=None, stderr=None, no_color=False)

    def add_arguments(self, parser):
        super().add_arguments(parser)
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
            "--fullcrawl",
            dest="full_crawl",
            action="store_true",
            default=False,
            help="Disable duplicate aborting.",
        )

    def scrape_court(
        self,
        site,
        full_crawl: bool = False,
        ocr_available: bool = True,
        backscrape: bool = False,
    ):
        # Get the court object early for logging
        # opinions.united_states.federal.ca9_u --> ca9
        court_str = site.court_id.split(".")[-1].split("_")[0]
        court = Court.objects.get(pk=court_str)

        dup_checker = DupChecker(court, full_crawl=full_crawl)
        if dup_checker.abort_by_url_hash(site.url, site.hash):
            logger.debug("Aborting by url hash.")
            return

        if site.cookies:
            logger.info("Using cookies: %s", site.cookies)

        logger.debug("#%s %s found.", len(site), self.scrape_target_descr)

        added = 0
        for i, item in enumerate(site):
            try:
                next_date = site[i + 1]["case_dates"]
            except IndexError:
                next_date = None

            try:
                self.ingest_a_case(
                    item, next_date, ocr_available, site, dup_checker, court
                )
                added += 1
            except ConsecutiveDuplicatesError:
                break
            except (
                SingleDuplicateError,
                BadContentError,
                InvalidDocumentError,
            ):
                pass

        # Update the hash if everything finishes properly.
        logger.debug(
            "%s: Successfully crawled %s/%s %s.",
            site.court_id,
            added,
            len(site),
            self.scrape_target_descr,
        )
        if not full_crawl:
            # Only update the hash if no errors occurred.
            dup_checker.update_site_hash(site.hash)

    def ingest_a_case(
        self,
        item,
        next_case_date: date | None,
        ocr_available: bool,
        site,
        dup_checker: DupChecker,
        court: Court,
    ):
        if item.get("content"):
            content = item.pop("content")
        else:
            content = get_binary_content(item["download_urls"], site)

        # request.content is sometimes a str, sometimes unicode, so
        # force it all to be bytes, pleasing hashlib.
        sha1_hash = sha1(force_bytes(content))

        if (
            court.pk == "nev"
            and item["precedential_statuses"] == "Unpublished"
        ) or court.pk in ["neb"]:
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

        # Duplicates will raise errors
        dup_checker.press_on(
            Opinion, item["case_dates"], next_case_date, **lookup_params
        )

        # Not a duplicate, carry on
        logger.info(
            "Adding new document found at: %s", item["download_urls"].encode()
        )
        dup_checker.reset()

        child_court = get_child_court(item.get("child_courts", ""), court.id)

        docket, opinion, cluster, citations = make_objects(
            item, child_court or court, sha1_hash, content
        )

        save_everything(
            items={
                "docket": docket,
                "opinion": opinion,
                "cluster": cluster,
                "citations": citations,
            }
        )
        extract_doc_content.delay(
            opinion.pk,
            ocr_available=ocr_available,
            citation_jitter=True,
            juriscraper_module=site.court_id,
        )

        logger.info(
            "Successfully added opinion %s: %s",
            opinion.pk,
            item["case_names"].encode(),
        )

    def parse_and_scrape_site(self, mod, options: dict):
        site = mod.Site(save_response_fn=save_response).parse()
        self.scrape_court(site, options["full_crawl"])

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
                self.parse_and_scrape_site(mod, options)
            except Exception as e:
                capture_exception(
                    e, fingerprint=[module_string, "{{ default }}"]
                )
                logger.debug(traceback.format_exc())
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
