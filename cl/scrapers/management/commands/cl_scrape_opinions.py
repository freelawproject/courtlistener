import signal
import sys
import time
import traceback
from datetime import date
from typing import Any

from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from django.db import transaction
from django.utils.encoding import force_bytes
from juriscraper.lib.exceptions import BadContentError, InvalidDocumentError
from juriscraper.lib.importer import build_module_list
from juriscraper.lib.string_utils import CaseNameTweaker
from sentry_sdk import capture_exception

from cl import settings
from cl.lib.command_utils import ScraperCommand, logger
from cl.lib.crypto import sha1
from cl.lib.string_utils import trunc
from cl.people_db.lookup_utils import lookup_judges_by_messy_str
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.exceptions import (
    ConsecutiveDuplicatesError,
    SingleDuplicateError,
)
from cl.scrapers.tasks import extract_opinion_content
from cl.scrapers.utils import (
    check_duplicate_ingestion,
    get_child_court,
    get_extension,
    make_citation,
    save_response,
    signal_handler,
    update_or_create_docket,
    update_or_create_originating_court_information,
)
from cl.search.models import (
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


def set_ordering_keys(opinions_content: list[tuple[dict]]) -> None:
    """Set a value for Opinion.ordering_key

    To know the relative order inside the cluster, we must know all the
    opinion types. Opinion types have an inherent order given by the first
    3 digits "010combined" < "020lead" < "030concurrence" < "040dissent" ...

    For scraped clusters we may
    - get 2 of one type. For example, 2 concurrences

    :param opinions_content: a list of tuples; where the first element of each
        tuple is a metadata dict
    :return None
    """
    types = [
        # we are sure the types key exist, since this is a cluster with more
        # than 1 opinion
        (opinion_metadata["types"], index)
        for index, (opinion_metadata, _, _) in enumerate(opinions_content)
    ]
    order = 1
    for _, index in sorted(types):
        opinions_content[index][0]["ordering_key"] = order
        order += 1


@transaction.atomic
def make_objects(
    item: dict[str, str | Any],
    court: Court,
    opinions_content: list[tuple[dict, bytes, str]],
) -> tuple[
    Docket,
    list[Opinion],
    OpinionCluster,
    list[Citation],
    OriginatingCourtInformation,
]:
    """Takes the meta data from the scraper and associates it with objects.

    The keys returned by juriscraper scrapers are defined by `self._all_attrs`
    on OpinionSite and OralArgumentSite, where the legacy convention is to use
    plural names.

    However, this function is also used by importers and user pages, that
    may not respect this convention, thus the duplication of singular and
    plural names, like in
    `item.get("disposition") or item.get("dispositions", "")`

    :return: the created objects.
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
        appeal_from_id=item.get("lower_court_ids", ""),
    )
    originating_court_info = update_or_create_originating_court_information(
        docket,
        item.get("lower_court_numbers", ""),
        item.get("lower_court_judges", ""),
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

    opinions = []

    if len(opinions_content) > 1:
        set_ordering_keys(opinions_content)

    for opinion_metadata, content, sha1_hash in opinions_content:
        url = opinion_metadata["download_urls"]
        if court.id == "tax":
            url = ""

        opinion = Opinion(
            type=opinion_metadata.get("types", Opinion.COMBINED),
            sha1=sha1_hash,
            download_url=url,
            joined_by_str=opinion_metadata.get("joined_by", ""),
            per_curiam=opinion_metadata.get("per_curiam", False),
            author_str=opinion_metadata.get("author_str")
            or opinion_metadata.get("authors", ""),
            ordering_key=opinion_metadata.get("ordering_key"),
        )

        cf = ContentFile(content)
        extension = get_extension(content)
        file_name = trunc(item["case_names"].lower(), 75) + extension
        opinion.file_with_date = cluster.date_filed
        opinion.local_path.save(file_name, cf, save=False)
        check_duplicate_ingestion(opinion.local_path.name)

        opinions.append(opinion)

    return docket, opinions, cluster, citations, originating_court_info


@transaction.atomic
def save_everything(
    items: dict[str, Any],
    backscrape: bool = False,
) -> None:
    """Saves all the sub items and associates them as appropriate."""
    docket, cluster = items["docket"], items["cluster"]
    opinions, citations = items["opinions"], items["citations"]
    originating_court_info = items.get("originating_court_information")

    # if the docket already had a related `originating_court_information`
    # the update was saved in the `make_objects` call
    if originating_court_info and not docket.originating_court_information:
        originating_court_info.save()
        docket.originating_court_information = originating_court_info

    docket.save()
    cluster.docket = docket
    cluster.save()

    for citation in citations:
        citation.cluster_id = cluster.pk
        citation.save()

    if cluster.judges:
        candidate_judges = async_to_sync(lookup_judges_by_messy_str)(
            cluster.judges, docket.court.pk, cluster.date_filed
        )

        if (
            len(candidate_judges) == 1
            and len(opinions) == 1
            and not opinions[0].author_str
        ):
            opinions[0].author = candidate_judges[0]
        elif len(candidate_judges) > 1:
            for candidate in candidate_judges:
                cluster.panel.add(candidate)

    for opinion in opinions:
        if opinion.author_str:
            candidate = async_to_sync(lookup_judges_by_messy_str)(
                opinion.author_str, docket.court.pk, cluster.date_filed
            )
            if len(candidate) == 1:
                opinion.author = candidate[0]

        opinion.cluster = cluster
        opinion.save()


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

        # do not update the site hash on a backscrape or manual full crawl
        update_site_hash = not full_crawl

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
            except SingleDuplicateError:
                pass
            except (BadContentError, InvalidDocumentError):
                # do not update site hash to ensure a retry on the next scrape
                update_site_hash = False

        # Update the hash if everything finishes properly.
        logger.debug(
            "%s: Successfully crawled %s/%s %s.",
            site.court_id,
            added,
            len(site),
            self.scrape_target_descr,
        )

        if update_site_hash:
            dup_checker.update_site_hash(site.hash)

    def get_opinions_content(
        self, case_dict: dict, site, court, dup_checker, next_case_date
    ) -> list[tuple[dict, bytes, str]]:
        """Downloads opinions and checks if the content is duplicated

        :return: a list of dictionaries containing the binary content and the hash of the content
        """
        opinions_content = []
        opinions_to_download = []

        # this field is populated when usign cl_back_scrape_citations
        if case_dict.get("content"):
            content = case_dict.pop("content")
            opinions_content.append(
                (case_dict, content, sha1(force_bytes(content)))
            )
        elif case_dict.get("sub_opinions"):
            opinions_to_download = case_dict["sub_opinions"]
        else:
            opinions_to_download.append(case_dict)

        # download content
        for sub_opinion in opinions_to_download:
            content = async_to_sync(site.download_content)(
                sub_opinion["download_urls"], media_root=settings.MEDIA_ROOT
            )
            opinions_content.append(
                (sub_opinion, content, sha1(force_bytes(content)))
            )

        for metadata, content, sha1_hash in opinions_content:
            if (
                court.pk == "nev"
                and case_dict["precedential_statuses"] == "Unpublished"
            ) or court.pk in ["neb"]:
                # Nevada's non-precedential cases have different SHA1 sums
                # every time.

                # Nebraska updates the pdf causing the SHA1 to not match
                # the opinions in CL causing duplicates. See CL issue #1452

                lookup_params = {
                    "lookup_value": metadata["download_urls"],
                    "lookup_by": "download_url",
                }
            else:
                lookup_params = {
                    "lookup_value": sha1_hash,
                    "lookup_by": "sha1",
                }

            # Duplicates will raise errors
            try:
                dup_checker.press_on(
                    Opinion,
                    case_dict["case_dates"],
                    next_case_date,
                    **lookup_params,
                )
            except SingleDuplicateError as exc:
                # track clusters if they have more than 1 sub opinions but one
                # of them is a duplicate
                if len(opinions_content) > 1:
                    logger.error(
                        "Cluster had 1 of %s duplicate sub opinion %s",
                        len(opinions_content),
                        opinions_to_download,
                        exc_info=True,
                    )
                raise exc

            # Not a duplicate, carry on
            logger.info(
                "Adding new document found at: %s",
                metadata["download_urls"].encode(),
            )
            dup_checker.reset()

        return opinions_content

    def ingest_a_case(
        self,
        item,
        next_case_date: date | None,
        ocr_available: bool,
        site,
        dup_checker: DupChecker,
        court: Court,
    ):
        opinions_content = self.get_opinions_content(
            item, site, court, dup_checker, next_case_date
        )

        child_court = get_child_court(item.get("child_courts", ""), court.id)

        docket, opinions, cluster, citations, originating_court_info = (
            make_objects(item, child_court or court, opinions_content)
        )

        save_everything(
            items={
                "docket": docket,
                "opinions": opinions,
                "cluster": cluster,
                "citations": citations,
                "originating_court_information": originating_court_info,
            }
        )

        for opinion in opinions:
            extract_opinion_content.delay(
                opinion.pk,
                ocr_available=ocr_available,
                juriscraper_module=site.court_id,
                percolate_opinion=True,
            )

            logger.info(
                "Successfully added opinion %s: %s",
                opinion.pk,
                item["case_names"].encode(),
            )

    def parse_and_scrape_site(self, mod, options: dict):
        site = async_to_sync(mod.Site(save_response_fn=save_response).parse)()
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
