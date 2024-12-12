import time

from juriscraper import AbstractSite
from juriscraper.AbstractSite import logger
from juriscraper.lib.importer import site_yielder

from cl.scrapers.management.commands import cl_scrape_opinions
from cl.scrapers.utils import save_response


def add_backscraper_arguments(parser) -> None:
    """Adds backscraper specific optional arguments to the parser"""
    parser.add_argument(
        "--backscrape-start",
        dest="backscrape_start",
        help="Starting value for backscraper iterable creation. "
        "Each scraper handles the parsing of the argument,"
        "since the value may represent a year, a string, a date, etc.",
    )
    parser.add_argument(
        "--backscrape-end",
        dest="backscrape_end",
        help="End value for backscraper iterable creation.",
    )
    parser.add_argument(
        "--days-interval",
        help="Days between each (start, end) date pairs in "
        "the back_scrape_iterable. Useful to shorten the ranges"
        "when there are too many opinions in a range, and the source"
        "imposes a limit of returned documents",
        type=int,
    )
    parser.add_argument(
        "--backscrape-wait",
        type=int,
        default=0,
        help="Seconds to wait after consuming each element "
        "of the backscrape iterable. Useful to avoid overloading"
        " a target server when backscraping.",
    )


class Command(cl_scrape_opinions.Command):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        add_backscraper_arguments(parser)

    def parse_and_scrape_site(
        self,
        mod: AbstractSite,
        options: dict,
    ) -> None:
        """Parse the site and scrape it using the backscraper

        :param mod: The juriscraper Site object to scrape
        :param options: argparse kwargs dictionary. May contain the following keys:
            - full_crawl: Whether or not to do a full crawl (Ignored value)
            - backscrape_start: string which may be a date, year, index, etc.
                which is parsed and used by a scraper as start value for the
                range to be backscraped
            - backscrape_end: end value for backscraper range
            - days_interval: days between each (start, end) date pairs in the
                Site.back_scrape_iterable
            - backscrape_wait: Seconds to wait after consuming each element
                of the backscrape iterable

        :return: None
        """
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
            self.scrape_court(site, full_crawl=True)

            if wait := options["backscrape_wait"]:
                logger.info(
                    "Sleeping for %s seconds before continuing backscrape",
                    wait,
                )
                time.sleep(wait)

    def save_everything(self, items, backscrape=True):
        super().save_everything(items, backscrape)
