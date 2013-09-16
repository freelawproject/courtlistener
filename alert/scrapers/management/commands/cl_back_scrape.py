from django.core.management import BaseCommand, CommandError
from alert.scrapers.management.commands.cl_scrape_and_extract import scrape_court

from juriscraper.GenericSite import logger
from juriscraper.lib.importer import build_module_list

import traceback
from datetime import date
from dateutil.rrule import rrule
from dateutil.rrule import DAILY, WEEKLY, MONTHLY
from optparse import make_option
from requests import HTTPError


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('-c',
                    '--courts',
                    dest='court_id',
                    metavar='COURTID',
                    help='The court(s) to scrape and extract. This should be in the form of a Python module or package'
                         'import from the Juriscraper library, e.g. "juriscraper.opinions.united_states.federal.ca1" '
                         'or simply "juriscraper.opinions" to do everything.'),
    )
    args = 'c COURTID'
    help = 'Runs the backwards-facing scraper against a court or collection of courts.'

    def site_yielder(self, iterable, mod):
        for i in iterable:
            try:
                site = mod.Site()
                site._download_backwards(i)
                yield site
            except HTTPError, e:
                logger.warn("Failed to download page.")
                continue

    def generate_sites(self, mod):
        # opinions.united_states.federal.ca9u --> ca9
        court_str = mod.__name__.split('.')[-1].split('_')[0]
        logger.info("Using court_str: \"%s\"" % court_str)

        if court_str == 'ca4':
            #start = date(1996, 1, 1)
            #start = date(1998, 11, 23)
            start  = date (1998, 11, 23)
            end = date(2010, 4, 1)
            return self.site_yielder([i.date() for i in rrule(WEEKLY, dtstart=start, until=end)], mod)
        elif court_str == 'cafc':
            return self.site_yielder(range(0, 185), mod)
        elif 'haw' in court_str:
            return self.site_yielder(range(2010, 2013), mod)
        elif court_str == 'mich':
            return self.site_yielder(range(0, 868), mod)
        elif court_str == 'miss':
            return self.site_yielder(range(1990, 2012), mod)
        elif court_str == 'mont':
            return self.site_yielder(range(1972, 2014), mod)
        elif 'neb' in court_str:
            return self.site_yielder(range(0, 11), mod)
        elif court_str in ['nd', 'ndctapp']:
            start = date(1996, 9, 1)
            end = date(2013, 6, 1)
            return self.site_yielder([i.date() for i in rrule(MONTHLY, dtstart=start, until=end)], mod)
        elif court_str in ['nmctapp', 'nm']:
            return self.site_yielder(range(2009, 2013), mod)
        elif court_str == 'sd':
            return self.site_yielder(range(1996, 2013), mod)
        elif court_str == 'tex':
            start = date(1997, 10, 2)
            end = date(2013, 6, 5)
            return self.site_yielder([i.date() for i in rrule(DAILY, dtstart=start, until=end)], mod)

    def back_scrape(self, mod):
        for site in self.generate_sites(mod):
            site.parse()
            scrape_court(site, full_crawl=True)

    def handle(self, *args, **options):
        court_id = options.get('court_id')
        if not court_id:
            raise CommandError('You must specify a court as a package or module')
        else:
            module_strings = build_module_list(court_id)
            if not len(module_strings):
                raise CommandError('Unable to import module or package. Aborting.')

            logger.info("Starting up the scraper.")
            num_courts = len(module_strings)
            i = 0
            while i < num_courts:
                package, module = module_strings[i].rsplit('.', 1)

                mod = __import__("%s.%s" % (package, module),
                                 globals(),
                                 locals(),
                                 [module])
                # noinspection PyBroadException
                try:
                    self.back_scrape(mod)
                except Exception, e:
                    msg = ('********!! CRAWLER DOWN !!***********\n'
                           '*****scrape_court method failed!*****\n'
                           '********!! ACTION NEEDED !!**********\n%s') % traceback.format_exc()
                    logger.critical(msg)
                finally:
                    i += 1

        logger.info("The scraper has stopped.")
