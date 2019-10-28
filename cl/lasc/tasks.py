# coding=utf-8
import json
import logging
import os
import pickle
from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from juriscraper.lasc.fetch import LASCSearch
from juriscraper.lasc.http import LASCSession
from requests import RequestException

from cl.celery import app
from cl.lasc.models import Docket, DocumentImage, QueuedCase, QueuedPDF, \
    UPLOAD_TYPE
from cl.lasc.models import LASCJSON, LASCPDF
from cl.lasc.utils import make_case_id
from cl.lib.crypto import sha1_of_json_data
from cl.lib.redis_utils import make_redis_interface

logger = logging.getLogger(__name__)

LASC_USERNAME = os.environ.get('LASC_USERNAME', settings.LASC_USERNAME)
LASC_PASSWORD = os.environ.get('LASC_PASSWORD', settings.LASC_PASSWORD)


LASC_SESSION_STATUS_KEY = "session:lasc:status"
LASC_SESSION_COOKIE_KEY = "session:lasc:cookies"


class SESSION_IS(object):
    LOGGING_IN = 'logging_in'
    OK = 'ok'


def login_to_court():
    """Set the login cookies in redis for an LASC user

    Replace any existing cookies in redis.

    :return: None
    """
    r = make_redis_interface('CACHE')
    # Give yourself a few minutes to log in
    r.set(LASC_SESSION_STATUS_KEY, SESSION_IS.LOGGING_IN, ex=60 * 2)
    lasc_session = LASCSession(username=LASC_USERNAME,
                               password=LASC_PASSWORD)
    lasc_session.login()
    cookie_str = str(pickle.dumps(lasc_session.cookies))
    # Done logging in; save the cookies.
    r.set(LASC_SESSION_COOKIE_KEY, cookie_str, ex=60 * 30)
    r.set(LASC_SESSION_STATUS_KEY, SESSION_IS.OK, ex=60 * 30)


def establish_good_login(self):
    """Make sure that we have good login credentials for LASC in redis

    Checks the Login Status for LASC.  If no status is found runs login
    function to store good keys in redis.

    :param self: A Celery task object
    :return: None
    """
    r = make_redis_interface('CACHE')
    retry_backoff = 60
    status = r.get(LASC_SESSION_STATUS_KEY)
    if status == SESSION_IS.LOGGING_IN:
        self.retry(countdown=retry_backoff)
    bad_login = status != SESSION_IS.OK
    if bad_login:
        login_to_court()


def make_lasc_search():
    """Create a logged-in LASCSearch object with cookies pulled from cache

    :return: LASCSearch object
    """
    r = make_redis_interface('CACHE')
    session = LASCSession()
    session.cookies = pickle.loads(r.get(LASC_SESSION_COOKIE_KEY))
    return LASCSearch(session)


@app.task(bind=True, ignore_result=True, max_retries=1)
def download_pdf(self, pdf_pk):
    """Downloads the PDF associated with the PDF DB Object ID passed in.

    :param self: The celery instance
    :param pdf_pk: The primary key of the QueuedPDF object we are downloading
    :return: None; object is saved to DB and filesystem
    """
    establish_good_login(self)
    lasc = make_lasc_search()

    q_pdf = QueuedPDF.objects.get(pk=pdf_pk)

    doc = DocumentImage.objects.get(doc_id=q_pdf.document_id)
    if doc.is_available:
        logger.info("Already have LASC PDF from docket ID %s with doc ID %s ",
                    doc.docket_id, doc.doc_id)
        return

    try:
        pdf_data = lasc.get_pdf_from_url(q_pdf.document_url)
    except RequestException as exc:
        logger.warning("Got RequestException trying to get PDF for PDF "
                       "Queue %s", q_pdf.pk)
        if self.request.retries == self.max_retries:
            return
        raise self.retry(exc=exc)

    pdf_document = LASCPDF(
        content_object=q_pdf,
        docket_number=q_pdf.docket.case_id.split(";")[0],
        document_id=q_pdf.document_id
    )

    logger.info("%s, ID #%s from docket ID %s ",
                doc.document_type, doc.doc_id, q_pdf.docket.case_id)

    with transaction.atomic():
        pdf_document.filepath_s3.save(
            doc.document_type,
            ContentFile(pdf_data),
        )

        doc.is_available = True
        doc.save()

        # Remove the PDF from the queue
        q_pdf.delete()


def add_case(case_id, case_data, original_data):
    """Adds a new case to the cl.lasc database

    :param case_id: A full LASC case_id
    :param case_data: Parsed data representing a docket as returned by
    Juriscraper
    :param original_data: The original JSON object as a str
    :return: None
    """
    logger.info("Adding LASC case %s", case_id)
    with transaction.atomic():
        # If the item is in the case queue, enhance it with metadata found
        # there.
        queued_cases = QueuedCase.objects.filter(internal_case_id=case_id)
        if queued_cases.count() == 1:
            case_data["Docket"]['judge_code'] = queued_cases[0].judge_code
            case_data["Docket"]['case_type_code'] = queued_cases[
                0].case_type_code
            queued_cases.delete()

        docket = Docket.objects.create(**case_data["Docket"])
        models = [x for x in apps.get_app_config('lasc').get_models()
                  if x.__name__ not in ["Docket"]]

        while models:
            mdl = models.pop()
            while case_data[mdl.__name__]:
                case_data_row = case_data[mdl.__name__].pop()
                case_data_row["docket"] = docket
                mdl.objects.create(**case_data_row).save()

        save_json(original_data, docket)


