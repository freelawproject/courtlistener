import pandas as pd
from celery.task import TaskSet

from cl.corpus_importer.tasks import download_recap_item
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.recap_utils import (
    get_docketxml_url, get_pdf_url, get_document_filename, get_docket_filename
)


def load_csv(csv_location):
    """Load the CSV data using pandas

    This CSV is generated with:

        mysql recap_prod -p -u recap < export.sql > out.csv

        or

        mysql recap_prod -p -u recap < export_latest.sql > out.csv

    export.sql contains:

        SELECT
            court, casenum, docnum, subdocnum, modified
        FROM
            uploads_document
        ORDER BY
            casenum
        WHERE
            available = 1;

    The resulting file is tab separated, and pandas will handle that just fine.
    """
    data = pd.read_csv(csv_location, delimiter='\t', dtype={
        'casenum': object,
        'docnum': object,
        'court': object,
    })
    return data, len(data.index)


def make_download_tasks(data, line_count, start_line):
    """For every item in the CSV, send it to Celery for processing"""
    previous_casenum = None
    subtasks = []
    completed = 0
    for index, item in data.iterrows():
        if completed < start_line - 1:
            # Skip ahead if start_lines is provided.
            completed += 1
            continue

        if item['casenum'] != previous_casenum:
            # New case, get the docket before getting the pdf
            logger.info("New docket found with casenum: %s" % item['casenum'])
            previous_casenum = item['casenum']
            filename = get_docket_filename(item['court'], item['casenum'])
            url = get_docketxml_url(item['court'], item['casenum'])
            subtasks.append(download_recap_item.subtask((url, filename)))

        # Get the document
        filename = get_document_filename(item['court'], item['casenum'],
                                         item['docnum'], item['subdocnum'])
        url = get_pdf_url(item['court'], item['casenum'], filename)
        subtasks.append(download_recap_item.subtask((url, filename)))

        # Every n items or on the last item, send the subtasks to Celery.
        last_item = (line_count == completed + 1)
        if (len(subtasks) >= 1000) or last_item:
            msg = ("Sent %s subtasks to celery. We have processed %s "
                   "rows so far." % (len(subtasks), completed + 1))
            logger.info(msg)
            job = TaskSet(tasks=subtasks)
            job.apply_async().join()
            subtasks = []

        completed += 1


class Command(VerboseCommand):
    help = ('Using a local CSV, download the XML data for RECAP content. '
            'Output is sent to the log.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--start_line',
            type=int,
            default=0,
            help='The line in the file where you wish to start processing.'
        )
        parser.add_argument(
            '--download_csv',
            required=True,
            help="The absolute path to the CSV containing the list of items "
                 "to download.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        data, line_count = load_csv(options['download_csv'])
        make_download_tasks(data, line_count, options['start_line'])
