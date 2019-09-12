# coding=utf-8

import argparse
import os

from datetime import datetime
from datetime import timedelta
from django.conf import settings
from juriscraper.lasc.http import LASCSession

from cl.lasc import tasks
from cl.lib.argparse_types import valid_date
from cl.lib.command_utils import VerboseCommand, logger

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

        # Action-specific parameters
        parser.add_argument(
            '--case',
            help="A case that you want to download when using the add-case "
                 "action. For example, '19STCV25157;SS;CV'",
        )
        parser.add_argument(
            '--directory-glob',
            help="A directory glob to use when importing bulk JSON files, for "
                 "example, '/home/you/bulk-data/*.json'",
        )

        today = datetime.today()
        start = today - timedelta(days=7)
        parser.add_argument(
            '--start',
            default=start,
            type=valid_date,
            help="Start Date",
        )
        parser.add_argument(
            '--end',
            default=today,
            type=valid_date,
            help="End Date",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options['action'](options)

    @staticmethod
    def date_search(options):
        """
        Collect a list of cases from a date range and add them to the db.

        :return: None
        """
        lasc_session = LASCSession(username=LASC_USERNAME,
                                   password=LASC_PASSWORD)
        lasc_session.login()
        start = options['start']
        end = options['end']
        logger.info("Getting cases between %s and %s, inclusive", start, end)
        tasks.fetch_case_list_by_date(lasc_session, start, end)



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


    def case_queue(self):
        """
        Finds all cases in case queue
        :return:
        """
        lasc_session = LASCSession(username=LASC_USERNAME, password=LASC_PASSWORD)
        lasc_session.login()
        tasks.case_queue(sess=lasc_session)

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
