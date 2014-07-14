from alert.lib import magic
from alert.lib.string_utils import trunc
from alert.scrapers.models import ErrorLog
from alert.scrapers.DupChecker import DupChecker
from alert.search.models import Citation
from alert.search.models import Court
from alert.search.models import Document

from celery.task.sets import subtask
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from juriscraper.AbstractSite import logger
from juriscraper.lib.importer import build_module_list
from scrapers.tasks import extract_doc_content, extract_by_ocr
from requests.exceptions import SSLError
from urlparse import urljoin

import hashlib
import mimetypes
import signal
import sys
import requests
import time
import traceback
from lxml import html
from optparse import make_option

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
            attr = html_tree.xpath("//meta[translate(@http-equiv, 'REFSH', 'refsh') = 'refresh']/@content")[0]
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
        logger.info('Following a meta redirection to: %s' % url)
        r = follow_redirections(s.get(url), s)
    return r


def get_extension(content):
    """A handful of workarounds for getting extensions we can trust."""
    file_str = magic.from_buffer(content)
    if file_str.startswith('Composite Document File V2 Document'):
        # Workaround for issue with libmagic1==5.09-2 in Ubuntu 12.04. Fixed in libmagic 5.11-2.
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
    return extension


def convert_from_selenium_style_cookies(cookies):
    """Selenium uses a different format for cookies than does requests. This converts from a Selenium dict to a
    requests dict.
    """
    requests_cookies = {}
    for cookie in cookies:
        requests_cookies[cookie['name']] = cookie['value']
    return requests_cookies


def get_binary_content(download_url, cookies):
    if not download_url:
        # Occurs when a DeferredList fetcher fails.
        msg = 'NoDownloadUrlError: %s\n%s' % (download_url, traceback.format_exc())
        return msg, None
    # noinspection PyBroadException
    try:
        s = requests.session()
        headers = {'User-Agent': 'CourtListener'}
        cookies = convert_from_selenium_style_cookies(cookies)
        logger.info("Using cookies: %s" % cookies)
        try:
            r = s.get(download_url,
                      headers=headers,
                      cookies=cookies)
        except SSLError:
            # Washington has a certificate we don't understand.
            r = s.get(download_url,
                      verify=False,
                      headers=headers,
                      cookies=cookies)

        # test for empty files (thank you CA1)
        if len(r.content) == 0:
            msg = 'EmptyFileError: %s\n%s' % (download_url, traceback.format_exc())
            return msg, r

        # test for and follow meta redirects
        r = follow_redirections(r, s)
    except:
        msg = 'DownloadingError: %s\n%s' % (download_url, traceback.format_exc())
        return msg, r

    # Success!
    return '', r


