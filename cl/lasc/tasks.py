# coding=utf-8

from datetime import datetime as dt
import hashlib, types, json

from cl.lasc.models import Docket, DocumentImages
from cl.lib.command_utils import logger
from cl.lib.models import LASCJSON, UPLOAD_TYPE, LASCPDF

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.serializers import serialize as sz
from django.utils import timezone
from django.utils.encoding import force_bytes

# from django.contrib.contenttypes.models import ContentType
from django.apps import apps

from juriscraper.lasc.fetch import LASCSearch
from juriscraper.lasc.http import LASCSession

from glob import glob as g

def get_pdf(lasc_session, case_id):

    docket = Docket.objects.get(case_id=case_id)
    images = DocumentImages.objects.filter(Docket=docket).filter(downloaded=False).all()
    if images.count() > 0:
        pdf = images[0]
        url = pdf.document_url

        query = LASCSearch(lasc_session)
        query._get_pdf_from_url(url)

        pdf_document = LASCPDF(content_object=pdf,
                                    upload_type=UPLOAD_TYPE.PDF)

        pdf_document.filepath.save(
            'lasc.pdf',
            ContentFile(query.pdf_data),
        )
        pdf.downloaded = True
        pdf.save()

    else:
        logger.info("All PDFs downloaded")

def get_pdfs(lasc_session, case_id):

    docket = Docket.objects.get(case_id=case_id)
    pdfs = DocumentImages.objects.filter(Docket=docket).filter(downloaded=False).all()
    if pdfs.count() > 0:
        for pdf in pdfs:
            logger.info("Downloading %s" % (pdf.document_url))

            url = pdf.document_url

            query = LASCSearch(lasc_session)
            query._get_pdf_from_url(url)

            pdf_document = LASCPDF(content_object=pdf,
                                        upload_type=UPLOAD_TYPE.PDF)

            pdf_document.filepath.save(
                'lasc.pdf',
                ContentFile(query.pdf_data),
            )
            pdf.downloaded = True
            pdf.save()
    else:
        logger.info("All PDFs downloaded")


def get_pdfs_async(lasc_session, case_id):

    url_list = []
    lasc_obj = Docket.objects.filter(case_id=case_id)[0]
    docket = Docket.objects.get(case_id=case_id)
    pdfs = DocumentImages.objects.filter(Docket=docket).filter(downloaded=False).all()
    if pdfs.count() > 0:
        for pdf in pdfs:
            url = pdf.document_url
            url_list.append(url)

        query = LASCSearch(lasc_session)
        query._get_pdfs_from_urls(url_list)

        for pdf_data in query.pdfs_data:
            pdf_document = LASCPDF(content_object=lasc_obj,
                                        upload_type=UPLOAD_TYPE.PDF)

            pdf_document.filepath.save(
                'lasc.pdf',  # We only care about the ext w/UUIDFileSystemStorage
                ContentFile(pdf_data),
            )


