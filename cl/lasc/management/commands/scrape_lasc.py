# coding=utf-8

import os, sys, argparse
from django.conf import settings
from juriscraper.lasc.http import LASCSession
from cl.lasc import tasks
from cl.lib.command_utils import VerboseCommand, logger
from dateutil.rrule import rrule, WEEKLY
import datetime

LASC_USERNAME = os.environ.get('LASC_USERNAME', settings.LASC_USERNAME)
LASC_PASSWORD = os.environ.get('LASC_PASSWORD', settings.LASC_PASSWORD)


class Command(VerboseCommand):
    help = "Get all content from MAP LA Unlimited Civil Cases."

    def valid_actions(self, s):

        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s" % (
                    ', '.join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        import datetime
        dt = datetime.datetime.today()
        minus_seven = datetime.timedelta(days=-7)
        start = (dt + minus_seven).strftime('%m/%d/%Y')
        end = (dt).strftime('%m/%d/%Y')

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
            '--count',
            default=0,
            help="Number of cases to collect",
        )
        parser.add_argument(
            '--dir',
            default='/Users/Palin/Desktop/Probate/',
            help="",
        )
        parser.add_argument(
            '--start',
            default=start,
            help="Start Date",
        )
        parser.add_argument(
            '--end',
            default=end,
            help="End Date",
        )




    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options['action'](options)


    def date_search(options):
        """
        This code collects the last weeks worth of new cases,
         and add them to the db.

         --start mm/dd/yyyy format -- default one week ago
         --end mm/dd/yyyy format -- default today

        :return:
        """

        logger.info("Getting last 7 days worth of cases.")

        s = datetime.datetime.strptime(options['start'], '%m/%d/%Y')
        e = datetime.datetime.strptime(options['end'], '%m/%d/%Y')
        dt = datetime.datetime.today()

        dates = ["/".join([x.strftime('%m-%d-%Y'),
                       (x + datetime.timedelta(days=7))
                      .strftime('%m-%d-%Y')]) for x in list(rrule(freq=WEEKLY,
                                                                  dtstart=s,
                                                                  until=e))
                        if x.strftime('%m-%d-%Y') != dt.strftime('%m-%d-%Y')]

        sess = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        sess.login()
        for daterange in dates:
            logger.info(daterange)
            tasks.fetch_last_week(sess=sess, daterange=daterange)



    def add_case(options):
        """
        Adds case to db by internal case id
        {docket_number}.
        :return:
        """

        if "--case" in sys.argv:
            case_id = options['case']
            lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
            lasc_session.login()
            tasks.add_case(lasc_session, case_id)


    def import_wormhole(options):

        """
        Wormhole refers to how we shared data.
        The code needs an directory wildcard to run.  It then glob.globs' the
        partial directory and generates a list of cases to import.

        :return:
        """

        if "--dir" in sys.argv:
            dir = options['dir']

            dir = dir + "*.json"
            tasks.import_wormhole_corpus(dir)

    def reset_db(options):
        """
        Deletes case from db
        :return:
        """

        if "--case" in sys.argv:
            case_id = options['case']
            tasks.remove_case(case_id)


    def case_queue(options):
        """
        Finds all cases in case queue
        :return:
        """
        count = int(options['count'])
        tasks.case_queue(count=count)



    def pdf_queue(self):
        """
        Pulls all pdfs in queue
        :return:
        """

        lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        lasc_session.login()
        tasks.pdf_queue(sess=lasc_session)


    VALID_ACTIONS = {
        'date': date_search,  #gets ~1k recent filings
        'add-case': add_case, #adds case by case id
        'reset-db': reset_db,  # clean the database of the case
        'case-queue': case_queue,
        'pdf-queue': pdf_queue,
        'wormhole': import_wormhole,  # fills in cases that are partial
    }
