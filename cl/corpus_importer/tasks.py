import logging
import os
import shutil
from tempfile import NamedTemporaryFile

import requests
from django.conf import settings
from django.db import IntegrityError
from requests.packages.urllib3.exceptions import ReadTimeoutError

from cl.celery import app
from cl.lib.pacer import PacerXMLParser
from cl.search.models import DocketEntry

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=5)
def download_recap_item(self, url, filename, clobber=False):
    logger.info("  Getting item at: %s" % url)
    location = os.path.join(settings.MEDIA_ROOT, 'recap', filename)
    try:
        if os.path.isfile(location) and not clobber:
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
        with NamedTemporaryFile(prefix='recap_download_') as tmp:
            r.raw.decode_content = True
            try:
                shutil.copyfileobj(r.raw, tmp)
                tmp.flush()
            except ReadTimeoutError as exc:
                # The download failed part way through.
                raise self.retry(exc=exc)
            else:
                # Successful download. Copy from tmp to the right spot. Note
                # that this will clobber.
                shutil.copyfile(tmp.name, location)


@app.task(bind=True, max_retries=3)
def parse_recap_docket(self, filename, debug=False):
    """Parse a docket path, creating items or updating existing ones."""
    docket_path = os.path.join(settings.MEDIA_ROOT, 'recap', filename)
    recap_pks = []
    try:
        pacer_doc = PacerXMLParser(docket_path)
    except IOError:
        logger.warning("Unable to find the docket at: %s" % docket_path)
    else:
        docket = pacer_doc.save(debug=debug)
        if docket is not None:
            try:
                recap_pks = pacer_doc.make_documents(docket, debug=debug)
            except (IntegrityError, DocketEntry.MultipleObjectsReturned) as exc:
                raise self.retry(exc=exc, countdown=20 * 60)
            else:
                pacer_doc.make_parties(docket, debug=debug)

    return recap_pks