def add_case(lasc_session, case_id):
    """

    :param lasc_session:
    :param case_id:
    :return:
    """

    case_obj = Docket.objects.filter(case_id=case_id)


    query = LASCSearch(lasc_session)
    query._get_json_from_internal_case_id(case_id)
    query._parse_case_data()
    data = query.normalized_case_data

    if case_obj.count() == 1:
        if case_obj[0].full_data_model == False:
            print "\nDo full search -- adding to database\n"

            docket = Docket.objects.filter(case_id=case_id)
            case = {}
            case['full_data_model'] = True
            case['date_checked'] = dt.now(tz=timezone.utc)
            case["case_hash"] = hashlib.sha1(force_bytes(query.case_data)).hexdigest()

            docket.update(**{key: value for key, value in case.iteritems()})


        else:
            logger.info("Run Code to check for updates... not adding")

            if not check_hash(query, case_id, case_obj[0].case_hash):
                logger.info("Case Up-To-Date")
                docket = Docket.objects.filter(case_id=case_id)
                case = {}
                case['date_checked'] = dt.now(tz=timezone.utc)
                docket.update(**{key: value for key, value in case.iteritems()})
            else:

                logger.info("Case Not - up to date, Sending to update")
                update_case(query, case_id)

            logger.info("Finished Updating")

            return "" #Can end here


    else:
        logger.info("New Case")

        case = {}
        case['case_id'] = case_id
        # case['date_added'], case['date_checked'], case['date_modified'] = \
        #     dt.now(tz=timezone.utc), dt.now(tz=timezone.utc), dt.now(tz=timezone.utc)
        case['date_checked'] = dt.now(tz=timezone.utc)
        case['full_data_model'] = True
        case["case_hash"] = hashlib.sha1(force_bytes(query.case_data)).hexdigest()

        docket = Docket.objects.create(**{key: value for key, value in case.iteritems()})

        docket.save()

    models = [x for x in apps.get_app_config('lasc').get_models() if x.__name__ not in ["Docket", "Proceedings"]]
    lasc_obj = Docket.objects.filter(case_id=case_id)[0]
    pmdl = apps.get_model('lasc', 'Proceedings')

    dont_save_list = ["PastProceedings", "FutureProceedings"]
    while models:
        mdl = models.pop()

        print mdl.__name__


        case_data_array = data[mdl.__name__]
        if mdl.__name__ == "CaseInformation":
            case_data_array = [case_data_array]
            # print case_data_array

        while case_data_array:

            case_data_row = case_data_array.pop()
            case_data_row["Docket"] = lasc_obj

            fields = [field.name for field in mdl._meta.fields]
            fields.append("Docket")

            jj = {key: value for key, value in case_data_row.iteritems() if key in fields}

            # mdl.objects.create(**{key: value for key, value in case_data_row.iteritems()}).save()

            if mdl.__name__ not in dont_save_list:
                mdl.objects.create(**jj).save()


            if mdl.__name__ == "PastProceedings":
                jj['past_or_future'] = 1
                pmdl.objects.create(**jj).save()

            if mdl.__name__ == "FutureProceedings":
                jj['past_or_future'] = 2
                pmdl.objects.create(**jj).save()

    logger.info("Saving Data to DB")


    json_file = LASCJSON(content_object=lasc_obj,
                                upload_type=UPLOAD_TYPE.JSON)

    json_file.filepath.save(
        'lasc.json',  # We only care about the ext w/UUIDFileSystemStorage
        ContentFile(query.case_data),
    )



def check_case(lasc_session, case_id):
    """

    :param lasc_session:
    :param case_id:
    :return:
    """
    print case_id
    pass


def check_hash(query, case_id, case_hash):
    """

    :param query:
    :param case_id:
    :param case_hash:
    :return:
    """

    query._get_json_from_internal_case_id(case_id)
    query._parse_case_data()

    if case_hash == hashlib.sha1(force_bytes(query.case_data)).hexdigest():
        return True
    else:
        return False



def update_case(query, case_id):
    """
    This code should update cases that have detected changes

    :param query:
    :param case_id:
    :return:
    """

    data = query.normalized_case_data

    for d in data:

        if type(data[d]) == types.ListType:

            mdl = apps.get_app_config('lasc').get_model(d)
            docs = mdl.objects.filter(Docket__case_id=case_id).order_by('pk')

            if len(docs) != len(data[d]): # If this is different new fields

                dx = len(data[d]) - len(docs)

                for row in data[d][0:dx]:

                    row["Docket"] = Docket.objects.filter(case_id=case_id)[0]
                    mdl.objects.create(**{key: value for key, value in row.iteritems()}).save()


        if type(data[d]) == types.DictionaryType:

            mdl = apps.get_app_config('lasc').get_model(d)
            docs = mdl.objects.filter(Docket__case_id=case_id).order_by('pk')

            sobj = sz('json', [docs[0], ])
            xx = json.loads(sobj)[0]['fields']

            for key in data[d]:

                if type(data[d][key]) != type(xx[key]):
                    checkd = dt.strptime(xx[key], '%Y-%m-%d').date()
                else:
                    checkd = xx[key]

                if checkd != data[d][key]:

                    # print "\n", key, ":", data[d][key], " -----> ", xx[key]

                    mdl.objects.filter(Docket__case_id=case_id).order_by('pk').update(**{key: value for key, value in {key:data[d][key]}.iteritems()})

    # Save our new hash and update the date checked moment.

    docket = Docket.objects.filter(case_id=case_id)
    case = {}
    case['date_checked'] = dt.now(tz=timezone.utc)
    case['date_modified'] = dt.now(tz=timezone.utc)
    case["case_hash"] = hashlib.sha1(force_bytes(query.case_data)).hexdigest()

    docket.update(**{key: value for key, value in case.iteritems()})

def remove_case(case_id):

    l = Docket.objects.get(case_id=case_id)
    l.delete()


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


            logger.info("Saving Data to DB")


            json_file = LASCJSON(content_object=lasc_obj,
                                        upload_type=UPLOAD_TYPE.CASE_JSON)

            json_file.filepath.save(
                'lasc.json',  # We only care about the ext w/UUIDFileSystemStorage
                ContentFile(l.case_data),
            )


        else:
            print "in the system"



