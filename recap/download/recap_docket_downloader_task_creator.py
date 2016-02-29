#!/usr/bin/env python
import os, sys
import csv
# Adding the path to ENV for importing constants.
sys.path.append(os.path.abspath('..'))
from recap_constants import *
import recap_docket_downloader



def run_downloader():

    with open(DOWNLOAD_REFERENCE_FILEPATH, 'r') as csv_file:
        reference_reader = csv.reader(csv_file, delimiter = ',', quotechar='"')
        for docket_csv_file_list in reference_reader:
            counter, docket_csv_file = docket_csv_file_list

            recap_docket_downloader.downloader.delay(recap_download_csv_file_name = docket_csv_file)
            with open(DOWNLOAD_REFERENCE_RESULT_FILEPATH, 'a') as csv_result_file:
                download_task_file = csv.writer(csv_result_file, delimiter = ',', quotechar='"')
                download_task_file.writerow([counter, docket_csv_file, STATUS_TASK_ADDED])


if __name__ == '__main__':
    run_downloader()

