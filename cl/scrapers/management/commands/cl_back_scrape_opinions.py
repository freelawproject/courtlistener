from cl.scrapers.management.commands import cl_scrape_opinions
from juriscraper.AbstractSite import logger
from juriscraper.lib.importer import site_yielder


class Command(cl_scrape_opinions.Command):
    def parse_and_scrape_site(self, mod, full_crawl):
        court_str = mod.__name__.split(".")[-1].split("_")[0]
        logger.info('Using court_str: "%s"' % court_str)

        for site in site_yielder(mod.Site().back_scrape_iterable, mod):
            site.parse()
            self.scrape_court(site, full_crawl=True)

    def save_everything(self, items, index=False, backscrape=True):
        super(Command, self).save_everything(items, index, backscrape)
