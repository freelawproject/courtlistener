import time

from juriscraper.AbstractSite import logger
from juriscraper.lib.importer import site_yielder

from cl.scrapers.management.commands import cl_scrape_oral_arguments
from cl.scrapers.management.commands.cl_back_scrape_opinions import (
    add_backscraper_arguments,
)
from cl.scrapers.utils import save_response


class Command(cl_scrape_oral_arguments.Command):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        add_backscraper_arguments(parser)

    def parse_and_scrape_site(self, mod, options: dict):
        court_str = mod.__name__.split(".")[-1].split("_")[0]
        logger.info(f'Using court_str: "{court_str}"')

        for site in site_yielder(
            mod.Site(
                backscrape_start=options.get("backscrape_start"),
                backscrape_end=options.get("backscrape_end"),
                days_interval=options.get("days_interval"),
            ).back_scrape_iterable,
            mod,
            save_response_fn=save_response,
        ):
            site.parse()
            self.scrape_court(site, full_crawl=True, backscrape=True)

            if wait := options["backscrape_wait"]:
                logger.info(
                    "Sleeping for %s seconds before continuing backscrape",
                    wait,
                )
                time.sleep(wait)