@app.task(bind=True, ignore_result=True, max_retries=1)
def add_or_update_case_db(self, case_id):
    """Add a case from the LASC MAP using an authenticated session object

    :param self: The celery object
    :param case_id: The case ID to download, for example, '19STCV25157;SS;CV'
    :return: None
    """
    establish_good_login(self)
    lasc = make_lasc_search()

    clean_data = {}
    try:
        clean_data = lasc.get_json_from_internal_case_id(case_id)
        logger.info("Successful Query")
    except RequestException:
        if self.request.retries == self.max_retries:
            logger.error("RequestException, unable to get case at %s", case_id)
            return
        r = make_redis_interface('CACHE')
        r.delete(LASC_SESSION_COOKIE_KEY, LASC_SESSION_STATUS_KEY)
        self.retry(countdown=60)

    if not clean_data:
        logger.info("No information for case %s. Possibly sealed?", case_id)
        return

    ds = Docket.objects.filter(case_id=case_id)
    ds_count = ds.count()
    if ds_count == 0:
        logger.info("Adding lasc case with ID: %s", case_id)
        add_case(case_id, clean_data, lasc.case_data)
    elif ds_count == 1:
        if latest_sha(case_id=case_id) != sha1_of_json_data(lasc.case_data):
            logger.info("Updating lasc case with ID: %s", case_id)
            update_case(lasc, clean_data)
        else:
            logger.info("LASC case is already up to date: %s", case_id)
    else:
        logger.warn("Issue adding or updating lasc case with ID '%s' - Too "
                    "many cases in system with that ID (%s cases)",
                    case_id, ds_count)


def latest_sha(case_id):
    """Get the latest SHA1 for a case by case_id

    :param case_id: The semicolon-delimited lasc ID for the case
    :return: The SHA1 for the case
    """
    docket = Docket.objects.get(case_id=case_id)
    o_id = LASCJSON(content_object=docket).object_id
    return LASCJSON.objects.filter(object_id=o_id).order_by('-pk')[0].sha1


def update_case(lasc, clean_data):
    """Update an existing case with new data

    Method currently deletes and replaces the data on the system except for
    lasc_docket and connections for older json and pdf files.

    :param lasc: A LASCSearch object
    :param clean_data: A normalized data dictionary
    :return: None
    """
    case_id = make_case_id(clean_data)
    with transaction.atomic():
        docket = Docket.objects.filter(case_id=case_id)[0]
        docket.__dict__.update(clean_data['Docket'])
        docket.save()

        skipped_models = ["Docket", "QueuedPDF", "QueuedCase", "LASCPDF",
                          "LASCJSON", "DocumentImage"]
        models = [x for x in apps.get_app_config('lasc').get_models()
                  if x.__name__ not in skipped_models]

        while models:
            mdl = models.pop()

            while clean_data[mdl.__name__]:
                row = clean_data[mdl.__name__].pop()
                row['docket'] = docket
                mdl.objects.create(**row).save()

        documents = clean_data['DocumentImage']

        for row in documents:
            dis = DocumentImage.objects.filter(doc_id=row['doc_id'])
            dis_count = dis.count()
            if dis_count == 1:
                di = dis[0]
                row['is_available'] = di.is_available
                di.__dict__.update(**row)
            elif dis_count == 0:
                row["docket"] = docket
                di = DocumentImage(**row)
            di.save()

        logger.info("Finished updating lasc case '%s'", case_id)
        save_json(lasc.case_data, content_obj=docket)


@app.task(ignore_result=True, max_retries=1)
def add_case_from_filepath(filepath):
    """Add case to database from filepath

    :param self: The celery object
    :param filepath: Filepath string to where the item is stored
    :return: None
    """
    query = LASCSearch(None)
    with open(filepath, 'r') as f:
        original_data = f.read()

    case_data = query._parse_case_data(json.loads(original_data))
    case_id = make_case_id(case_data)

    ds = Docket.objects.filter(case_id=case_id)

    if ds.count() == 0:
        add_case(case_id, case_data, original_data)
    elif ds.count() == 1:
        logger.warn("LASC case on file system at '%s' is already in "
                    "the database ", filepath)


@app.task(bind=True, ignore_result=True, max_retries=2)
def fetch_date_range(self, start, end):
    """Queries LASC for one week or less range and returns the cases filed.

    :param self: the celery object
    :param start: The date you want to start searching for cases
    :type start: datetime
    :param end: The date you want to stop searching for cases
    :type end: datetime
    :return: None
    """
    establish_good_login(self)
    lasc = make_lasc_search()

    try:
        cases = lasc.query_cases_by_date(start, end)
    except RequestException as exc:
        logger.warning("Got RequestException trying to get cases by date "
                       "between %s and %s", start, end)
        if self.request.retries == self.max_retries:
            return
        raise self.retry(exc=exc)

    cases_added_cnt = 0
    for case in cases:
        internal_case_id = case['internal_case_id']
        case_object = QueuedCase.objects.filter(
            internal_case_id=internal_case_id)
        if not case_object.exists():
            QueuedCase.objects.create(**{
                'internal_case_id': internal_case_id,
                'judge_code': case['judge_code'],
                'case_type_code': case['case_type_code'],
            })
            cases_added_cnt += 1
            logger.info("Adding case '%s' to LASC database.",
                        case['internal_case_id'])

    logger.info("Added %s cases to the QueuedCase table.", cases_added_cnt)


def save_json(data, content_obj):
    """
    Save json string to file and generate SHA1.

    :param data: JSON response cleaned
    :param content_obj: The content object associated with the JSON file in
    the DB
    :return: None
    """
    json_file = LASCJSON(content_object=content_obj)
    json_file.sha1 = sha1_of_json_data(data)
    json_file.upload_type = UPLOAD_TYPE.DOCKET
    json_file.filepath.save(
        'lasc.json',
        ContentFile(data),
    )
