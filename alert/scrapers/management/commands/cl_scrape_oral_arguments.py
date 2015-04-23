import hashlib
import random
import traceback

from alert.audio.models import Audio
from alert.lib.string_utils import trunc
from alert.scrapers.DupChecker import DupChecker
from alert.scrapers.management.commands import cl_scrape_opinions
from alert.scrapers.management.commands.cl_scrape_opinions import \
    get_binary_content, get_extension
from alert.scrapers.models import ErrorLog
from alert.search.models import Court, Docket
from alerts.models import RealTimeQueue
from scrapers.tasks import process_audio_file

from juriscraper.AbstractSite import logger

from django.core.files.base import ContentFile


class Command(cl_scrape_opinions.Command):
    @staticmethod
    def associate_meta_data_to_objects(site, i, court, sha1_hash):
        audio_file = Audio(
            source='C',
            sha1=sha1_hash,
            case_name=site.case_names[i],
            download_url=site.download_urls[i],
            processing_complete=False,
        )
        if site.judges:
            audio_file.judges = site.judges[i]
        if site.docket_numbers:
            audio_file.docket_number = site.docket_numbers[i]

        docket = Docket(
            date_argued=site.case_dates[i],
            case_name=site.case_names[i],
            court=court,
        )

        return docket, audio_file

    @staticmethod
    def save_everything(docket, audio_file):
        docket.save()
        audio_file.docket = docket
        audio_file.save(index=False)
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
            for i in range(0, len(site.case_names)):
                msg, r = get_binary_content(
                    site.download_urls[i],
                    site.cookies,
                    method=site.method
                )
                if msg:
                    logger.warn(msg)
                    ErrorLog(log_level='WARNING',
                             court=court,
                             message=msg).save()
                    continue

                current_date = site.case_dates[i]
                try:
                    next_date = site.case_dates[i + 1]
                except IndexError:
                    next_date = None

                sha1_hash = hashlib.sha1(r.content).hexdigest()
                onwards = dup_checker.should_we_continue_break_or_carry_on(
                    Audio,
                    current_date,
                    next_date,
                    lookup_value=sha1_hash,
                    lookup_by='sha1'
                )

                if onwards == 'CONTINUE':
                    # It's a duplicate, but we haven't hit any thresholds yet.
                    continue
                elif onwards == 'BREAK':
                    # It's a duplicate, and we hit a date or dup_count threshold.
                    dup_checker.update_site_hash(sha1_hash)
                    break
                elif onwards == 'CARRY_ON':
                    # Not a duplicate, carry on
                    logger.info('Adding new document found at: %s' % site.download_urls[i])
                    dup_checker.reset()

                    docket, audio_file = self.associate_meta_data_to_objects(
                        site, i, court, sha1_hash)

                    audio_file.docket = docket

                    # Make and associate the file object
                    try:
                        cf = ContentFile(r.content)
                        extension = get_extension(r.content)
                        if extension not in ['.mp3', '.wma']:
                            extension = '.' + site.download_urls[i].rsplit('.', 1)[1]
                        # See bitbucket issue #215 for why this must be
                        # lower-cased.
                        file_name = trunc(site.case_names[i].lower(), 75) + extension
                        audio_file.local_path_original_file.save(file_name, cf, save=False)
                    except:
                        msg = 'Unable to save binary to disk. Deleted document: % s.\n % s' % \
                              (site.case_names[i], traceback.format_exc())
                        logger.critical(msg)
                        ErrorLog(log_level='CRITICAL', court=court, message=msg).save()
                        download_error = True
                        continue

                    self.save_everything(docket, audio_file)
                    random_delay = random.randint(0, 3600)
                    process_audio_file.apply_async(
                        (audio_file.pk,),
                        countdown=random_delay
                    )

                    logger.info("Successfully added audio file %s: %s" % (audio_file.pk, site.case_names[i]))

            # Update the hash if everything finishes properly.
            logger.info("%s: Successfully crawled oral arguments." % site.court_id)
            if not download_error and not full_crawl:
                # Only update the hash if no errors occurred.
                dup_checker.update_site_hash(site.hash)
