#!/usr/bin/env python
import sys
import csv
from downloader_constants import *
import recap_docket_downloader



def run_downloader():

    with open(REFERENCE_FILEPATH, 'r') as csv_file:
        reference_reader = csv.reader(csv_file, delimiter = ',', quotechar='"')
        for docket_csv_file_list in reference_reader:
            counter, docket_csv_file = docket_csv_file_list

            recap_docket_downloader.downloader.delay(recap_download_csv_file_name = docket_csv_file)
            with open(REFERENCE_RESULT_FILEPATH, 'a') as csv_result_file:
                download_task_file = csv.writer(csv_result_file, delimiter = ',', quotechar='"')
                download_task_file.writerow([counter, docket_csv_file, STATUS_TASK_ADDED])


if __name__ == '__main__':
    run_downloader()