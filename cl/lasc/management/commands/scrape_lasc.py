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

    @staticmethod
    def add_or_update_case(options):
        """Add a case to the DB by internal case id

        :return: None
        """
        if options['case'] is None:
            print("--case is a required parameter when the add-case action is "
                  "requested.")
        else:
            lasc_session = LASCSession(username=LASC_USERNAME,
                                       password=LASC_PASSWORD)
            lasc_session.login()
            tasks.add_or_update_case(lasc_session, options['case'])

    @staticmethod
    def add_directory(options):
        """Import JSON files from a directory provided at the command line.

        Use glob.globs' to identify JSON files to import.

        :return: None
        """
        if options['directory'] is None:
            print("--directory is a required parameter when the "
                  "'add-directory' action is selected.")
        else:
            tasks.add_cases_from_directory(options['directory-glob'])

    @staticmethod
    def rm_case(options):
        """Delete a case from db

        :return: None
        """
        if options['case'] is None:
            print("--case is a required parameter when the rm-case action is "
                  "requested.")
        else:
            tasks.remove_case(options['case'])

    @staticmethod
    def process_case_queue():
        """Download all cases in case queue

        :return: None
        """
        lasc_session = LASCSession(username=LASC_USERNAME,
                                   password=LASC_PASSWORD)
        lasc_session.login()
        tasks.process_case_queue(lasc_session=lasc_session)

    @staticmethod
    def process_pdf_queue():
        """Download all PDFs in queue

        :return: None
        """
        lasc_session = LASCSession(username=LASC_USERNAME,
                                   password=LASC_PASSWORD)
        lasc_session.login()
        tasks.process_pdf_queue(lasc_session=lasc_session)

    VALID_ACTIONS = {
        'get-cases-by-date': date_search,
        'add-or-update-case': add_or_update_case,
        'add-directory': add_directory,
        'rm-case': rm_case,
        'process-case-queue': process_case_queue,
        'process-pdf-queue': process_pdf_queue,
    }
