#!/usr/bin/env python

import os, sys
import csv
import glob
import logging
import recap_docket_xml_parser

from recap_constants import *
logger = logging.getLogger(__name__)

def add_to_unsaved_judges(unsaved_judges_dict):
    """
        Adds the judge data that is not found in the Person_db database to a CSV file.
        CSV Filename : unsaved_recap_judges.csv
        The CSV filename will have headers:

            Judge Name, Courthouse

    :param judge_fullname: The name of the Judge as found in RECAP Dockets.
    :param court_obj: The Court model object
    :return:
    """
    with open(UNSAVED_JUDGES_FILEPATH, 'w') as judges_fp:
        csv_writer = csv.writer(judges_fp, delimiter=',', quotechar='"')
        csv_writer.writerow(['Judge Name', 'Courthouse'])

        for judge_fullname, court_obj in unsaved_judges_dict.keys():
            csv_writer.writerow([judge_fullname, court_obj.id])

    return

def parser_task_creator():

    # Creating dictionary for fast look up
    parsed_files_dict = {}
    unsaved_judges_dict = {}
    try:
        fp = open(PARSED_FILES_TRACKER_FILEPATH, 'r')
    except IOError:
        pass
    else:
        csv_reader = csv.reader(fp, delimiter=',', quotechar='"')
        for row in csv_reader:
            counter = row[0]
            parsed_filepath = row[1]
            parsed_files_dict[parsed_filepath] = counter

    file_counter = 0
    for docket_filepath in glob.glob(DOWNLOAD_CSV_FILEPATH+"*.xml"):
        file_counter += 1
        try:
            file_parsed = parsed_files_dict[docket_filepath]
        except KeyError:
            logger.info("Parsing Docket : %s."%docket_filepath)
            unsaved_judges_dict.update(recap_docket_xml_parser.parser(docket_filepath))

            with open(PARSED_FILES_TRACKER_FILEPATH, 'a') as fp:
                csv_writer = csv.writer(fp, delimiter=',', quotechar='"')
                csv_writer.writerow([file_counter, docket_filepath ])
        else:
            logger.info("Docket : %s was already parsed."%docket_filepath)
    if unsaved_judges_dict:
         add_to_unsaved_judges(unsaved_judges_dict)






if __name__ == '__main__':
    parser_task_creator()
