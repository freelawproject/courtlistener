import hashlib
import mimetypes
import os
import random
import signal
import sys
import requests
import time
import traceback

from cl.alerts.models import RealTimeQueue
from cl.lib import magic
from cl.lib.string_utils import trunc
from cl.scrapers.models import ErrorLog
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.tasks import extract_doc_content, extract_by_ocr
from cl.search.models import Docket
from cl.search.models import Court
from cl.search.models import Opinion
from cl.search.models import OpinionCluster
from juriscraper.AbstractSite import logger
from juriscraper.lib.importer import build_module_list
from juriscraper.tests import MockRequest

from celery.task.sets import subtask
from datetime import date
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import make_aware, utc, now
from lxml import html
from urlparse import urljoin

# for use in catching the SIGINT (Ctrl+4)
die_now = False


def signal_handler(signal, frame):
    # Trigger this with CTRL+4
    logger.info('**************')
    logger.info('Signal caught. Finishing the current court, then exiting...')
    logger.info('**************')
    global die_now
    die_now = True


def test_for_meta_redirections(r):
    mime = magic.from_buffer(r.content, mime=True)
    extension = mimetypes.guess_extension(mime)
    if extension == '.html':
        html_tree = html.fromstring(r.text)
        try:
            path = "//meta[translate(@http-equiv, 'REFSH', 'refsh') = " \
                   "'refresh']/@content"
            attr = html_tree.xpath(path)[0]
            wait, text = attr.split(";")
            if text.lower().startswith("url="):
                url = text[4:]
                if not url.startswith('http'):
                    # Relative URL, adapt
                    url = urljoin(r.url, url)
                return True, url
        except IndexError:
            return False, None
    else:
        return False, None


def follow_redirections(r, s):
    """
    Parse and recursively follow meta refresh redirections if they exist until
    there are no more.
    """
    redirected, url = test_for_meta_redirections(r)
    if redirected:
        logger.info('Following a meta redirection to: %s' % url)
        r = follow_redirections(s.get(url), s)
    return r


def get_extension(content):
    """A handful of workarounds for getting extensions we can trust."""
    file_str = magic.from_buffer(content)
    if file_str.startswith('Composite Document File V2 Document'):
        # Workaround for issue with libmagic1==5.09-2 in Ubuntu 12.04. Fixed
        # in libmagic 5.11-2.
        mime = 'application/msword'
    elif file_str == '(Corel/WP)':
        mime = 'application/vnd.wordperfect'
    elif file_str == 'C source, ASCII text':
        mime = 'text/plain'
    else:
        # No workaround necessary
        mime = magic.from_buffer(content, mime=True)
    extension = mimetypes.guess_extension(mime)
    if extension == '.obj':
        # It could be a wpd, if it's not a PDF
        if 'PDF' in content[0:40]:
            # Does 'PDF' appear in the beginning of the content?
            extension = '.pdf'
        else:
            extension = '.wpd'
    if extension == '.wsdl':
        # It's probably an HTML file, like those from Resource.org
        extension = '.html'
    if extension == '.ksh':
        extension = '.txt'
    if extension == '.asf':
        extension = '.wma'
    return extension


def get_binary_content(download_url, cookies, method='GET'):
    """ Downloads the file, covering a few special cases such as invalid SSL
    certificates and empty file errors.

    :param download_url: The URL for the item you wish to download.
    :param cookies: Cookies that might be necessary to download the item.
    :param method: The HTTP method used to get the item, or "LOCAL" to get an
    item during testing
    :return: Two values. The first is a msg indicating any errors encountered.
    If blank, that indicates success. The second value is the response object
    containing the downloaded file.
    """
    if not download_url:
        # Occurs when a DeferredList fetcher fails.
        msg = 'NoDownloadUrlError: %s\n%s' % (download_url,
                                              traceback.format_exc())
        return msg, None
    # noinspection PyBroadException
    try:
        if method == 'LOCAL':
            url = os.path.join(
                settings.MEDIA_ROOT,
                download_url)
            mr = MockRequest(url=url)
            r = mr.get()
        else:
            # Note that we do a GET even if site.method is POST. This is
            # deliberate.
            s = requests.session()
            headers = {'User-Agent': 'CourtListener'}

            r = s.get(
                download_url,
                verify=False,  # WA has a certificate we don't understand
                headers=headers,
                cookies=cookies
            )

            # test for empty files (thank you CA1)
            if len(r.content) == 0:
                msg = 'EmptyFileError: %s\n%s' % (download_url,
                                                  traceback.format_exc())
                return msg, None

            # test for and follow meta redirects
            r = follow_redirections(r, s)

            r.raise_for_status()
    except:
        msg = 'DownloadingError: %s\n%s' % (download_url,
                                            traceback.format_exc())
        return msg, None

    # Success!
    return '', r


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
            type='combined',
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
            logger.critical(msg)
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
                    method=site.method
                )
                content = site.cleanup_content(r.content)
                if msg:
                    logger.warn(msg)
                    ErrorLog(log_level='WARNING',
                             court=court,
                             message=msg).save()
                    continue

                current_date = item['case_dates']
                try:
                    next_date = site[i + 1]['case_dates']
                except IndexError:
                    next_date = None

                # Make a hash of the data
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
                                item['download_urls'])
                    dup_checker.reset()

                    docket, opinion, cluster, error = self.make_objects(
                        item, court, sha1_hash, content)

                    if error:
                        continue

                    # Save everything, but don't update Solr index yet
                    self.save_everything(
                        items={
                            'docket': docket,
                            'opinion': opinion,
                            'cluster': cluster
                        },
                        index=False
                    )
                    random_delay = random.randint(0, 3600)
                    extract_doc_content.delay(
                        opinion.pk,
                        callback=subtask(extract_by_ocr),
                        citation_countdown=random_delay
                    )

                    logger.info("Successfully added doc {pk}: {name}".format(
                        pk=opinion.pk,
                        name=item['case_names'],
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
