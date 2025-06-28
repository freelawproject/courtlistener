"""
When opinions are first published on the courts' sites, they won't have
all their citations assigned. Some courts will publish the citations
in the same pages we scrape, but months later

This command re-uses the (back)scraper we use to get opinions, to get
the lagged citations and associate them with the Opinions we first
downloaded. If we find an Opinion we don't have in the database,
we ingest it as in a regular scrape
"""

from django.db import IntegrityError
from django.utils.encoding import force_bytes

from cl.lib.command_utils import logger
from cl.lib.crypto import sha1
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.exceptions import BadContentError
from cl.scrapers.management.commands import cl_back_scrape_opinions
from cl.scrapers.management.commands.cl_scrape_opinions import make_citation
from cl.scrapers.utils import citation_is_duplicated, get_binary_content
from cl.search.models import Court, Opinion, OpinionCluster


class Command(cl_back_scrape_opinions.Command):
    scrape_target_descr = "citations"
    juriscraper_module_type = "opinions"

    def scrape_court(
        self,
        site,
        full_crawl: bool = False,
        ocr_available: bool = True,
        backscrape: bool = False,
    ):
        """
        If the scraped case has citation data
            Check for Opinion existance via content hash
            If we have the Opinion
                if we don't have the citation -> ingest
                if we already have the citation -> pass
            If we don't have the Opinion
                ingest the opinion with it's citation, that is to say,
                use the regular scraping process!

        :param site: scraper object that has already downloaded
            it's case data
        """
        court_str = site.court_id.split(".")[-1].split("_")[0]
        court = Court.objects.get(id=court_str)
        dup_checker = DupChecker(court, full_crawl=True)

        for case in site:
            citation = case.get("citations")
            docket_number = case.get("docket_numbers") if citation else None
            parallel_citation = case.get("parallel_citations")
            content = None
            if not citation and not parallel_citation:
                logger.debug(
                    "No citation, skipping row for case %s",
                    case.get("case_names"),
                )
                continue
            try:
                if court_str == "scotus":
                    # In SCOTUS, docket numbers are unique, so we can use them to match citations.
                    # We use filter (not get) because the system has duplicates: the court site sometimes
                    # do minor updates to their opinion files, and we end up with multiple clusters. But we only want the most recent one.
                    cluster = (
                        OpinionCluster.objects.filter(
                            docket__court=court,
                            docket__docket_number=docket_number,
                            case_name=case.get("case_names"),
                            date_filed=case.get("case_dates"),
                            judges=case.get("judges"),
                        )
                        .order_by("-date_created")
                        .first()
                    )
                else:
                    content = get_binary_content(case["download_urls"], site)
                    sha1_hash = sha1(force_bytes(content))
                    cluster = Opinion.objects.get(sha1=sha1_hash).cluster
            except BadContentError:
                continue
            except (OpinionCluster.DoesNotExist, Opinion.DoesNotExist) as e:
                logger.info(
                    "Case '%s', opinion '%s' has no match in the DB. "
                    "Has a citation '%s'. Will try to ingest all objects",
                    case["case_names"],
                    case["download_urls"],
                    citation or parallel_citation,
                )
                if isinstance(e, Opinion.DoesNotExist):
                    case["content"] = content
                self.ingest_a_case(case, None, True, site, dup_checker, court)
                continue

            for cite in [citation, parallel_citation]:
                if not cite:
                    continue

                citation_candidate = make_citation(cite, cluster, court_str)
                if not citation_candidate:
                    continue

                if citation_is_duplicated(citation_candidate, cite):
                    continue

                try:
                    citation_candidate.save()
                    logger.info(
                        "Saved citation %s for cluster %s", cite, cluster
                    )
                except IntegrityError:
                    logger.warning(
                        "Error when saving citation %s for cluster %s",
                        cite,
                        cluster,
                    )
