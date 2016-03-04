#!/usr/bin/env python
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'cl.settings'
import django
django.setup()
from django.conf import settings


# change these to connect to the RECAP Database.
RECAP_DB_USER = 'recap'
RECAP_DB_PASSWORD = 'recapthelaw'
RECAP_DB_HOST = 'localhost'
RECAP_DB_PORT = 3306
RECAP_DB_NAME = 'recap_dev'

# The Message Broker for celery jobs
CELERY_MESSAGE_BROKER = 'redis://localhost'

# Stages in the initial process
STAGE_DOWNLOAD = '_download'
STAGE_PARSE = '_parse'
STAGE_INDEX = '_index'

# File/Process Status
FILE_IN_PROGRESS = "_in_progress"
FILE_COMPLETE = "_complete"

STATUS_TASK_ADDED  = 'TASK ADDED'

# Creating an independent file path
DOWNLOAD_CSV_FILEPATH = "%s/recap/"%settings.MEDIA_ROOT

DOWNLOAD_REFERENCE_FILEPATH = DOWNLOAD_CSV_FILEPATH + "recap_csv_file_reference.csv"
DOWNLOAD_REFERENCE_RESULT_FILEPATH = DOWNLOAD_CSV_FILEPATH + "recap_csv_file_reference_results.csv"
DOWNLOAD_MAX_XML_PER_TASK = 100000

PARSED_FILES_TRACKER_FILEPATH = DOWNLOAD_CSV_FILEPATH + "parsed_files_tracker.csv"

IA_URL_PREFIX = "https://archive.org/download/"
IA_XML_DOCKET_PATH_FORMAT_STRING = IA_URL_PREFIX + "%s/%s.docket.xml"
IA_PDF_DOCUMENT_PATH_FORMAT_STRING = IA_URL_PREFIX + "{0}/{0}.{1}.{2}.pdf"
XML_DOWNLOAD_FOLDER_PATH = DOWNLOAD_CSV_FILEPATH
