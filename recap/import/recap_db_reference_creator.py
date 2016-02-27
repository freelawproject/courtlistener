#!/usr/bin/env python

import MySQLdb as database
from recap_constants import *
import time
import csv
import re


def main():
    """
        The RECAP CSV creator
    """
    recap_db_connection = database.connect(host=RECAP_DB_HOST, user=RECAP_DB_USER, passwd=RECAP_DB_PASSWORD,port=RECAP_DB_PORT, db=RECAP_DB_NAME)
    recap_db_cursor = recap_db_connection.cursor()
    sql = "SELECT filename FROM uploads_pickledput WHERE docket=1 LIMIT %s OFFSET %s"
    
    filecount = 0
    csv_lines_count_offset = 0
    while True:
        # Initializing counters
        filecount += 1
        csv_row_count = csv_lines_count_offset+1

        # Constructing the csv filename
        csv_filename = "%s%s.csv"%(CSV_FILEPATH, re.sub('\.', '',"%f" % time.time()))
        sql_args = (MAX_NUMBER_OF_XML_PER_TASK, csv_lines_count_offset)

        if recap_db_cursor.execute(sql, sql_args):
            docket_xml_filenames_tuple_tuple = recap_db_cursor.fetchall()
            
            # Length of the XML file will be used to determine if there are dockets still left in the DB.
            xml_tuple_length = len(docket_xml_filenames_tuple_tuple)
            csv_lines_count_offset += xml_tuple_length
            
            # Creating the CSV file and filling it with Docket XML filenames.
            with open(csv_filename, 'w') as csvfile:
                csvwriter = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                
                for xml_filename_tuple in docket_xml_filenames_tuple_tuple:
                    csvwriter.writerow([str(csv_row_count), xml_filename_tuple[0]])
                    csv_row_count += 1
                
            # Appending to the reference file.
            with open(REFERENCE_FILEPATH, 'a') as file_reference:
                csvwriter = csv.writer(file_reference, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                csvwriter.writerow([str(filecount), csv_filename])
                
        else:
            # db.execute() returns 0 if there are no items in the DB starting form the OFFSET value.
            break
        
        
if __name__ == "__main__":
    main()