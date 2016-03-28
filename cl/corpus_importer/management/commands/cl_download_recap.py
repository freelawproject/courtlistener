import logging
import os
import pandas as pd
from celery.task import TaskSet
from django.core.management import BaseCommand
from django.conf import settings

from cl.corpus_importer.tasks import download_recap_item
from cl.recap.utils import (
    get_docketxml_url, get_pdf_url, get_document_filename, get_docket_filename
)

CSV_PATH = os.path.join(settings.BASE_DIR, 'cl', 'corpus_importer', 'recap',
                        "document_table.csv")
logger = logging.getLogger(__name__)


def load_csv():
    """Load the CSV data using pandas

    This CSV is generated with:

        mysql recap_prod -p -u recap < export.sql > out.csv

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
    with open(CSV_PATH, 'r') as f:
        line_count = sum(1 for line in f) - 1
    data = pd.read_csv(CSV_PATH, delimiter='\t', dtype={
        'casenum': object,
        'docnum': object,
        'court': object,
    })
    return data, line_count


def make_download_tasks(data, line_count):
    """For every item in the CSV, send it to Celery for processing"""
    previous_casenum = None
    subtasks = []
    completed = 0
    for index, item in data.iterrows():
        last_item = (line_count == completed + 1)
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

        # Every fifty items send the subtasks to Celery.
        if (len(subtasks) >= 50) or last_item:
            msg = ("Sent %s subtasks to celery. We have processed %s "
                   "rows so far." % (len(subtasks), completed))
            logger.info(msg)
            print msg
            job = TaskSet(tasks=subtasks)
            job.apply_async().join()
            subtasks = []

        completed += 1


class Command(BaseCommand):
    help = ('Using a local CSV, download the XML data for RECAP content. '
            'Output is sent to the log.')

    def handle(self, *args, **kwargs):
        data, line_count = load_csv()
        make_download_tasks(data, line_count)
