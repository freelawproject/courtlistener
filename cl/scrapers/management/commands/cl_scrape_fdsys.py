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
from cl.search.models import Docket, RECAPDocument, DocketEntry, CaseParties
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

        logging.warning("Starting up the fdsys scraper.")
        self.cnt = CaseNameTweaker()
        # num_courts = len(module_strings)
        # wait = (options['rate'] * 60)
        wait = 2

        i = 0
        fdsys = FDSysSite().parse()
        mods_num = len(fdsys)
        logging.warning('Found {} documents'.format(mods_num))
        while i < mods_num:
            if die_now:
                logging.warning("The fdsys scraper has stopped.")
                sys.exit(1)

            # noinspection PyBroadException

            try:
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
                    logging.warning('All done. Looping back to'
                                 'the beginning because daemon mode is enabled.')
                    i = 0
                else:
                    i += 1

        logging.warning("The fdsys scraper has stopped.")
        sys.exit(0)

    def scrape_mods_file(self, fdsys, index, full_crawl=True):
        logging.warning([fdsys, index])
        download_error = False
        mods_data = fdsys[index]
        court_str = mods_data.court_id

        logging.warning([fdsys, index, mods_data, court_str])
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
                lookup_params = {
                    'lookup_value': mods_data.fdsys_id,
                    'lookup_by': 'fdsys_case_id'
                }

                onwards = dup_checker.press_on(Docket, None, None, **lookup_params)
                if onwards:
                    # Not a duplicate, carry on
                    logging.warning('Adding new document found at: %s' %
                                 mods_data.download_url.encode('utf-8'))
                    dup_checker.reset()

                    docket, error = self.make_objects(
                        mods_data, court, r.content, dup_checker
                    )

                    if error:
                        download_error = True
                    else:
                        logging.warning("Successfully added doc {pk}: {name}".format(
                            pk=docket.pk,
                            name=mods_data.case_name.encode('utf-8'),
                        ))

                        # Update the hash if everything finishes properly.
                        logging.warning("%s: Successfully crawled opinions." % mods_data.court_id)
            if not download_error:
                # Only update the hash if no errors occurred.
                dup_checker.update_site_hash(mods_data.hash)

    def make_objects(self, item, court, content, dup_checker):
        """Takes the meta data from the scraper and associates it with objects.

        Returns the created objects.
        :param content: str with html page
        :param court: Court:
        :param item: juriscraper.fdsys.FDSysSite.FDSysModsContent
        """
        # removed blocked_statuses
        blocked = False
        date_blocked = None
        error = False

        case_name_short = self.cnt.make_case_name_short(item.case_name)

        docket = Docket(
            docket_number=item.docket_number,
            case_name=item.case_name,
            case_name_short=case_name_short,
            fdsys_case_id=item.fdsys_id,
            court=court,
            blocked=blocked,
            date_blocked=date_blocked,
            filepath_ia=item.download_url,
            source=Docket.RECAP
        )

        try:
            logging.warning('Saving the content for docket: {}'.format(docket.docket_number))
            cf = ContentFile(content)
            extension = get_extension(content)
            file_name = trunc(item.case_name.lower(), 75) + extension
            docket.filepath_local.save(file_name, cf, save=True)
            docket.save()
            logging.warning('===============SAVED++++++++++++++')
        except:
            msg = ('Unable to save binary to disk. Deleted '
                   'item: %s.\n %s' %
                   (item.case_name, traceback.format_exc()))
            logging.warning(msg.encode('utf-8'))
            ErrorLog(log_level='CRITICAL', court=court, message=msg).save()
            error = True
            return docket, error

        # adding the parties
        for parties in item.parties:

            case_parties = CaseParties(
                docket=docket,
                first_name=parties['name_first'],
                last_name=parties['name_last'],
                middle_name=parties['name_middle'],
                suffix_name=parties['name_suffix'],
                role=parties['role']
            )
            logging.warning('Saving Parties {}'.format(case_parties.first_name))
            case_parties.save()

        # adding the documents
        for document in item.documents:
            docket_entry = DocketEntry(
                docket=docket,
                date_filed=document['date_filed'],
                description=document['description'],
                entry_number=999  # todo not sure if this is the best solution, but this is a scraper for fdsys not pacer
            )
            logging.warning('Saving docket entry {}'.format(docket_entry.date_filed))
            docket_entry.save()

            recap_document = RECAPDocument(
                docket_entry=docket_entry,
                document_type=RECAPDocument.PACER_DOCUMENT,
                filepath_ia=document['download_url'],
                document_number=999  # todo not sure if this is the best solution, but this is a scraper for fdsys not pacer
            )

            try:
                logging.warning('Getting the binary data of a recap document {}'.format(recap_document.filepath_ia))

                msg, r = get_binary_content(
                    document['download_url'],
                    {},
                    item._get_adapter_instance(),
                    method=item.method
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

                    onwards = dup_checker.press_on(RECAPDocument, None, None, **lookup_params)
                    if onwards:
                        # Not a duplicate, carry on
                        logging.warning('Adding new document found at: %s' %
                                     document['download_url'].encode('utf-8'))
                        dup_checker.reset()
                        cf = ContentFile(r.content)
                        extension = get_extension(r.content)
                        file_name = trunc(item.case_name.lower(), 75) + extension
                        recap_document.filepath_local.save(file_name, cf, save=True)
                        logging.warning('Saving recap document {}'.format(recap_document.filepath_local))

                        recap_document.save()
            except:
                msg = ('Unable to save binary to disk. Deleted '
                       'item: %s.\n %s' %
                       (item.case_name, traceback.format_exc()))
                logging.warning(msg.encode('utf-8'))
                ErrorLog(log_level='CRITICAL', court=court, message=msg).save()
                error = True
                return docket, error

        return docket, error
