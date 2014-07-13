from datetime import date

from requests import HTTPError

from alert.scrapers.management.commands import cl_scrape_opinions
from juriscraper.AbstractSite import logger


class Command(cl_scrape_opinions.Command):
    def scrape_court(self, site, full_crawl=False):
        download_error = False




    def parse_and_scrape_site(self, mod, full_crawl):
        for site in self.generate_sites(mod):
            site.parse()
            self.scrape_court(site, full_crawl=True)
