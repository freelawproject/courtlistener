import mimetypes
import os
import traceback
from urlparse import urljoin

import requests
from celery.canvas import group
from django.conf import settings
from juriscraper.AbstractSite import logger
from juriscraper.lib.test_utils import MockRequest
from lxml import html

from cl.lib import magic
from cl.scrapers.tasks import extract_recap_pdf
from cl.search.models import RECAPDocument


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
        logger.info('Following a meta redirection to: %s' % url.encode('utf-8'))
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


def get_binary_content(download_url, cookies, adapter, method='GET'):
    """ Downloads the file, covering a few special cases such as invalid SSL
    certificates and empty file errors.

    :param download_url: The URL for the item you wish to download.
    :param cookies: Cookies that might be necessary to download the item.
    :param adapter: An HTTPAdapter for use when getting content.
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
            s.mount('https://', adapter)
            headers = {'User-Agent': 'CourtListener'}

            r = s.get(
                download_url,
                verify=False,  # WA has a certificate we don't understand
                headers=headers,
                cookies=cookies,
                timeout=300,
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


def signal_handler(signal, frame):
    # Trigger this with CTRL+4
    logger.info('**************')
    logger.info('Signal caught. Finishing the current court, then exiting...')
    logger.info('**************')
    global die_now
    die_now = True


def extract_recap_documents(docs, skip_ocr=False, order_by=None, queue=None,
                            queue_length=100):
    """Loop over RECAPDocuments and extract their contents. Use OCR if requested.

    :param docs: A queryset containing the RECAPDocuments to be processed.
    :type docs: Django Queryset
    :param skip_ocr: Whether OCR should be completed (False) or whether items
    should simply be updated to have status OCR_NEEDED.
    :type skip_ocr: Bool
    :param order_by: An optimization parameter. You may opt to order the
    processing by 'small-first' or 'big-first'.
    :type order_by: str
    :param queue: The celery queue to send the content to.
    :type queue: str
    :param queue_length: The number of items to send to the queue at a time.
    :type queue_length: int
    """
    docs = docs.exclude(filepath_local='')
    if skip_ocr:
        # Focus on the items that we don't know if they need OCR.
        docs = docs.filter(ocr_status=None)
    else:
        # We're doing OCR. Only work with those items that require it.
        docs = docs.filter(ocr_status=RECAPDocument.OCR_NEEDED)

    if order_by is not None:
        if order_by == 'small-first':
            docs = docs.order_by('page_count')
        elif order_by == 'big-first':
            docs = docs.order_by('-page_count')

    tasks = []
    completed = 0
    count = docs.count()
    logger.info("There are %s documents to process." % count)
    for pk in docs.values_list('pk', flat=True):
        # Send the items off for processing.
        last_item = (count == completed + 1)
        tasks.append(extract_recap_pdf.s(pk, skip_ocr).set(priority=5,
                                                           queue=queue))

        # Every enqueue_length items, send the tasks to Celery.
        if (len(tasks) >= queue_length) or last_item:
            logger.info("Sent %s tasks to celery. We have sent %s "
                        "items so far." % (len(tasks), completed + 1))
            job = group(*tasks)
            job.apply_async().join()
            tasks = []

        completed += 1
