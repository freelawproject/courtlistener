import logging
import time
from functools import wraps

import requests
import tldextract
from django.conf import settings
from requests import RequestException

from cl.lib.bot_detector import is_bot

logger = logging.getLogger(__name__)


def retry(ExceptionToCheck, tries=4, delay=3, backoff=2, logger=None):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param ExceptionToCheck: the exception to check. may be a tuple of
    exceptions to check
    :type ExceptionToCheck: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
    each retry
    :type backoff: int
    :param logger: logger to use. If None, print
    :type logger: logging.Logger instance
    """
    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    else:
                        print msg
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


def track_in_matomo(func, timeout=0.5, check_bots=True):
    """A decorator to track a request in Matomo.

    This decorator is needed on static assets that we want to track because
    those assets can only be tracked by client-side Matomo if they are accessed
    by a user clicking a link in CourtListener itself. If, for example,
    somebody shares a link or otherwise clicks it outside of CourtListener, we
    don't have an opportunity to run our client-side code on that item, and we
    won't be able to track it.

    The code here wraps a view so that when somebody accesses something like a
    PDF from an external site (and only from an external site), we track that
    properly. If people have a CourtListener referer, we ignore them under the
    assumption that they got tracked client-side.

    :param func: The function that we're wrapping.
    :param timeout: The amount of time the Matomo tracking request has to
    respond. If it does not respond in this amount of time, we time out and
    move on.
    :param check_bots: Whether to check bots before hitting Matomo. Matomo
    itself has robust bot detection, so we can rely on that in general, but
    it's generally better to do some basic blocking here too to avoid even
    involving Matomo if we can. Set this to False if you prefer to rely
    exclusively on Matomo's bot detection.
    :returns the result of the wrapped function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        t1 = time.time()
        result = func(*args, **kwargs)  # Run the view
        t2 = time.time()

        if settings.DEVELOPMENT:
            # Disable tracking during development.
            return result

        request = args[0]  # Request is always first arg.
        if check_bots and is_bot(request):
            return result

        url = request.build_absolute_uri()
        referer = request.META.get('HTTP_REFERER', '')
        url_domain = tldextract.extract(url)
        ref_domain = tldextract.extract(referer)
        if url_domain == ref_domain:
            # Referer domain is same as current. Don't count b/c it'll be
            # caught by client-side Matomo tracker already.
            return result

        try:
            # See: https://developer.matomo.org/api-reference/tracking-api
            requests.get(
                settings.MATOMO_URL,
                timeout=timeout,
                params={
                    'idsite': settings.MATOMO_SITE_ID,
                    'rec': 1,  # Required but unexplained in docs.
                    'url': url,
                    'download': url,
                    'apiv': 1,
                    'urlref': referer,
                    'ua': request.META.get('HTTP_USER_AGENT', ''),
                    'gt_ms': int((t2 - t1) * 1000),  # Milliseconds
                    'send_image': 0,
                },
            )
        except RequestException:
            logger.info("Matomo tracking request had an error (likely "
                        "timeout?) out for URL: %s" % url)
        return result

    return wrapper
