import hashlib
import mimetypes
import os
import random
import signal
import sys
import requests
import time
import traceback

from alert.lib import magic
from alert.lib.string_utils import trunc
from alert.scrapers.models import ErrorLog
from alert.scrapers.DupChecker import DupChecker
from alert.search.models import Citation, Docket
from alert.search.models import Court
from alert.search.models import Document
from juriscraper.AbstractSite import logger
from juriscraper.lib.importer import build_module_list
from juriscraper.tests import MockRequest
from alerts.models import RealTimeQueue
from scrapers.tasks import extract_doc_content, extract_by_ocr

from celery.task.sets import subtask
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from lxml import html
from optparse import make_option
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
            path = "//meta[translate(@http-equiv, 'REFSH', 'refsh') = 'refresh']/@content"
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
    Recursive function that follows meta refresh redirections if they exist.
    """
    redirected, url = test_for_meta_redirections(r)
    if redirected:
        logger.info('Following a meta redirection to: %s' % url.encode('utf-8'))
        r = follow_redirections(s.get(url), s)
    return r


def is_html(s):
    """Sniffs for stuff that distinguishes an HTML document. Tricky because we
    allow partial ones and because other formats (like WordPerfect) closely
    resemble HTML.
    """
    if any([
        '<a href=' in s[:100],
        '<table ' in s[:100],
        '<html' in s[:100],
    ]):
        html_status = True
    else:
        html_status = False
    return html_status

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
        elif is_html(content):
            extension = '.html'
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


def get_binary_content(download_url, cookies, adapter, method='GET'):
    """ Downloads the file, covering a few special cases such as invalid SSL
    certificates and empty file errors.

    :param download_url: The URL for the item you wish to download.
    :param adapter: A HTTPAdapter for use when accessing the site.
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
            mr = MockRequest(url=os.path.join(
                settings.INSTALL_ROOT,
                'alert',
                download_url)
            )
            r = mr.get()
        else:
            # Note that we do a GET even if site.method is POST. This is
            # deliberate.
            s = requests.session()
            s.mount('https://', adapter)
            headers = {'User-Agent': 'CourtListener'}

            r = s.get(download_url,
                      verify=False,  # WA has a certificate we don't understand
                      headers=headers,
                      cookies=cookies)

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
    option_list = BaseCommand.option_list + (
        make_option('-d',
                    '--daemon',
                    action='store_true',
                    dest='daemonmode',
                    help=('Use this flag to turn on daemon mode, in which all '
                          'courts requested will be scraped in turn, '
                          'nonstop.')),
        make_option('-r',
                    '--rate',
                    dest='rate',
                    metavar='RATE',
                    help=('The length of time in minutes it takes to crawl '
                          'all requested courts. Particularly useful if it is '
                          'desired to quickly scrape over all courts. Default '
                          'is 30 minutes.')),
        make_option('-c',
                    '--courts',
                    dest='court_id',
                    metavar="COURTID",
                    help=('The court(s) to scrape and extract. This should be '
                          'in the form of a python module or package import '
                          'from the Juriscraper library, e.g. '
                          '"juriscraper.opinions.united_states.federal.ca1" '
                          'or simply "opinions" to do all opinions.')),
        make_option('-f',
                    '--fullcrawl',
                    dest='full_crawl',
                    action='store_true',
                    help="Disable duplicate aborting."),
    )
    args = "-c COURTID [-d] [-f] [-r RATE]"
    help = 'Runs the Juriscraper toolkit against one or many jurisdictions.'

    def associate_meta_data_to_objects(self, site, i, court, sha1_hash):
        """Takes the meta data from the scraper and assocites it with objects.

        Returns the created objects.
        """
        cite = Citation(case_name=site.case_names[i])
        if site.docket_numbers:
            cite.docket_number = site.docket_numbers[i]
        if site.neutral_citations:
            cite.neutral_cite = site.neutral_citations[i]
        if site.west_citations:
            cite.federal_cite_one = site.west_citations[i]
        if site.west_state_citations:
            cite.west_state_cite = site.west_state_citations[i]

        docket = Docket(
            case_name=site.case_names[i],
            court=court,
        )

        doc = Document(
            source='C',
            sha1=sha1_hash,
            date_filed=site.case_dates[i],
            download_url=site.download_urls[i],
            precedential_status=site.precedential_statuses[i]
        )
        if site.judges:
            doc.judges = site.judges[i]
        if site.nature_of_suit:
            doc.nature_of_suit = site.nature_of_suit[i]

        return cite, docket, doc

    @staticmethod
    def save_everything(cite, docket, doc, index=False):
        """Saves all the sub items and associates them as appropriate.
        """
        cite.save(index=index)
        doc.citation = cite
        docket.save()
        doc.docket = docket
        doc.save(index=index)
        RealTimeQueue.objects.create(
            item_type='o',
            item_pk=doc.pk,
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

                current_date = site.case_dates[i]
                try:
                    next_date = site.case_dates[i + 1]
                except IndexError:
                    next_date = None

                # Make a hash of the data
                if isinstance(content, unicode):
                    sha1_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
                else:
                    sha1_hash = hashlib.sha1(content).hexdigest()
                if court_str == 'nev' and \
                                site.precedential_statuses[i] == 'Unpublished':
                    # Nevada's non-precedential cases have different SHA1
                    # sums every time.
                    onwards = dup_checker.should_we_continue_break_or_carry_on(
                        Document,
                        current_date,
                        next_date,
                        lookup_value=site.download_urls[i],
                        lookup_by='download_url'
                    )
                else:
                    onwards = dup_checker.should_we_continue_break_or_carry_on(
                        Document,
                        current_date,
                        next_date,
                        lookup_value=sha1_hash,
                        lookup_by='sha1'
                    )

                if onwards == 'CONTINUE':
                    # It's a duplicate, but we haven't hit any thresholds yet.
                    continue
                elif onwards == 'BREAK':
                    # It's a duplicate, and we hit a date or dup_count
                    # threshold.
                    dup_checker.update_site_hash(sha1_hash)
                    break
                elif onwards == 'CARRY_ON':
                    # Not a duplicate, carry on
                    logger.info('Adding new document found at: %s' %
                                site.download_urls[i].encode('utf-8'))
                    dup_checker.reset()

                    cite, docket, doc = self.associate_meta_data_to_objects(
                        site, i, court, sha1_hash)

                    # Make and associate the file object
                    try:
                        cf = ContentFile(content)
                        extension = get_extension(content)
                        # See bitbucket issue #215 for why this must be
                        # lower-cased.
                        file_name = trunc(site.case_names[i].lower(), 75) + \
                            extension
                        doc.local_path.save(file_name, cf, save=False)
                    except:
                        msg = ('Unable to save binary to disk. Deleted '
                               'document: % s.\n % s' %
                               (site.case_names[i], traceback.format_exc()))
                        logger.critical(msg.encode('utf-8'))
                        ErrorLog(
                            log_level='CRITICAL',
                            court=court,
                            message=msg
                        ).save()
                        download_error = True
                        continue

                    # Save everything, but don't update Solr index yet
                    self.save_everything(cite, docket, doc, index=False)
                    random_delay = random.randint(0, 3600)
                    extract_doc_content.delay(
                        doc.pk,
                        callback=subtask(extract_by_ocr),
                        citation_countdown=random_delay
                    )

                    logger.info("Successfully added doc {pk}: {name}".format(
                        pk=doc.pk,
                        name=site.case_names[i].encode('utf-8')
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

        self.verbosity = int(options.get('verbosity', 1))
        daemon_mode = options.get('daemonmode', False)

        full_crawl = options.get('full_crawl', False)

        try:
            rate = int(options['rate'])
        except (ValueError, AttributeError, TypeError):
            rate = 30

        court_id = options.get('court_id')
        if not court_id:
            raise CommandError('You must specify a court as a package or '
                               'module.')
        else:
            module_strings = build_module_list(court_id)
            if not len(module_strings):
                raise CommandError('Unable to import module or package. '
                                   'Aborting.')

            logger.info("Starting up the scraper.")
            num_courts = len(module_strings)
            wait = (rate * 60) / num_courts
            i = 0
            while i < num_courts:
                # this catches SIGTERM, so the code can be killed safely.
                if die_now:
                    logger.info("The scraper has stopped.")
                    sys.exit(1)

                package, module = module_strings[i].rsplit('.', 1)

                mod = __import__("%s.%s" % (package, module),
                                 globals(),
                                 locals(),
                                 [module])
                # noinspection PyBroadException
                try:
                    self.parse_and_scrape_site(mod, full_crawl)
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
                    if last_court_in_list and daemon_mode:
                        # Start over...
                        logger.info("All jurisdictions done. Looping back to "
                                    "the beginning.")
                        i = 0
                    else:
                        i += 1

        logger.info("The scraper has stopped.")
        sys.exit(0)
