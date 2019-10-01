# coding=utf-8

import argparse
from glob import glob

from datetime import datetime
from datetime import timedelta

from juriscraper.lib.date_utils import make_date_range_tuples

from cl.lasc import tasks
from cl.lib.argparse_types import valid_date
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger

from cl.lasc.models import QueuedCase, QueuedPDF


def date_search(options):
    """Collects a list of cases from a date range and adds them to the db.

    :return: None
    """
    start = options['start']
    end = options['end']
    logger.info("Getting cases between %s and %s, inclusive", start, end)

    end = min(end, datetime.today())
    date_ranges = make_date_range_tuples(start, end, gap=7)
    for start, end in date_ranges:
        tasks.fetch_date_range.apply_async(kwargs={"start": start, "end": end},
                                           queue=options['queue'])


def add_or_update_case(options):
    """Adds a case to the DB by internal case id

    :return: None
    """
    if options['case'] is None:
        print("--case is a required parameter when the add-case action is "
              "requested.")
    else:
        tasks.add_or_update_case_db.apply_async(
            kwargs={"case_id": options['case']},
            queue=options['queue'],
        )


def add_directory(options):
    """Import JSON files from a directory provided at the command line.

    Use glob.globs' to identify JSON files to import.

    :return: None
    """
    dir_glob = options['directory_glob']
    skip_until = options['skip_until']
    if dir_glob is None:
        print("--directory-glob is a required parameter when the "
              "'add-directory' action is selected.")
    else:
        dir_glob = options['directory_glob']
        fps = sorted(glob(dir_glob))
        if skip_until:
            # Remove items from the list until the skip_until value is hit.
            try:
                skip_index = fps.index(skip_until)
                fps = fps[skip_index:]
            except ValueError:
                logger.error("Unable to find '%s' in directory_glob: '%s'. "
                             "The first few items of the glob look like: \n  "
                             "%s", skip_until, dir_glob, '\n  '.join(fps[0:3]))
                raise

        q = options['queue']
        throttle = CeleryThrottle(queue_name=q)
        for fp in fps:
            throttle.maybe_wait()
            logger.info("Adding LASC JSON file at: %s", fp)
            tasks.add_case_from_filepath.apply_async(kwargs={"filepath": fp},
                                                     queue=q)


def process_case_queue(options):
    """
    Work through the queue of cases that need to be added to the database,
    and add them one by one.

    :return: None
    """
    case_ids = QueuedCase.objects.all().values_list(
        'internal_case_id', flat=True)
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for case_id in case_ids:
        throttle.maybe_wait()
        tasks.add_or_update_case_db.apply_async(kwargs={"case_id": case_id},
                                                queue=q)


def process_pdf_queue(options):
    """Download all PDFs in queue

    Work through the queue of PDFs that need to be added to the database,
    download them and add them one by one.

    :return: None
    """
    pdf_pks = QueuedPDF.objects.all().values_list('pk', flat=True)
    q = options['queue']
    throttle = CeleryThrottle(queue_name=q)
    for pdf_pk in pdf_pks:
        throttle.maybe_wait()
        tasks.download_pdf.apply_async(kwargs={"pdf_pk": pdf_pk},
                                       queue=q)


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
                 "example, '/home/you/bulk-data/*.json'. Note that to avoid "
                 "the shell interpreting the glob, you'll want to put it in "
                 "single quotes.",
        )
        parser.add_argument(
            '--skip-until',
            type=str,
            help="When using --directory-glob, skip processing until an item "
                 "at this location is encountered. Use a path comparable to "
                 "that passed to --directory-glob.",
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

    VALID_ACTIONS = {
        'add-cases-by-date': date_search,
        'add-or-update-case': add_or_update_case,
        'add-directory': add_directory,
        'process-case-queue': process_case_queue,
        'process-pdf-queue': process_pdf_queue,
    }
