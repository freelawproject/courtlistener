"""
When opinions are first published on the courts' sites, they won't have
all their citations assigned. Some courts will publish the citations
in the same pages we scrape, but months later

This command re-uses the (back)scraper we use to get opinions, to get
the lagged citations and associate them with the Opinions we first
downloaded. If we find an Opinion we don't have in the database,
we ingest it as in a regular scrape
"""

from django.utils.encoding import force_bytes

from cl.lib.command_utils import logger
from cl.lib.crypto import sha1
from cl.scrapers.management.commands import cl_back_scrape_opinions
from cl.scrapers.management.commands.cl_scrape_opinions import make_citation
from cl.scrapers.utils import get_binary_content
from cl.search.models import Citation, Opinion, OpinionCluster


class Command(cl_back_scrape_opinions.Command):
    def scrape_court(self, site, full_crawl=False, ocr_available=True):
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
        missing_opinions = []
        court_str = site.court_id.split(".")[-1].split("_")[0]

        for case in site:
            citation = case.get("citations")
            parallel_citation = case.get("parallel_citations")
            if not citation and not parallel_citation:
                logger.debug(
                    "No citation, skipping row for case %s",
                    case.get("case_names"),
                )
                continue

            content = get_binary_content(case["download_urls"], site)
            if not content:
                # Errors are logged by get_binary_content itself
                continue
            sha1_hash = sha1(force_bytes(content))

            try:
                cluster = Opinion.objects.get(sha1=sha1_hash).cluster
            except Opinion.DoesNotExist:
                missing_opinions.append(case)
                logger.info(
                    "Case '%s', opinion '%s' has no matching hash in the DB. "
                    "Has a citation '%s'. Will try to ingest all objects",
                    case["case_names"],
                    case["download_urls"],
                    citation or parallel_citation,
                )
                continue

            for cite in [citation, parallel_citation]:
                if not cite:
                    continue

                citation_candidate = make_citation(cite, cluster, court_str)
                if not citation_candidate:
                    continue

                if self.citation_is_duplicated(
                    citation_candidate, cluster, cite
                ):
                    continue

                logger.info("Saving citation %s for cluster %s", cite, cluster)
                citation_candidate.save()

        # We don't have these opinions. Since we are backscraping, if the citation
        # exists, it will be in the case dictionary, and will be saved in a
        # regular ingestion process
        if missing_opinions:
            # It is easy to ingest a filtered list of cases for OpinionSiteLinear
            # but not for plain OpinionSite
            if hasattr(site, "cases"):
                site.cases = missing_opinions
                super().scrape_court(site, full_crawl=True)
            else:
                logger.info("Run the backscraper to collect missing opinions")

    def citation_is_duplicated(
        self, citation_candidate: Citation, cluster: OpinionCluster, cite: str
    ) -> bool:
        """Checks for exact or reporter duplication of citation in the cluster
        Inspired on corpus_importer.utils.add_citations_to_cluster
        """
        citation_params = {**citation_candidate.__dict__}
        citation_params.pop("_state", "")
        citation_params.pop("id", "")

        # Exact duplication
        if Citation.objects.filter(**citation_params).exists():
            logger.info(
                "Citation '%s' already exists for cluster %s",
                cite,
                cluster.id,
            )
            return True

        # Duplication in the same reporter
        if Citation.objects.filter(
            cluster_id=cluster.id, reporter=citation_candidate.reporter
        ).exists():
            logger.info(
                "Another citation in the same reporter '%s' exists for cluster %s",
                citation_candidate.reporter,
                cluster.id,
            )
            return True

        return False
