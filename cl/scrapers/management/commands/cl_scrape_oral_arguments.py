import hashlib
import random
import traceback

from django.utils.encoding import force_bytes

from cl.alerts.models import RealTimeQueue
from cl.audio.models import Audio
from cl.lib.string_utils import trunc
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.management.commands import cl_scrape_opinions
from cl.lib.scrape_helpers import get_extension, get_binary_content
from cl.scrapers.models import ErrorLog
from cl.scrapers.tasks import process_audio_file
from cl.search.models import Court, Docket
from juriscraper.AbstractSite import logger

from datetime import date
from django.core.files.base import ContentFile


class Command(cl_scrape_opinions.Command):

    def make_objects(self, item, court, sha1_hash, content):
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
            date_argued=item['case_dates'],
            source=Docket.SCRAPER,
        )

        audio_file = Audio(
            judges=item.get('judges', ''),
            source='C',
            case_name=item['case_names'],
            case_name_short=case_name_short,
            sha1=sha1_hash,
            download_url=item['download_urls'],
            blocked=blocked,
            date_blocked=date_blocked,
        )

        error = False
        try:
            cf = ContentFile(content)
            extension = get_extension(content)
            if extension not in ['.mp3', '.wma']:
                extension = '.' + item['download_urls'].rsplit('.', 1)[1]
            # See bitbucket issue #215 for why this must be
            # lower-cased.
            file_name = trunc(item['case_names'].lower(), 75) + extension
            audio_file.file_with_date = docket.date_argued
            audio_file.local_path_original_file.save(file_name, cf, save=False)
        except:
            msg = 'Unable to save binary to disk. Deleted audio file: %s.\n ' \
                  '%s' % (item['case_names'], traceback.format_exc())
            logger.critical(msg.encode('utf-8'))
            ErrorLog(log_level='CRITICAL', court=court, message=msg).save()
            error = True

        return docket, audio_file, error

    @staticmethod
    def save_everything(items, index=False):
        docket, audio_file = items['docket'], items['audio_file']
        docket.save()
        audio_file.docket = docket
        audio_file.save(index=index)
        RealTimeQueue.objects.create(
            item_type='oa',
            item_pk=audio_file.pk,
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

                # request.content is sometimes a str, sometimes unicode, so
                # force it all to be bytes, pleasing hashlib.
                sha1_hash = hashlib.sha1(force_bytes(content)).hexdigest()
                onwards = dup_checker.press_on(
                    Audio,
                    current_date,
                    next_date,
                    lookup_value=sha1_hash,
                    lookup_by='sha1'
                )
                if dup_checker.emulate_break:
                    break

                if onwards:
                    # Not a duplicate, carry on
                    logger.info('Adding new document found at: %s' %
                                item['download_urls'].encode('utf-8'))
                    dup_checker.reset()

                    docket, audio_file, error = self.make_objects(
                        item, court, sha1_hash, content,
                    )

                    if error:
                        download_error = True
                        continue

                    self.save_everything(
                        items={
                            'docket': docket,
                            'audio_file': audio_file,
                        },
                        index=False,
                    )
                    process_audio_file.apply_async(
                        (audio_file.pk,),
                        countdown=random.randint(0, 3600)
                    )

                    logger.info(
                        "Successfully added audio file {pk}: {name}".format(
                            pk=audio_file.pk,
                            name=item['case_names'].encode('utf-8')
                        )
                    )

            # Update the hash if everything finishes properly.
            logger.info("%s: Successfully crawled oral arguments." %
                        site.court_id)
            if not download_error and not full_crawl:
                # Only update the hash if no errors occurred.
                dup_checker.update_site_hash(site.hash)
