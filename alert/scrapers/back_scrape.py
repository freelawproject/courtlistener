import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.scrapers.scrape_and_extract import scrape_court, signal_handler

from juriscraper.GenericSite import logger
from juriscraper.lib.importer import build_module_list

import signal
import traceback
from datetime import date
from dateutil.rrule import rrule
from dateutil.rrule import DAILY
from optparse import OptionParser
from requests import HTTPError

# for use in catching the SIGINT (Ctrl+4)
die_now = False


def generate_sites(court_module):
    # opinions.united_states.federal.ca9u --> ca9
    court_str = court_module.__name__.split('.')[-1].split('_')[0]
    logger.info("Using court_str: \"%s\"" % court_str)
    if court_str == 'cafc':
        # This is a generator that cranks out a site object when called.
        # Useful because doing it this way won't load each site object
        # with HTML until it's called.
        for i in range(0, 185):
            try:
                site = court_module.Site()
                site._download_backwards(i)
                yield site
            except HTTPError, e:
                logger.warn("Failed to download page.")
                continue

    elif 'haw' in court_str:
        for i in range(2010, 2013):
            try:
                site = court_module.Site()
                site._download_backwards(i)
                yield site
            except HTTPError, e:
                logger.warn("Failed to download page")
                continue

    elif court_str == 'mich':
        for i in range(0, 868):
            try:
                site = court_module.Site()
                site._download_backwards(i)
                yield site
            except HTTPError, e:
                logger.warn("Failed to download page")
                continue

    elif court_str == 'miss':
        for i in range(1990, 2012):
            try:
                site = court_module.Site()
                site._download_backwards(i)
                yield site
            except HTTPError, e:
                logger.warn("Failed to download page")
                continue

    elif court_str == 'mont':
        for i in range(1972, 2014):
            try:
                site = court_module.Site()
                site._download_backwards(i)
                yield site
            except HTTPError, e:
                logger.warn("Failed to download page")
                continue

    elif court_str in ['nmctapp', 'nm']:
        for i in range(2009, 2013):
            try:
                site = court_module.Site()
                site._download_backwards(i)
                yield site
            except HTTPError, e:
                logger.warn("Failed to download page")
                continue

    elif court_str == 'tex':
        start = date(1997, 10, 2)
        end = date(2013, 6, 5)
        for i in rrule(DAILY, dtstart=start, until=end):
            try:
                site = court_module.Site()
                site._download_backwards(i)
                yield site
            except HTTPError, e:
                logger.warn("Failed to download page")
                continue


def back_scrape(mod):
    global die_now
    for site in generate_sites(mod):
        if die_now == True:
            logger.info("The scraper has stopped.")
            sys.exit(1)
        site.parse()
        scrape_court(site, full_crawl=True)


def main():
    global die_now

    # this line is used for handling SIGKILL, so things can die safely.
    signal.signal(signal.SIGTERM, signal_handler)

    usage = 'usage: %prog -c COURTID'
    parser = OptionParser(usage)
    parser.add_option('-c', '--courts', dest='court_id', metavar="COURTID",
                      help=('The court(s) to scrape and extract. This should be in '
                            'the form of a python module or package import '
                            'from the Juriscraper library, e.g. '
                            '"juriscraper.opinions.united_states.federal.ca1" or '
                            'simply "opinions" to do all opinions.'))
    (options, args) = parser.parse_args()

    court_id = options.court_id

    if not court_id:
        parser.error('You must specify a court as a package or module.')
    else:
        module_strings = build_module_list(court_id)
        if len(module_strings) == 0:
            parser.error('Unable to import module or package. Aborting.')

        logger.info("Starting up the scraper.")
        num_courts = len(module_strings)
        i = 0
        while i < num_courts:
            # this catches SIGINT, so the code can be killed safely.
            if die_now == True:
                logger.info("The scraper has stopped.")
                sys.exit(1)

            package, module = module_strings[i].rsplit('.', 1)

            mod = __import__("%s.%s" % (package, module),
                             globals(),
                             locals(),
                             [module])

            try:
                back_scrape(mod)
            except:
                msg = ('********!! CRAWLER DOWN !!***********\n'
                       '*****scrape_court method failed!*****\n'
                       '********!! ACTION NEEDED !!**********\n%s') % \
                       traceback.format_exc()
                logger.critical(msg)

                # opinions.united_states.federal.ca9_u --> ca9
                court_str = mod.Site.__module__.split('.')[-1].split('_')[0]
                i += 1
                continue

            i += 1

    logger.info("The scraper has stopped.")

if __name__ == '__main__':
    main()
