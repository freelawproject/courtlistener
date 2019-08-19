import os, sys, argparse, json
from datetime import datetime as dt

from django.conf import settings
from django.core.serializers import serialize as sz
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType


from juriscraper.lasc.http import LASCSession
from juriscraper.lasc.fetch import LASCSearch

from cl.lasc import tasks
from cl.lasc.models import Docket, Proceedings, DocumentImages
from cl.lib.models import LASCJSON, LASCPDF
from cl.lib.command_utils import VerboseCommand, logger


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
            help="T.",
        )

        parser.add_argument(
            '--dir',
            default='/Users/Palin/Desktop/Probate/',
            help="",
        )



    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options['action'](options)


    def get_cases_for_last_week(options):
        """
        This code collects the last weeks worth of new cases and add them to the database.

        :return:
        """

        if "--date" in sys.argv:
            date1 = options['date1']
            date2 = options['date2']
            # query._get_cases_around_dates()

        logger.info("Getting last weeks data.")

        lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        lasc_session.login()

        query = LASCSearch(lasc_session)
        query._get_case_list_for_last_seven_days()
        logger.info("Got data")
        query._parse_date_data()

        datum = query.normalized_date_data
        logger.info("Saving Data to DB")

        for case in datum:
            case_id = case['case_id']
            case_object = Docket.objects.filter(case_id=case_id)
            if not case_object.exists():

                dc = {}
                dc['date_added'] = dt.now(tz=timezone.utc)
                dc['full_data_model'] = False
                dc['case_id'] = case_id

                print case_id

                cd = Docket.objects.create(**{key: value for key, value in dc.iteritems()})
                cd.save()

                logger.info("Finished Adding.")



        logger.info("Finished Saving.")


    def add_case(options):
        """

        :return:
        """

        if "--case" in sys.argv:
            case_id = options['case']
            lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
            lasc_session.login()
            tasks.add_case(lasc_session, case_id)


    def check_out_of_date_case(options):
        """
        # Add options later... for tagged types... clients -- etc

        :return:
        """
        lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        lasc_session.login()

        fmds = Docket.objects.filter(full_data_model=True).order_by('date_checked') #oldest to newest
        print fmds.count()
        for f in fmds:
            print f.date_checked
            tasks.check_case(lasc_session, f.case_id)




    def fill_in_case(options):
        """
        If no case is passed - the tool searches for cases that have yet to be indexed and added to the system.
        :return:
        """

        if "--case" in sys.argv:
            case_id = options['case']
            case_search = Docket.objects.filter(case_id=case_id)
            if case_search.count() == 0:

                logger.info("New Case")

                lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
                lasc_session.login()
                tasks.add_case(lasc_session, case_id)
            else:

                logger.info("%s cases to update" % case_search.count())

                lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
                lasc_session.login()
                query = LASCSearch(lasc_session)

                if tasks.check_hash(query, case_id, case_search[0].case_hash):

                    case = {'date_checked' : dt.now(tz=timezone.utc)}
                    Docket.objects.filter(case_id=case_id).update(**{key: value for key, value in case.iteritems()})
                    logger.info("Case has not Changed, Updating date_checked Value")

                else:

                    logger.info("Changes Detected, Need to update")
                    tasks.update_case(query, case_id)



        else:

            fmds = Docket.objects.filter(full_data_model=False)

            if fmds.count() == 0:
                logger.info("%s cases to update" % fmds.count())

            else:

                logger.info("Updating %s cases." % fmds.count())

                lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
                lasc_session.login()
                for case in fmds:
                    tasks.add_case(lasc_session, case.case_id)



    def test(options):


        if "--case" in sys.argv:
            case_id = options['case']
            """
            code to access filepath of atleast the first object ... maybe all the filepaths
            """

            try:
                dock = Docket.objects.get(case_id=case_id)
                pdfs = DocumentImages.objects.filter(Docket_id=dock.id).filter(downloaded=True)
                for pdf in pdfs:
                    print LASCPDF.objects.filter(object_id=pdf.id)[0].filepath

            except:

                print "docket not found"


            # try:
            #     l = Docket.objects.get(case_id=case_id)
            #     o_id = LASCJSON(content_object=l).object_id
            #     print o_id
            #     x = LASCJSON.objects.get(object_id=o_id)
            #     print x.filepath
            # except:
            #     print "docket not found"


            """
            Code to access the case_id from the file path of the document.
            """
            # docs = JSONFile.objects.all()
            # # print docs.last()
            # print docs[1].content_object.case_id

    def import_wormhole(options):

        if "--dir" in sys.argv:
            dir = options['dir']
            dir = dir + "*.json"
            tasks.import_wormhole_corpus(dir)


    def reset_db(options):
        print('reset db')

        if "--case" in sys.argv:
            case_id = options['case']
            tasks.remove_case(case_id)

        pass

    def get_pdf(options):

        if "--case" in sys.argv:
            case_id = options['case']

            lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
            lasc_session.login()

            tasks.get_pdf(lasc_session, case_id)


        pass

    def get_pdfs(options):

        if "--case" in sys.argv:
            case_id = options['case']

            lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
            lasc_session.login()

            # tasks.get_pdfs(lasc_session, case_id)
            tasks.get_pdfs(lasc_session, case_id)


        pass



    VALID_ACTIONS = {
        'lastweek': get_cases_for_last_week,  #gets ~1k recent filings
        'add-case': add_case, #adds case by case id
        'get-pdf': get_pdf, #adds case by case id
        'get-pdfs': get_pdfs, #adds case by case id
        'out-of-date': check_out_of_date_case,
        'fill-in': fill_in_case,  #fills in cases that are partial
        'test': test,  # fills in cases that are partial
        'wormhole': import_wormhole,  # fills in cases that are partial
        'reset-db': reset_db  # clean the database
    }














