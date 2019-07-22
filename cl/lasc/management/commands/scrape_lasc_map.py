import argparse
import os, json, sys
#
from celery.canvas import chain
from django.conf import settings
from django.utils.timezone import now
from django.utils import timezone
from juriscraper.lasc.http import LASCSession
from juriscraper.lasc.fetch import LASCSearch

from cl.lasc.models import LASC, DocumentImages, RegisterOfActions, \
                        Parties, DocumentsFiled, \
                        PastProceedings, FutureProceedings, \
                        CrossReferences, CaseHistory, TentativeRulings

from datetime import datetime as dt

from requests import RequestException
#
# from cl.corpus_importer.tasks import (
#     mark_court_done_on_date,
#     get_and_save_free_document_report,
#     process_free_opinion_result, get_and_process_pdf, delete_pacer_row,
# )
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.db_tools import queryset_generator
# from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id
# from cl.scrapers.models import PACERFreeDocumentLog, PACERFreeDocumentRow
# from cl.scrapers.tasks import extract_recap_pdf
# from cl.search.models import Court, RECAPDocument
# from cl.search.tasks import add_items_to_solr, add_docket_to_solr_by_rds


LASC_USERNAME = os.environ.get('LASC_USERNAME', settings.LASC_USERNAME)
LASC_PASSWORD = os.environ.get('LASC_PASSWORD', settings.LASC_PASSWORD)


