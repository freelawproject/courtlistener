from juriscraper.AbstractSite import logger
from juriscraper.lib.importer import site_yielder

from cl.scrapers.management.commands import cl_scrape_oral_arguments


class Command(cl_scrape_oral_arguments.Command):
    def parse_and_scrape_site(self, mod, options: dict):
        court_str = mod.__name__.split(".")[-1].split("_")[0]
        logger.info(f'Using court_str: "{court_str}"')

        for site in site_yielder(mod.Site().back_scrape_iterable, mod):
            site.parse()
            self.scrape_court(site, full_crawl=True, backscrape=True)
