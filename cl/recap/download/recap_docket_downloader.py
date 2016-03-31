#!/usr/bin/env python

import argparse
import re
import urllib2
import csv
import os, sys
# Adding the path to ENV for importing constants.
sys.path.append(os.path.abspath('..'))
from recap_constants import *

from celery import Celery
from celery.registry import tasks
app = Celery('recap_docket_downloader', broker=CELERY_MESSAGE_BROKER)


def get_args():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--docket_csv', type=str, help='A CSV file containing the XML dockets to be downloaded.\n')
    args = arg_parser.parse_args()

    if not args.docket_csv:
        arg_parser.print_help()
    return args

@app.task(bind=True, default_retry_delay=1, max_retries=5)
def downloader (self, recap_download_csv_file_name):

    if recap_download_csv_file_name:
        STATUS_INPROGRESS = STAGE_DOWNLOAD + FILE_IN_PROGRESS
        STATUS_COMPLETE = STAGE_DOWNLOAD + FILE_COMPLETE

        file_timestamp_part = re.search(r'(?P<timestamp>\d+)\.csv$', recap_download_csv_file_name).group('timestamp')
        last_downloaded_file_line = None

        # Checking if there is already a file with 'complete' status.
        # If there is, then all the docket downloads for the input CSV file are complete.
        # Therefore we stop
        completed_csv_filename = "%s%s%s.csv"%(DOWNLOAD_CSV_FILEPATH, file_timestamp_part, STATUS_COMPLETE)
        try:
            completed_csv_file  = open(completed_csv_filename, 'r')
        except IOError:
            pass
        else:
            print " File %s is found with COMPLETE status. Stopping the task."%completed_csv_filename
            sys.exit(1)

        result_csv_filename = "%s%s%s.csv"%(DOWNLOAD_CSV_FILEPATH, file_timestamp_part, STATUS_INPROGRESS)
        try:
            # Try opening the Results CSV file.
            result_csv_file  = open(result_csv_filename, 'r')
        except IOError:
            pass
        else:
            # Going to the last line of the result so that we can continue from there.
            # this is to continue if a task has failed anywhere while downloading dockets.
            # We get the last downloaded docket and continue with the others from there.
            result_csv_reader = csv.reader(result_csv_file, delimiter=',', quotechar='"')
            for csv_line in result_csv_reader:
                if csv_line:
                    last_downloaded_file_line = csv_line
            # Closing the result file after we get the last downloaded file.
            result_csv_file.close()

        with open(recap_download_csv_file_name) as docket_list_file:

            csv_reader = csv.reader(docket_list_file, delimiter=',', quotechar='"')
            if last_downloaded_file_line:

                for docket_name_list in csv_reader:
                    if docket_name_list == last_downloaded_file_line:
                        break

            for row in csv_reader:
                counter, docket_filename = row

                docket_name = re.search('(?P<docketname>(.*))\.docket\.xml', docket_filename).group('docketname')

                # Constructing the IA docket link
                docket_ia_url = IA_XML_DOCKET_PATH_FORMAT_STRING%(docket_name, docket_name)

                # getting the xml file
                xml_response = urllib2.urlopen(docket_ia_url)
                xml_content = xml_response.read()

                #
                docket_xml_filepath = "%s%s"%(XML_DOWNLOAD_FOLDER_PATH, docket_filename)
                with open(docket_xml_filepath, 'w') as docket_file:
                    docket_file.write(xml_content)

                with open(result_csv_filename, 'a') as result_csv_file:
                    result_writer = csv.writer(result_csv_file, delimiter=',', quotechar='"')
                    result_writer.writerow([counter, docket_filename])

        # Renaming the file for status COMPLETE
        os.rename(result_csv_filename, completed_csv_filename)

    return


tasks.register(downloader)

def main():
    args = get_args()
    downloader.delay (recap_download_csv_file_name = args.docket_csv)

if __name__ == '__main__':
    main()