class Command(VerboseCommand):
    help = "Get all the free content from PACER."

    def valid_actions(self, s):

        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s" % (
                    ', '.join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s" % (
                ', '.join(self.VALID_ACTIONS.keys())
            )
        )
        parser.add_argument(
            '--queue',
            default='batch1',
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            '--index',
            action='store_true',
            default=False,
            help='Do we index as we go, or leave that to be done later?'
        )
        parser.add_argument(
            '--case',
            default='19STCV25157;SS;CV',
            help="The celery queue where the tasks should be processed.",
        )


    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options['action'](options)



    def get_cases_for_last_week(options):
        """This code collects the last weeks worth of new cases and add them to the database."""
        logger.info("Getting last weeks data.")

        lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        lasc_session.login()

        query = LASCSearch(lasc_session)
        query._get_case_list_for_last_seven_days()
        logger.info("Got data")

        cases = json.loads(query.date_case_list)['ResultList']
        logger.info("Saving Data to DB")

        for case in cases:
            num_results = LASC.objects.filter(InternalCaseID=case['InternalCaseID']).count()

            if num_results == 0:
                if case['DispTypeCode'] == None:
                    case['DispTypeCode'] = ""
                if case['JudgeCode'] == None:
                    case['JudgeCode'] = ""

                cd = LASC.objects.create(**{key: value for key, value in case.iteritems()})
                cd.save()
            else:
                print "Exists"

        logger.info("Finished Saving.")


    def fill_data(options):

        if "--case" in sys.argv:
            InternalCaseID = options['case']
            q = LASC.objects.filter(InternalCaseID=InternalCaseID)

        else:
            q = LASC.objects.all()
            InternalCaseID = q[0].InternalCaseID

        print InternalCaseID,

        lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        lasc_session.login()

        query = LASCSearch(lasc_session)
        query._get_json_from_internal_case_id(InternalCaseID)

        datum =  json.loads(query.case_data)['ResultList']

        rOfA = datum[0]['NonCriminalCaseInformation']['RegisterOfActions'][0]
        rOfA['LASC'] = q[0]
        ra = RegisterOfActions.objects.create(**{key: value for key, value in rOfA.iteritems()})

        print ra.Description


    def add_new_case(options):

        if "--case" in sys.argv:
            icID = options['case']
            q = LASC.objects.filter(InternalCaseID=icID)

            if not q.exists():
                print "Case doesnt exist"

            else:
                print "case already exists"
                q.delete()
                return ''

        lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        lasc_session.login()
        query = LASCSearch(lasc_session)
        query._get_json_from_internal_case_id(icID)


        datum = json.loads(query.case_data)['ResultList'][0]['NonCriminalCaseInformation']

        case = datum['CaseInformation']
        rOfA = datum['RegisterOfActions']
        dI = datum['DocumentImages']
        p = datum['Parties']
        dF = datum['DocumentsFiled']
        pP = datum['PastProceedings']
        fP = datum['FutureProceedings']
        cR = datum['CrossReferences']
        cH = datum['CaseHistory']
        tT = datum['TentativeRulings']

        case['InternalCaseID'] = icID
        case['date_added'] = dt.now(tz=timezone.utc)
        case['date_updated'] = dt.now(tz=timezone.utc)

        cd = LASC.objects.create(**{key: value for key, value in case.iteritems()})
        cd.save()

        while rOfA:
            r = rOfA.pop()
            r["LASC"] = cd
            RegisterOfActions.objects.create(**{key: value for key, value in r.iteritems()}).save()

        while dI:
            r = dI.pop()
            r["LASC"] = cd
            DocumentImages.objects.create(**{key: value for key, value in r.iteritems()}).save()

        while p:
            r = p.pop()
            r["LASC"] = cd
            Parties.objects.create(**{key: value for key, value in r.iteritems()}).save()

        while dF:
            r = dF.pop()
            r["LASC"] = cd
            DocumentsFiled.objects.create(**{key: value for key, value in r.iteritems()}).save()

        while pP:
            r = pP.pop()
            r["LASC"] = cd
            PastProceedings.objects.create(**{key: value for key, value in r.iteritems()}).save()

        while fP:
            r = fP.pop()
            r["LASC"] = cd
            FutureProceedings.objects.create(**{key: value for key, value in r.iteritems()}).save()

        while cR:
            r = cR.pop()
            r["LASC"] = cd
            CrossReferences.objects.create(**{key: value for key, value in r.iteritems()}).save()

        while cH:
            r = cH.pop()
            r["LASC"] = cd
            CaseHistory.objects.create(**{key: value for key, value in r.iteritems()}).save()

        while tT:
            r = tT.pop()
            r["LASC"] = cd
            TentativeRulings.objects.create(**{key: value for key, value in r.iteritems()}).save()

        logger.info("Saving Data to DB")



    def update_case(options):

        lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        lasc_session.login()

        query = LASCSearch(lasc_session)
        intID = options['case']
        query._get_json_from_internal_case_id(intID)

        datum =  json.loads(query.case_data)['ResultList']

        # lasc_object = LASC.objects.filter(InternalCaseID="19STCV25152;SS;CV")
        # lasc_object = LASC.objects.filter(InternalCaseID="19STCV25155;SS;CV")
        lasc_object = LASC.objects.filter(InternalCaseID=intID)


        roa_count = len(datum[0]['NonCriminalCaseInformation']['RegisterOfActions'])  #found register of actions
        roa_db_count = len(RegisterOfActions.objects.filter(LASC_id=lasc_object[0].id))  #saved register of actions

        docI_count = len(datum[0]['NonCriminalCaseInformation']['DocumentImages'])  #found register of actions
        docI_db_count = len(DocumentImages.objects.filter(LASC_id=lasc_object[0].id))  #saved register of actions

        parties_count = len(datum[0]['NonCriminalCaseInformation']['Parties'])  #found register of actions
        parties_db_count = len(Parties.objects.filter(LASC_id=lasc_object[0].id))  #saved register of actions

        print docI_count, docI_db_count

        if roa_count > roa_db_count:
            for r in datum[0]['NonCriminalCaseInformation']['RegisterOfActions']:

                results = RegisterOfActions.objects.filter(LASC_id=lasc_object[0].id)\
                    .filter(Description=r['Description'])\
                    .filter(RegisterOfActionDateString=r['RegisterOfActionDateString'])

                if results.count() == 0:
                    r['LASC'] = lasc_object[0]
                    ra = RegisterOfActions.objects.create(**{key: value for key, value in r.iteritems()})
                    ra.save()
                else:
                    print results.count(),
                    print "Already have", r['Description']
        else:
            print "same roa's"

        if docI_count > docI_db_count:
            for r in datum[0]['NonCriminalCaseInformation']['DocumentImages']:

                results = DocumentImages.objects.filter(LASC_id=lasc_object[0].id)\
                    .filter(docId=r['docId'])


                if results.count() == 0:
                    r['LASC'] = lasc_object[0]
                    ra = DocumentImages.objects.create(**{key: value for key, value in r.iteritems()})
                    ra.save()
                else:
                    print results.count(),
                    print "Already have", r['docId']

        else:
            print "same doc Images's"

        if parties_count > parties_db_count:
            for r in datum[0]['NonCriminalCaseInformation']['Parties']:
                print "adding ", r['EntityNumber']
                results = Parties.objects.filter(LASC_id=lasc_object[0].id)\
                    .filter(EntityNumber=r['EntityNumber'])


                if results.count() == 0:
                    r['LASC'] = lasc_object[0]
                    ra = Parties.objects.create(**{key: value for key, value in r.iteritems()})
                    ra.save()
                else:
                    print results.count(),
                    print "Already have", r['EntityNumber']

        else:
            print "same parties information"







    def get_pdfs(options):
        """Get PDFs for the results of the Free Document Report queries.

        At this stage, we have rows in the PACERFreeDocumentRow table, each of
        which represents a PDF we need to download and merge into our normal
        tables: Docket, DocketEntry, and RECAPDocument.

        In this function, we iterate over the entire table of results, merge it
        into our normal tables, and then download and extract the PDF.

        :return: None
        """
        pass

    def test(options):

        # for case in LASC.objects.all():
        #     print case.InternalCaseID

        for order in LASC.objects.filter(InternalCaseID="19STCV25152;SS;CV"):
            types = order.registers.values('Description')
            for type in types:
                print type
        # pass

    #
    # def do_ocr(options):
    #     pass
    #

    VALID_ACTIONS = {
        'get-lastweek': get_cases_for_last_week,
        'fill-data': fill_data,
        'update-case': update_case,
        'add-new-case': add_new_case,
        'test': test
    }


