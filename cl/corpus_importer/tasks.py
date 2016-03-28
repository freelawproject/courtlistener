import logging
import os
import requests
import shutil

from celery import task
from django.conf import settings

logger = logging.getLogger(__name__)


@task
def download_recap_item(url, filename):
    logger.info("  Getting item at: %s" % url)
    location = os.path.join(settings.MEDIA_ROOT, 'recap', filename)
    try:
        if os.path.isfile(location):
            raise IOError("    IOError: File already exists at %s" % location)
        r = requests.get(
            url,
            stream=True,
            headers={'User-Agent': "Free Law Project"},
        )
        r.raise_for_status()
    except requests.RequestException as e:
        logger.warning("    Unable to get item! Exception was:\n%s" % e)
    except IOError as e:
        logger.warning("    %s" % e)
    else:
        with open(location, 'wb') as f:
            r.raw.decode_content = True
            shutil.copyfileobj(r.raw, f)
