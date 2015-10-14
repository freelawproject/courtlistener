import hashlib
import random
import signal
import sys
import time
import traceback
from datetime import date

from celery.task.sets import subtask
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import now
from juriscraper.AbstractSite import logger
from juriscraper.lib.importer import build_module_list

from cl.alerts.models import RealTimeQueue
from cl.lib.scrape_helpers import (
    get_extension, get_binary_content, signal_handler
)
from cl.lib.string_utils import trunc
from cl.scrapers.models import ErrorLog
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.tasks import extract_doc_content, extract_by_ocr
from cl.search.models import Docket
from cl.search.models import Court
from cl.search.models import Opinion
from cl.search.models import OpinionCluster



# for use in catching the SIGINT (Ctrl+4)
die_now = False


class Command(BaseCommand):
    help = 'Runs the Juriscraper toolkit against one or many jurisdictions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--daemon',
            action='store_true',
            default=False,
            help=('Use this flag to turn on daemon mode, in which all '
                  'courts requested will be scraped in turn, '
                  'nonstop, in a loop.'),
        )
        parser.add_argument(
            '--rate',
            type=int,
            required=True,
            default=30,
            help=('The length of time in minutes it takes to crawl '
                  'all requested courts. Particularly useful if it is '
                  'desired to quickly scrape over all courts. Default '
                  'is 30 minutes.'),
        )
        parser.add_argument(
            '--courts',
            type=str,
            dest='court_id',
            metavar="COURTID",
            required=True,
            help=('The court(s) to scrape and extract. This should be '
                  'in the form of a python module or package import '
                  'from the Juriscraper library, e.g. '
                  '"juriscraper.opinions.united_states.federal.ca1" '
                  'or simply "opinions" to do all opinions.'),
        )
        parser.add_argument(
            '--fullcrawl',
            dest='full_crawl',
            action='store_true',
            default=False,
            help="Disable duplicate aborting.",
        )

    @staticmethod
    def make_objects(item, court, sha1_hash, content):
        """Takes the meta data from the scraper and associates it with objects.

        Returns the created objects.
        """
        blocked = item['blocked_statuses']
        if blocked is not None:
            date_blocked = date.today()
        else:
            date_blocked = None

        docket = Docket(
            docket_number=item.get('docket_numbers', ''),
            case_name=item['case_names'],
            case_name_short=item['case_name_shorts'],
            court=court,
            blocked=blocked,
            date_blocked=date_blocked,
            # TODO remove these lines after the DB migration
            date_created=now(),
            date_modified=now(),
        )

        cluster = OpinionCluster(
            judges=item.get('judges', ''),
            date_filed=item['case_dates'],
            case_name=item['case_names'],
            case_name_short=item['case_name_shorts'],
            source='C',
            precedential_status=item['precedential_statuses'],
            nature_of_suit=item.get('nature_of_suit', ''),
            blocked=blocked,
            date_blocked=date_blocked,
            federal_cite_one=item.get('west_citations', ''),
            state_cite_one=item.get('west_state_citations', ''),
            neutral_cite=item.get('neutral_citations', ''),
            # TODO remove these lines after the DB migration
            date_created=now(),
            date_modified=now(),
        )
        opinion = Opinion(
            type='010combined',
            sha1=sha1_hash,
            download_url=item['download_urls'],
            # TODO remove these lines after the DB migration
            date_created=now(),
            date_modified=now(),
        )

        error = False
        try:
            cf = ContentFile(content)
            extension = get_extension(content)
            file_name = trunc(item['case_names'].lower(), 75) + extension
            opinion.file_with_date = cluster.date_filed
            opinion.local_path.save(file_name, cf, save=False)
        except:
            msg = ('Unable to save binary to disk. Deleted '
                   'item: %s.\n %s' %
                   (item['case_names'], traceback.format_exc()))
            logger.critical(msg.encode('utf-8'))
            ErrorLog(log_level='CRITICAL', court=court, message=msg).save()
            error = True

        return docket, opinion, cluster, error

    @staticmethod
    def save_everything(items, index=False):
        """Saves all the sub items and associates them as appropriate.
        """
        docket, cluster, opinion = items['docket'], items['cluster'], items['opinion']
        docket.save()
        cluster.docket = docket
        cluster.save(index=False)  # Index only when the opinion is associated.
        opinion.cluster = cluster
        opinion.save(index=index)
        RealTimeQueue.objects.create(
            item_type='o',
            item_pk=opinion.pk,
        )

    def scrape_court(self, site, full_crawl=False):
        download_error = False
        # Get the court object early for logging
        # opinions.united_states.federal.ca9_u --> ca9
        court_str = site.court_id.split('.')[-1].split('_')[0]
        court = Court.objects.get(pk=court_str)

        dup_checker = DupChecker(court, full_crawl=full_crawl)
        abort = dup_checker.abort_by_url_hash(site.url, site.hash)
        if not abort:
            if site.cookies:
                logger.info("Using cookies: %s" % site.cookies)
            for i, item in enumerate(site):
                msg, r = get_binary_content(
                    item['download_urls'],
                    site.cookies,
                    site._get_adapter_instance(),
                    method=site.method
                )
                if msg:
                    logger.warn(msg)
                    ErrorLog(log_level='WARNING',
                             court=court,
                             message=msg).save()
                    continue

                content = site.cleanup_content(r.content)

                current_date = item['case_dates']
                try:
                    next_date = site[i + 1]['case_dates']
                except IndexError:
                    next_date = None

                sha1_hash = hashlib.sha1(content).hexdigest()
                if court_str == 'nev' and \
                                item['precedential_statuses'] == 'Unpublished':
                    # Nevada's non-precedential cases have different SHA1
                    # sums every time.
                    lookup_params = {'lookup_value': item['download_urls'],
                                     'lookup_by': 'download_url'}
                else:
                    lookup_params = {'lookup_value': sha1_hash,
                                     'lookup_by': 'sha1'}

                onwards = dup_checker.press_on(Opinion, current_date, next_date,
                                               **lookup_params)
                if onwards:
                    # Not a duplicate, carry on
                    logger.info('Adding new document found at: %s' %
                                item['download_urls'].encode('utf-8'))
                    dup_checker.reset()

                    docket, opinion, cluster, error = self.make_objects(
                        item, court, sha1_hash, content
                    )

                    if error:
                        download_error = True
                        continue

                    self.save_everything(
                        items={
                            'docket': docket,
                            'opinion': opinion,
                            'cluster': cluster
                        },
                        index=False
                    )
                    extract_doc_content.delay(
                        opinion.pk,
                        callback=subtask(extract_by_ocr),
                        citation_countdown=random.randint(0, 3600)
                    )

                    logger.info("Successfully added doc {pk}: {name}".format(
                        pk=opinion.pk,
                        name=item['case_names'].encode('utf-8'),
                    ))

            # Update the hash if everything finishes properly.
            logger.info("%s: Successfully crawled opinions." % site.court_id)
            if not download_error and not full_crawl:
                # Only update the hash if no errors occurred.
                dup_checker.update_site_hash(site.hash)

    def parse_and_scrape_site(self, mod, full_crawl):
        site = mod.Site().parse()
        self.scrape_court(site, full_crawl)

    def handle(self, *args, **options):
        global die_now

        # this line is used for handling SIGTERM (CTRL+4), so things can die
        # safely
        signal.signal(signal.SIGTERM, signal_handler)

        module_strings = build_module_list(options['court_id'])
        if not len(module_strings):
            raise CommandError('Unable to import module or package. Aborting.')

        logger.info("Starting up the scraper.")
        num_courts = len(module_strings)
        wait = (options['rate'] * 60) / num_courts
        i = 0
        while i < num_courts:
            # this catches SIGTERM, so the code can be killed safely.
            if die_now:
                logger.info("The scraper has stopped.")
                sys.exit(1)

            package, module = module_strings[i].rsplit('.', 1)

            mod = __import__(
                "%s.%s" % (package, module),
                globals(),
                locals(),
                [module]
            )
            # noinspection PyBroadException
            try:
                self.parse_and_scrape_site(mod, options['full_crawl'])
            except Exception, e:
                # noinspection PyBroadException
                try:
                    msg = ('********!! CRAWLER DOWN !!***********\n'
                           '*****scrape_court method failed!*****\n'
                           '********!! ACTION NEEDED !!**********\n%s' %
                           traceback.format_exc())
                    logger.critical(msg)

                    # opinions.united_states.federal.ca9_u --> ca9
                    court_str = mod.Site.__module__.split('.')[-1].split('_')[0]
                    court = Court.objects.get(pk=court_str)
                    ErrorLog(
                        log_level='CRITICAL',
                        court=court,
                        message=msg
                    ).save()
                except Exception, e:
                    # This is very important. Without this, an exception
                    # above will crash the caller.
                    pass
            finally:
                time.sleep(wait)
                last_court_in_list = (i == (num_courts - 1))
                if last_court_in_list and options['daemon']:
                    # Start over...
                    logger.info("All jurisdictions done. Looping back to "
                                "the beginning because daemon mode is enabled.")
                    i = 0
                else:
                    i += 1

        logger.info("The scraper has stopped.")
        sys.exit(0)
