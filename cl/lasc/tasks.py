# coding=utf-8

from datetime import datetime as dt
import hashlib, json
from glob import glob as g

from cl.lasc.models import Docket, QueuedCase, QueuedPDF, \
                         DocumentImage, UPLOAD_TYPE
from cl.lib.command_utils import logger
from cl.lasc.models import LASCJSON, LASCPDF

from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.apps import apps

from juriscraper.lasc.fetch import LASCSearch




def case_queue(sess):
    """

    :param lasc_session:
    :return:
    """

    queue = QueuedCase.objects.all()
    if queue.count() > 0:
        for case in queue:
            add_case(sess, case.internal_case_id)


def pdf_queue(sess):
    """

    :param lasc_session:
    :return:
    """

    queue = QueuedPDF.objects.all()
    if queue.count() > 0:
        for pdf in queue:

            # Check if we already have the pdf
            doc = DocumentImage.objects.get(doc_id=pdf.document_id)
            if doc.is_available == False:

                query = LASCSearch(sess)
                query._get_pdf_from_url(pdf.document_url)

                pdf_document = LASCPDF(
                    content_object=pdf,
                    docket_number=pdf.docket.case_id.split(";")[0],
                    document_id=pdf.document_id

                )

                pdf_document.filepath.save(
                    pdf.document_id,
                    ContentFile(query.pdf_data),
                )

                doc = DocumentImage.objects.get(doc_id=pdf.document_id)
                doc.is_available = True
                doc.save()

                pdf.delete()
            else:
                logger.info("Already Have Document")


def add_case(lasc_session, case_id):
    """
    :param lasc_session:
    :param case_id:
    :return:
    """

    docket = docket_for_case(case_id)

    query = LASCSearch(lasc_session)
    query.internal_case_id = case_id

    if docket.count() == 0:
        is_queued = QueuedCase.objects.filter(internal_case_id=case_id)

        data = get_normalized_data(query)

        if is_queued.count() == 1:
            data["Docket"]['judge_code'] = is_queued[0].judge_code
            data["Docket"]['case_type_code'] = is_queued[0].case_type_code


        docket = Docket.objects.create(**{key: value
                                          for key, value in
                                          data["Docket"].iteritems()})
        docket.save()

        docket = docket_for_case(case_id)
        models = [x for x in apps.get_app_config('lasc').get_models()
                  if x.__name__ not in ["Docket"]]

        while models:
            mdl = models.pop()
            while data[mdl.__name__]:
                case_data_row = data[mdl.__name__].pop()
                case_data_row["docket"] = docket[0]
                jj = {key: value for key, value in case_data_row.iteritems()}
                mdl.objects.create(**jj).save()

        save_json(query, content_obj=docket[0])

        if is_queued.count() == 1:
            is_queued[0].delete()

    elif docket.count() == 1:
        get_normalized_data(query)

        if latest_sha(case_id=case_id) != makeSha1(query):
            logger.info("Send to Update")
            update_case(query)
        else:
            logger.info("Case Up To Date")
    else:
        logger.info("Issue - More than one case in system")


def get_normalized_data(query):
    query._get_json_from_internal_case_id(query.internal_case_id)
    query._parse_case_data()
    return query.normalized_case_data


def makeSha1(query):
    """
    Generate SHA1 from case_data
    :param query:
    :return:
    """
    return hashlib.sha1(force_bytes(json.loads(query.case_data))).hexdigest()


def latest_sha(case_id):
    """
    Get newest sha1 generated on case by case id
    :param case_id:
    :return:
    """

    dn = case_id.split(";")
    docket = Docket.objects \
        .get(docket_number=dn[0])
    o_id = LASCJSON(content_object=docket).object_id
    return LASCJSON.objects.filter(object_id=o_id).order_by('-pk')[0].sha1


