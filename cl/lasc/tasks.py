# coding=utf-8

import hashlib
import json
from glob import glob

from django.apps import apps
from django.core.files.base import ContentFile
from django.utils.encoding import force_bytes
from juriscraper.lasc.fetch import LASCSearch

from cl.lasc.models import Docket, QueuedCase, QueuedPDF, DocumentImage, \
    UPLOAD_TYPE
from cl.lasc.models import LASCJSON, LASCPDF
from cl.lib.command_utils import logger


def process_case_queue(lasc_session):
    """Work through the queue of cases that need to be added to the database,
    and add them one by one.

    :param lasc_session: A Juriscraper.lasc.http.LASCSession object
    :return: None
    """
    queue = QueuedCase.objects.all()
    for case in queue:
        add_or_update_case(lasc_session, case.internal_case_id)


def process_pdf_queue(lasc_session):
    """Work through the queue of PDFs that need to be added to the database,
    download them and add them one by one.

    :param lasc_session: A Juriscraper.lasc.http.LASCSession object
    :return:
    """
    queue = QueuedPDF.objects.all()
    for pdf in queue:
        # Check if we already have the pdf
        doc = DocumentImage.objects.get(doc_id=pdf.document_id)
        if not doc.is_available:
            query = LASCSearch(lasc_session)
            pdf_data = query.get_pdf_from_url(pdf.document_url)

            pdf_document = LASCPDF(
                content_object=pdf,
                docket_number=pdf.docket.case_id.split(";")[0],
                document_id=pdf.document_id
            )

            pdf_document.filepath.save(
                pdf.document_id,
                ContentFile(pdf_data),
            )

            doc = DocumentImage.objects.get(doc_id=pdf.document_id)
            doc.is_available = True
            doc.save()

            pdf.delete()
        else:
            logger.info("Already have LASC PDF from docket ID %s with doc ID "
                        "%s ", doc.docket_id, doc.doc_id)


def add_case(case_id, case_data, lasc):
    is_queued = QueuedCase.objects.filter(internal_case_id=case_id)

    if is_queued.count() == 1:
        case_data["Docket"]['judge_code'] = is_queued[0].judge_code
        case_data["Docket"]['case_type_code'] = is_queued[0].case_type_code

    docket = Docket.objects.create(**case_data["Docket"])

    models = [x for x in apps.get_app_config('lasc').get_models()
              if x.__name__ not in ["Docket"]]

    while models:
        mdl = models.pop()
        while case_data[mdl.__name__]:
            case_data_row = case_data[mdl.__name__].pop()
            case_data_row["docket"] = docket
            mdl.objects.create(**case_data_row).save()

    save_json(lasc, docket)

    if is_queued.count() == 1:
        is_queued[0].delete()


def add_or_update_case(lasc_session, case_id):
    """Add a case from the LASC MAP using an authenticated session object

    :param lasc_session: A Juriscraper.lasc.http.LASCSession object
    :param case_id: The case ID to download, for example, '19STCV25157;SS;CV'
    :return: None
    """
    docket = Docket.objects.filter(case_id=case_id)
    lasc = LASCSearch(lasc_session)
    case_data = lasc.get_json_from_internal_case_id(case_id)

    if docket.count() == 0:
        logger.info("Adding Case")
        add_case(case_id, case_data, lasc)

    elif docket.count() == 1:
        if latest_sha(case_id=case_id) != make_sha1(lasc):
            logger.info("Updating Case")
            update_case(lasc)
        else:
            logger.info("Case Up To Date")
    else:
        logger.info("Issue - More than one case in system")


def make_sha1(query):
    """
    Generate SHA1 from case_data
    :param query: LASC Search Object
    :return: A generated SHA1 code.
    """
    return hashlib.sha1(force_bytes(json.loads(query.case_data))).hexdigest()


def latest_sha(case_id):
    """
    Query latest sha1 for Case by case_id
    :param case_id:
    :return:
    """
    docket = Docket.objects.get(case_id=case_id)
    o_id = LASCJSON(content_object=docket).object_id
    return LASCJSON.objects.filter(object_id=o_id).order_by('-pk')[0].sha1


def check_hash(query, case_id, case_hash):
    """
    Check if case has changed by case_hash.  Return True/False
    :param query:
    :param case_id:
    :param case_hash:
    :return:
    """
    query.get_json_from_internal_case_id(case_id)

    if case_hash == hashlib.sha1(force_bytes(json.loads(query.case_data))) \
        .hexdigest():
        return True
    else:
        return False


