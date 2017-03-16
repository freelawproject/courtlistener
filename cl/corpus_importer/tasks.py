import logging
import os
import shutil
from tempfile import NamedTemporaryFile

import internetarchive as ia
import requests
from django.conf import settings
from django.db import IntegrityError
from juriscraper.pacer import FreeOpinionReport
from requests.exceptions import ChunkedEncodingError, HTTPError
from requests.packages.urllib3.exceptions import ReadTimeoutError, \
    ConnectionError
from rest_framework.status import HTTP_403_FORBIDDEN

from cl.celery import app
from cl.lib.pacer import PacerXMLParser, lookup_and_save
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
        required_fields = ['case_name', 'date_filed']
        for field in required_fields:
            if not getattr(pacer_doc, field):
                logger.error("Missing required field: %s" % field)
                return recap_pks
        docket = lookup_and_save(pacer_doc, debug=debug)
        if docket is not None:
            try:
                recap_pks = pacer_doc.make_documents(docket, debug=debug)
            except (IntegrityError, DocketEntry.MultipleObjectsReturned) as exc:
                raise self.retry(exc=exc, countdown=20 * 60)
            else:
                pacer_doc.make_parties(docket, debug=debug)

    return recap_pks


@app.task(bind=True, max_retries=5)
def get_free_document_report(self, court_id, start, end, session):
    """Get structured results from the PACER free document report"""
    report = FreeOpinionReport(court_id, session)
    try:
        responses = report.query(start, end, sort='case_number')
    except (ConnectionError, ChunkedEncodingError) as exc:
        logger.warning("Unable to get free document report results from %s on "
                       "%s. Trying again." % (court_id, d))
        raise self.retry(exc=exc, countdown=5)
    else:
        return report.parse(responses)


@app.task(bind=True, max_retries=5)
def get_pdf(self, data, court_id, session):
    report = FreeOpinionReport(court_id, session)
    try:
        r = report.download_pdf(data.pacer_case_id, data.pacer_doc_id)
    except ConnectionError as exc:
        logger.warning("Unable to get PDF for %s" % data)
        raise self.retry(exc=exc, countdown=5)
    else:
        return r


@app.task(bind=True, max_retries=15)
def upload_to_ia(self, identifier, files, metadata=None, session=None):
    """Upload an item and its files to the Internet Archive

    On the Internet Archive there are Items and files. Items have a global
    identifier, and files go inside the item:

        https://internetarchive.readthedocs.io/en/latest/items.html

    This function mirrors the IA library's similar upload function, but builds
    in retries and various assumptions that make sense. Note that according to
    emails with IA staff, it is best to maximize the number of files uploaded to
    an Item at a time, rather than uploading each file in a separate go.

    :param identifier: The global identifier within IA for the item you wish to
    work with.
    :param files: The filepaths or file-like objects to upload. This value can be
    an iterable or a single file-like object or string.
    :param metadata: Metadata used to create a new item. If the item already
    exists, the metadata will not be updated
    :param session: An ArchiveSession object. If none is provided, one will be
    created automatically. However, if more than one item is being uploaded,
    it's best to create one session for the entire batch rather than one session
    per upload.

    :rtype: list
    :returns: List of response objects, one per file.
    """
    metadata = {} if metadata is None else metadata
    countdown = 5 * self.request.retries  # 5s, 10s, 15s...
    access_key = settings.IA_ACCESS_KEY
    secret_key = settings.IA_SECRET_KEY
    session = session or ia.get_session({'s3': {
        'access': access_key,
        'secret': secret_key,
    }})
    logger.info("Uploading file to Internet Archive with identifier: %s and "
                "files %s" % (identifier, files))
    item = session.get_item(identifier)
    try:
        # Before pushing files, check if the endpoint is overloaded. This is
        # lighter-weight than attempting a document upload off the bat.
        if session.s3_is_overloaded(identifier, access_key):
            try:
                raise Exception("S3 is currently overloaded.")
            except Exception as exc:
                raise self.retry(exc=exc, countdown=countdown)
        responses = item.upload(files=files, metadata=metadata,
                                queue_derive=False, verify=True)
        logger.info("Item uploaded to IA with responses %s" %
                    [r.status_code for r in responses])
        return responses
    except HTTPError as exc:
        if exc.response.status_code == HTTP_403_FORBIDDEN:
            return [exc.response]
        raise self.retry(exc=exc, countdown=countdown)

