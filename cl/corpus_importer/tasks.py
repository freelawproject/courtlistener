import logging
import os
import shutil

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from requests.packages.urllib3.exceptions import ReadTimeoutError

from cl.celery import app

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=5)
def download_recap_item(self, url, filename):
    logger.info("  Getting item at: %s" % url)
    location = os.path.join(settings.MEDIA_ROOT, 'recap', filename)
    try:
        if os.path.isfile(location):
            raise IOError("    IOError: File already exists at %s" % location)
        r = requests.get(
            url,
            stream=True,
            timeout=60,
            headers={'User-Agent': "Free Law Project"},
        )
        r.raise_for_status()
    except requests.Timeout as e:
        logger.warning("    Timed out attempting to get: %s\n" % url)
        raise self.retry(exc=e, countdown=2)
    except requests.RequestException as e:
        logger.warning("    Unable to get %s\nException was:\n%s" % (url, e))
    except IOError as e:
        logger.warning("    %s" % e)
    else:
        with open(location, 'wb') as f:
            r.raw.decode_content = True
            try:
                shutil.copyfileobj(r.raw, f)
            except ReadTimeoutError as exc:
                os.remove(location)  # Cleanup
                raise self.retry(exc=exc)


@app.task
def parse_recap_item(path):
    """Parse a RECAP docket and save it to the database

    If a judge string is found that cannot be looked up, save that value to a
    CSV for later review.
    """
    logger.info("Parsing docket: %s" % path)

    with open(path, 'r') as f:
        docket_xml_content = f.read()
        if not docket_xml_content:
            raise Exception("Could not read the XML contents")

    soup = BeautifulSoup(docket_xml_content, 'lxml-xml')
