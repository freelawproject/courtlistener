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
from cl.search.models import Court, Opinion


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
            parallel_citation = case.get("parallel_citations")
            if not citation and not parallel_citation:
                logger.debug(
                    "No citation, skipping row for case %s",
                    case.get("case_names"),
                )
                continue

            try:
                content = get_binary_content(case["download_urls"], site)
            except BadContentError:
                continue

            sha1_hash = sha1(force_bytes(content))

            try:
                cluster = Opinion.objects.get(sha1=sha1_hash).cluster
            except Opinion.DoesNotExist:
                # populate special key to avoid downloading the file again
                case["content"] = content

                logger.info(
                    "Case '%s', opinion '%s' has no matching hash in the DB. "
                    "Has a citation '%s'. Will try to ingest all objects",
                    case["case_names"],
                    case["download_urls"],
                    citation or parallel_citation,
                )

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