def scrape_court(site, full_crawl=False):
    download_error = False
    # Get the court object early for logging
    # opinions.united_states.federal.ca9_u --> ca9
    court_str = site.court_id.split('.')[-1].split('_')[0]
    court = Court.objects.get(pk=court_str)

    dup_checker = DupChecker(court, full_crawl=full_crawl)
    abort = dup_checker.abort_by_url_hash(site.url, site.hash)
    if not abort:
        for i in range(0, len(site.case_names)):
            msg, r = get_binary_content(site.download_urls[i], site._get_cookies())
            clean_content = site._cleanup_content(r.content)
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

            # Make a hash of the data. Need to convert unicode to binary before hashing.
            if type(clean_content) == unicode:
                hash_content = clean_content.encode('utf-8')
            else:
                hash_content = clean_content
            sha1_hash = hashlib.sha1(hash_content).hexdigest()
            if court_str == 'nev' and site.precedential_statuses[i] == 'Unpublished':
                # Nevada's non-precedential cases have different SHA1 sums every time.
                onwards = dup_checker.should_we_continue_break_or_carry_on(
                    current_date,
                    next_date,
                    lookup_value=site.download_urls[i],
                    lookup_by='download_url'
                )
            else:
                onwards = dup_checker.should_we_continue_break_or_carry_on(
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

                # Make a citation
                cite = Citation(case_name=site.case_names[i])
                if site.docket_numbers:
                    cite.docket_number = site.docket_numbers[i]
                if site.neutral_citations:
                    cite.neutral_cite = site.neutral_citations[i]
                if site.west_citations:
                    cite.federal_cite_one = site.west_citations[i]
                if site.west_state_citations:
                    cite.west_state_cite = site.west_state_citations[i]

                # Make the document object
                doc = Document(source='C',
                               sha1=sha1_hash,
                               date_filed=site.case_dates[i],
                               court=court,
                               download_url=site.download_urls[i],
                               precedential_status=site.precedential_statuses[i])

                # Make and associate the file object
                try:
                    cf = ContentFile(clean_content)
                    extension = get_extension(r.content)
                    # See issue #215 for why this must be lower-cased.
                    file_name = trunc(site.case_names[i].lower(), 75) + extension
                    doc.local_path.save(file_name, cf, save=False)
                except:
                    msg = 'Unable to save binary to disk. Deleted document: % s.\n % s' % \
                          (cite.case_name, traceback.format_exc())
                    logger.critical(msg)
                    ErrorLog(log_level='CRITICAL', court=court, message=msg).save()
                    download_error = True
                    continue

                if site.judges:
                    doc.judges = site.judges[i]
                if site.nature_of_suit:
                    doc.nature_of_suit = site.nature_of_suit[i]

                # Save everything, but don't update Solr index yet
                cite.save(index=False)
                doc.citation = cite
                doc.save(index=False)

                # Extract the contents asynchronously.
                extract_doc_content(doc.pk, callback=subtask(extract_by_ocr))

                logger.info("Successfully added doc %s: %s" % (doc.pk, site.case_names[i]))

        # Update the hash if everything finishes properly.
        logger.info("%s: Successfully crawled." % site.court_id)
        if not download_error and not full_crawl:
            # Only update the hash if no errors occurred.
            dup_checker.update_site_hash(site.hash)


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('-d',
                    '--daemon',
                    action='store_true',
                    dest='daemonmode',
                    help=('Use this flag to turn on daemon mode, in which all courts requested will be scraped in turn, '
                          'nonstop.')),
        make_option('-r',
                    '--rate',
                    dest='rate',
                    metavar='RATE',
                    help=('The length of time in minutes it takes to crawl all requested courts. Particularly useful '
                          'if it is desired to quickly scrape over all courts. Default is 30 minutes.')),
        make_option('-c',
                    '--courts',
                    dest='court_id',
                    metavar="COURTID",
                    help=('The court(s) to scrape and extract. This should be in the form of a python module or '
                          'package import from the Juriscraper library, e.g. '
                          '"juriscraper.opinions.united_states.federal.ca1" or simply "opinions" to do all opinions.')),
        make_option('-f',
                    '--fullcrawl',
                    dest='full_crawl',
                    action='store_true',
                    help="Disable duplicate aborting."),
    )
    args = "-c COURTID [-d] [-r RATE]"
    help = 'Runs the Juriscraper toolkit against one or many courts.'

    def handle(self, *args, **options):
        global die_now

        # this line is used for handling SIGTERM (CTRL+4), so things can die safely
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
            raise CommandError('You must specify a court as a package or module.')
        else:
            module_strings = build_module_list(court_id)
            if not len(module_strings):
                raise CommandError('Unable to import module or package. Aborting.')

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
                    site = mod.Site().parse()
                    scrape_court(site, full_crawl)
                except Exception, e:
                    # noinspection PyBroadException
                    try:
                        msg = ('********!! CRAWLER DOWN !!***********\n'
                               '*****scrape_court method failed!*****\n'
                               '********!! ACTION NEEDED !!**********\n%s') % traceback.format_exc()
                        logger.critical(msg)

                        # opinions.united_states.federal.ca9_u --> ca9
                        court_str = mod.Site.__module__.split('.')[-1].split('_')[0]
                        court = Court.objects.get(pk=court_str)
                        ErrorLog(log_level='CRITICAL', court=court, message=msg).save()
                    except Exception, e:
                        # This is very important. Without this, an exception above will crash the caller.
                        pass
                finally:
                    time.sleep(wait)
                    last_court_in_list = (i == (num_courts - 1))
                    if last_court_in_list and daemon_mode:
                        # Start over...
                        logger.info("All jurisdictions done. Looping back to the beginning.")
                        i = 0
                    else:
                        i += 1

        logger.info("The scraper has stopped.")
        sys.exit(0)