def check_hash(query, case_id, case_hash):
    """

    :param query:
    :param case_id:
    :param case_hash:
    :return:
    """

    query._get_json_from_internal_case_id(case_id)
    query._parse_case_data()

    # hashlib.sha1(force_bytes(json.loads(query.case_data))).hexdigest()
    # if case_hash == hashlib.sha1(force_bytes(query.case_data)).hexdigest():

    if case_hash == hashlib.sha1(force_bytes(json.loads(query.case_data)))\
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
    :param case_id:
    :return:
    """

    docket_number = query.normalized_case_data['Docket']['docket_number']
    district = query.normalized_case_data['Docket']['district']
    division_code = query.normalized_case_data['Docket']['division_code']

    case_id = ";".join([docket_number, district, division_code])

    docket = docket_for_case(case_id)[0]
    docket.__dict__.update(query.normalized_case_data['Docket'])
    docket.save()

    docket = docket_for_case(case_id)[0]

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
            jj = {key: value for key, value in row.iteritems()}
            mdl.objects.create(**jj).save()


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
            jj = {key: value for key, value in row.iteritems()}
            DocumentImage.objects.create(**jj).save()


    logger.info("Saving Data to DB")
    save_json(query, content_obj=docket)


def remove_case(case_id):

    case_obj = Docket.objects.filter(case_id=case_id)
    case_obj.delete()

    pass

def get_filepath_from_case_id(case_id):

    l = Docket.objects.get(case_id=case_id)
    o_id = LASCJSON(content_object=l).object_id
    print o_id
    x = LASCJSON.objects.get(object_id=o_id)
    print x.filepath


def import_wormhole_corpus(dir):
    """
    This is a function for importing the vast majority of data
    collected on the cases over the preceding months.


    :param directory:
    :return:
    """

    l = LASCSearch("")

    for fp in g(dir):
        with open(fp, 'r') as f:
            l.case_data = f.read()
        l._parse_case_data()
        data = l.normalized_case_data

        case_id = data['CaseInformation']['case_id']
        print case_id
        case_obj = Docket.objects.filter(case_id=case_id)
        if not case_obj.exists():

            case = {}
            case['case_id'] = case_id

            # case['date_added'], case['date_checked'], case['date_modified'] = \
            #     dt.now(tz=timezone.utc), dt.now(tz=timezone.utc), dt.now(tz=timezone.utc)
            case['date_checked'] = dt.now(tz=timezone.utc)
            case['full_data_model'] = True
            case["case_hash"] = hashlib.sha1(force_bytes(l.case_data)).hexdigest()

            docket = Docket.objects.create(**{key: value for key, value in case.iteritems()})
            docket.save()

            models = [x for x in apps.get_app_config('docket').get_models() if x.__name__ != "Docket"]
            lasc_obj = Docket.objects.filter(case_id=case_id)[0]

            while models:
                mdl = models.pop()

                case_data_array = data[mdl.__name__]
                if mdl.__name__ == "CaseInformation":
                    case_data_array = [case_data_array]
                    # print case_data_array

                while case_data_array:
                    case_data_row = case_data_array.pop()
                    case_data_row["Docket"] = lasc_obj
                    mdl.objects.create(**{key: value for key, value in case_data_row.iteritems()}).save()


def fetch_last_week(sess):
    query = LASCSearch(sess)
    query._get_case_list_for_last_seven_days()
    logger.info("Got data")
    query._parse_date_data()

    datum = query.normalized_date_data
    logger.info("Saving Data to DB")
    i = 0
    for case in datum:
        internal_case_id = case['case_id']
        case_object = QueuedCase.objects.filter(internal_case_id=internal_case_id)
        if not case_object.exists():
            i += 1
            dc = {}
            dc['internal_case_id'] = internal_case_id
            dc['judge_code'] = case['judge_code']
            dc['case_type_code'] = case['case_type_code']
            cd = QueuedCase.objects.create(**{key: value for key, value in dc.iteritems()})
            cd.save()

            logger.info("Adding %s" % (case['case_number']))

    logger.info("Added %s cases." % (i))

            json_file.filepath_local.save(
                'lasc.json',  # We only care about the ext w/UUIDFileSystemStorage
                ContentFile(l.case_data),
            )

def save_json(query, content_obj):
    json_file = LASCJSON(content_object=content_obj)
    json_file.upload_type = UPLOAD_TYPE.DOCKET
    json_file.filepath.save(
        'lasc.json',
        ContentFile(query.case_data),
    )

def docket_for_case(case_id):
    dn = case_id.split(";")
    return Docket.objects \
        .filter(docket_number=dn[0]) \
        .filter(district=dn[1]) \
        .filter(division_code=dn[2])
