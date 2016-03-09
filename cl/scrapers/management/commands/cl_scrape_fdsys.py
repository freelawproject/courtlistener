import hashlib
import logging
import random
import signal
import sys
import time
import traceback
from datetime import date

from celery.task.sets import subtask
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from juriscraper.fdsys.FDSysSite import FDSysSite
from juriscraper.lib.importer import build_module_list
from juriscraper.lib.string_utils import CaseNameTweaker

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
            default=30,
            help=('The length of time in minutes it takes to crawl '
                  'all requested courts. Particularly useful if it is '
                  'desired to quickly scrape over all courts. Default '
                  'is 30 minutes.'),
        )

    def handle(self, *args, **options):
        global die_now

        # this line is used for handling SIGTERM (CTRL+4), so things can die
        # safely
        signal.signal(signal.SIGTERM, signal_handler)

        logging.info("Starting up the fdsys scraper.")
        self.cnt = CaseNameTweaker()
        # num_courts = len(module_strings)
        wait = (options['rate'] * 60)

        i = 0
        fdsys = FDSysSite().parse()
        mods_num = len(fdsys)

        while i < mods_num:
            if die_now:
                logging.info("The fdsys scraper has stopped.")
                sys.exit(1)

            # noinspection PyBroadException

            try:
                # todo
                self.scrape_mods_file(fdsys, i)

            except Exception, e:
                # noinspection PyBroadException
                try:
                    msg = ('********!! FDSYS CRAWLER DOWN !!***********\n'
                           '*****scrape_mods_file method failed!*****\n'
                           '********!! ACTION NEEDED !!**********\n%s' %
                           traceback.format_exc())
                    logging.critical(msg)
                except Exception, e:
                    # This is very important. Without this, an exception
                    # above will crash the caller.
                    pass
            finally:
                time.sleep(wait)
                last_mods_in_list = (i == (mods_num - 1))
                if last_mods_in_list and options['daemon']:
                    # Start over...
                    logging.info('All done. Looping back to'
                                 'the beginning because daemon mode is enabled.')
                    i = 0
                else:
                    i += 1

        logging.info("The fdsys scraper has stopped.")
        sys.exit(0)

    def scrape_mods_file(self, fdsys, index, full_crawl=True):
        download_error = False
        mods_data = fdsys[index]
        court_str = mods_data.court_id
        court = Court.objects.get(pk=court_str)

        dup_checker = DupChecker(court, full_crawl=full_crawl)
        abort = dup_checker.abort_by_url_hash(mods_data.url, mods_data.hash)
        if not abort:
            msg, r = get_binary_content(
                mods_data.download_url,
                mods_data.cookies,
                mods_data._get_adapter_instance(),
                method=mods_data.method
            )
            if msg:
                logging.warn(msg)
                ErrorLog(log_level='WARNING',
                         court=court,
                         message=msg).save()
            else:
                sha1_hash = hashlib.sha1(r.content).hexdigest()

                lookup_params = {
                    'lookup_value': sha1_hash,
                    'lookup_by': 'sha1'
                }

                onwards = dup_checker.press_on(Opinion, None, None, **lookup_params)
                if onwards:
                    # Not a duplicate, carry on
                    logging.info('Adding new document found at: %s' %
                                mods_data.download_url.encode('utf-8'))
                    dup_checker.reset()

                    docket, opinion, cluster, error = self.make_objects(
                        mods_data, court, sha1_hash, r.content
                    )

                    if error:
                        download_error = True
                    else:

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

                        logging.info("Successfully added doc {pk}: {name}".format(
                            pk=opinion.pk,
                            name=mods_data.case_name.encode('utf-8'),
                        ))

                    # Update the hash if everything finishes properly.
                    logging.info("%s: Successfully crawled opinions." % mods_data.court_id)
            if not download_error:
                # Only update the hash if no errors occurred.
                dup_checker.update_site_hash(mods_data.hash)

    def make_objects(self, item, court, sha1_hash, content):
        """Takes the meta data from the scraper and associates it with objects.

        Returns the created objects.
        :param content: str with html page
        :param sha1_hash: str with sha1_hash
        :param court: Court:
        :param item: juriscraper.fdsys.FDSysSite.FDSysModsContent
        """
        # todo this isn't done

        blocked = item['blocked_statuses']
        if blocked is not None:
            date_blocked = date.today()
        else:
            date_blocked = None

        case_name_short = (item.get('case_name_shorts') or
                           self.cnt.make_case_name_short(item['case_names']))
        docket = Docket(
            docket_number=item.get('docket_numbers', ''),
            case_name=item['case_names'],
            case_name_short=case_name_short,
            court=court,
            blocked=blocked,
            date_blocked=date_blocked,
        )

        cluster = OpinionCluster(
            judges=item.get('judges', ''),
            date_filed=item['case_dates'],
            case_name=item['case_names'],
            case_name_short=case_name_short,
            source='C',
            precedential_status=item['precedential_statuses'],
            nature_of_suit=item.get('nature_of_suit', ''),
            blocked=blocked,
            date_blocked=date_blocked,
            federal_cite_one=item.get('west_citations', ''),
            state_citejuriscraper_one=item.get('west_state_citations', ''),
            neutral_cite=item.get('neutral_citations', ''),
        )
        opinion = Opinion(
            type='010combined',
            sha1=sha1_hash,
            download_url=item['download_urls'],
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
            logging.critical(msg.encode('utf-8'))
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