def update_case(query):
    """
    This code should update cases that have detected changes
    Method currently deletes and replaces the data on the system except for
    lasc_docket and connections for older json and pdf files.

    :param query:
    :return:
    """
    docket_number = query.normalized_case_data['Docket']['docket_number']
    district = query.normalized_case_data['Docket']['district']
    division_code = query.normalized_case_data['Docket']['division_code']

    case_id = ";".join([docket_number, district, division_code])

    docket = Docket.objects.filter(case_id=case_id)[0]
    docket.__dict__.update(query.normalized_case_data['Docket'])
    docket.save()

    docket = Docket.objects.filter(case_id=case_id)[0]

    data = query.normalized_case_data

    models = [x for x in apps.get_app_config('lasc').get_models()
              if x.__name__ not in ["Docket", "QueuedPDF",
                                    "QueuedCase", "LASCPDF",
                                    "LASCJSON", "DocumentImage"]]

    while models:
        mdl = models.pop()
        print mdl.__name__

        while data[mdl.__name__]:
            row = data[mdl.__name__].pop()
            row['docket'] = docket
            mdl.objects.create(**row).save()

    documents = query.normalized_case_data['DocumentImage']
    for row in documents:
        r = DocumentImage.objects.filter(doc_id=row['doc_id'])
        if r.count() == 1:
            row['is_available'] = r[0].is_available
            rr = r[0]
            rr.__dict__.update(**row)
            rr.save()
        else:
            row["docket"] = docket
            DocumentImage.objects.create(**row).save()

    logger.info("Saving Data to DB")
    save_json(query, content_obj=docket)


def remove_case(case_id):
    dock_obj = Docket.objects.filter(case_id=case_id)
    dock_obj.delete()


def get_filepath_from_case_id(case_id):
    docket = Docket.objects.get(case_id=case_id)
    object_id = LASCJSON(content_object=docket).object_id
    x = LASCJSON.objects.get(object_id=object_id)
    return x.filepath


def add_cases_from_directory(directory_glob):
    """Add cases from JSON saved to disk.

    :param directory_glob: A glob in which we look for cases to add, typically
    of the form /data/@json. Note that this will not recursively traverse
    directories.
    :return: None
    """
    query = LASCSearch(None)
    for fp in glob(directory_glob):
        with open(fp, 'r') as f:
            query.case_data = f.read()

        data = query._parse_case_data()
        docket_number = data['Docket']['docket_number']
        district = data['Docket']['district']
        division_code = data['Docket']['division_code']

        case_id = ";".join([docket_number, district, division_code])

        dock_obj = Docket.objects.filter(case_id=case_id)

        if dock_obj.count() == 0:
            is_queued = QueuedCase.objects.filter(internal_case_id=case_id)

            if is_queued.count() == 1:
                data["Docket"]['judge_code'] = is_queued[0].judge_code
                data["Docket"]['case_type_code'] = is_queued[0].case_type_code

            docket = Docket.objects.create(**data["Docket"])
            docket.save()

            dock_obj = Docket.objects.filter(case_id=case_id)

            models = [x for x in apps.get_app_config('lasc').get_models()
                      if x.__name__ not in ["Docket"]]

            while models:
                mdl = models.pop()
                while data[mdl.__name__]:
                    row = data[mdl.__name__].pop()
                    row["docket"] = dock_obj[0]
                    mdl.objects.create(**row).save()

            save_json(query, dock_obj[0])

            if is_queued.count() == 1:
                is_queued[0].delete()

        elif dock_obj.count() == 1:
            logger.info("Case Already In System")


def fetch_case_list_by_date(lasc_session, start, end):
    """Search for cases by date and add them to the DB.

    :param lasc_session: A Juriscraper.lasc.http.LASCSession object
    :param start: The date you want to start searching for cases
    :type start: datetime.date
    :param end: The date you want to stop searching for cases
    :type end: datetime.date
    :return: None
    """
    lasc = LASCSearch(lasc_session)
    cases = lasc.query_cases_by_date(start, end)

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

    logger.info("Added %s cases.", cases_added_cnt)

def save_json(query, content_obj):
    json_file = LASCJSON(content_object=content_obj)
    json_file.sha1 = make_sha1(query)
    json_file.upload_type = UPLOAD_TYPE.DOCKET
    json_file.filepath.save(
        'lasc.json',
        ContentFile(query.case_data),
    )
