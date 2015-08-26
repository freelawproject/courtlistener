import mimetypes
import os
import requests
import traceback
from django.conf import settings
from lxml import html
from urlparse import urljoin

from cl.lib import magic
from juriscraper.AbstractSite import logger
from juriscraper.tests import MockRequest


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


def signal_handler(signal, frame):
    # Trigger this with CTRL+4
    logger.info('**************')
    logger.info('Signal caught. Finishing the current court, then exiting...')
    logger.info('**************')
    global die_now
    die_now = True
