#!/usr/bin/env python

import re, os, sys
import pytz
import csv
import argparse
from django.core.exceptions import ObjectDoesNotExist
from bs4 import BeautifulSoup
from django.utils import timezone
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

# Adding the path to ENV for importing constants.
sys.path.append(os.path.abspath('..'))
sys.path.append(os.path.abspath('../../../'))
from recap_constants import *
from cl.search.models import *
from cl.people_db.models import Position

# Stopwords that appear in the judge names
JUDGE_STOPWORDS_LIST = ['magistrate', 'hon\.', 'honorable', 'justice', 'arj', 'chief', 'prior', 'dissent', 'further'
    ,'page', 'did', 'not', 'sit', 'conferences','submitted'
    ,'participate', 'participation', 'issuance', 'consultation', 'his', 'resul', 'furth', 'even', 'district'
    ,'though', 'argument', 'qualified', 'present', 'majority', 'specially', 'the', 'concurrence', 'initial'
    ,'concurring', 'final', 'may', 'dissenting', 'opinion', 'decision', 'conference', 'this', 'adopted', 'but'
    ,'retired', 'before', 'certified', 'sat', 'oral', 'resigned', 'case', 'member', 'time', 'preparation'
    ,'joined', 'active', 'while', 'order', 'participated', 'was', 'fellows', 'although', 'available'
    ,'authorized', 'continue', 'capacity', 'died', 'panel', 'sitting', 'judge', 'and', 'judges', 'senior', 'justices'
    ,'superior', 'court', 'pro', 'tem', 'participating', 'appeals', 'appellate', 'per', 'curiam', 'presiding'
    ,'supernumerary', 'circuit', 'appellate', 'part', 'division', 'vice', 'result', 'judgment', 'special', 'italic'
    ,'bold', 'denials', 'transfer', 'center', 'with', 'indiana', 'commissioner', 'dissents', 'acting', 'footnote'
    ,'reference', 'concurred']

class DocumentType:
    PACER_DOCUMENT = 1
    ATTACHMENT = 2

class FormatType:
    STRING = 0
    INTEGER = 1
    DATE = 2
    DATETIME = 3
    COURT_OBJ = 4
    JUDGE_OBJ = 5
    BOOLEAN = 6

class DocketSource:
    DEFAULT = 0
    RECAP = 1

def get_args():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--docket_xml', type=str, help='The XML docket file in RECAP/IA to parse\n')
    args = arg_parser.parse_args()

    if not args.docket_xml:
        arg_parser.print_help()
    return args

def get_reformated_value_from_xml(xml_tag, format_type):
    """

    :param xml_tag:
    :param format_type:
    :return:
    """
    return_obj = None
    if format_type == FormatType.COURT_OBJ:
        # Making the court name string mandatory.
        court_abbr = xml_tag.string
        try:
           return_obj = Court.objects.get(id=court_abbr)
        except ObjectDoesNotExist:
            # Returning None in case the Court object is nor found for the RECAP court name
            pass

    elif format_type == FormatType.DATE:
        date_str = xml_tag.string if xml_tag else None
        if date_str:

            return_date = datetime.strptime(date_str, "%Y-%m-%d")
            return_obj = return_date.replace(tzinfo=pytz.utc)

    elif format_type == FormatType.DATETIME:
        date_str = xml_tag.string if xml_tag else None
        if date_str:
            return_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            return_obj = return_date.replace(tzinfo=pytz.utc)

    elif format_type == FormatType.INTEGER:
        item_str = xml_tag.string if xml_tag else None
        if item_str:
            try:
                return_obj = int(item_str)
            except ValueError:
                # Returning None if error found while trying to converting to INT throws error
                pass

    elif format_type == FormatType.STRING:
        return_obj = xml_tag.string if xml_tag else None

    elif format_type == FormatType.BOOLEAN:
        number_val = xml_tag.string if xml_tag else None
        if number_val:
            try:
                return_obj = bool(int(number_val))
            except ValueError:
                # Returning None if error found while trying to converting to INT throws error
                pass

    elif format_type == FormatType.JUDGE_OBJ:
        judge_full_name = xml_tag.string if xml_tag else None
        if judge_full_name:
            # Removing the Noise in the name and making a
            judge_full_name_reformed = re.sub("|".join(map((lambda x : re.sub('^.', "(%s|%s)"%(x[0].upper(), x[0].lower()), x)),JUDGE_STOPWORDS_LIST)), '', judge_full_name).strip()

            if judge_full_name_reformed:
                judge_name_list = judge_full_name_reformed.split()
                return_obj = judge_name_list

    return return_obj


def get_judge_obj(judge_names_list, court_obj, filing_date):

    # Converting all to the lowercase
    lowered_judge_names_list = list(map((lambda x : x.lower()), judge_names_list))
    # Assuming the last string value in the list is that last name.
    judge_lname = lowered_judge_names_list[:-1]

    # Identifying the Judge using combination of last name court and date_start.
    # Last name is used to avoid chances of having nicknames in the First Name
    # Example : 'Bill' instead of 'William', 'Mike' instead of 'Michael'.

    # Filing date is not a mandatory argument. Therefore checking if there is a filing date
    if filing_date:
        judge_pos_qs = Position.objects.filter(person__name_last=judge_lname,
                                               position_type = "Judge",
                                               court=court_obj,
                                               date_start__lte=filing_date)
    else:
        judge_pos_qs = Position.objects.filter(person__name_last=judge_lname,
                                               position_type = "Judge",
                                               court=court_obj)

    judge_obj = None
    if judge_pos_qs:
        judge_pos_list = []
        for judge_pos in judge_pos_qs:
            if judge_pos.date_termination and filing_date:
                if judge_pos.date_termination > filing_date:
                    judge_pos_list.append(judge_pos.judge)
            else:
                judge_pos_list.append(judge_pos.judge)
        # If more than once judge is found. Raise an Exception.
        if judge_pos_list:
            if len(judge_pos_list) > 1:
                raise Exception("Found more than one Judge with Last Name - %s  in the court %s"%(judge_lname, court_obj.id))
            else:
                judge_obj = judge_pos_list[0]

    return judge_obj

def parser(recap_docket_xml_filepath):

    # Getting the docket file name
    # For example: 'gov.uscourts.ilcd.61910'
    docket_url_name = re.search('(?P<docket>gov\.uscourts\.(.*))\.docket', recap_docket_xml_filepath).group('docket')
    # A dictionary to keep a record of unsaved judges
    unsaved_judge_dict = {}

    with open(recap_docket_xml_filepath, 'r') as docket_fp:
        docket_xml_content = docket_fp.read()

    if docket_xml_content:

        soup = BeautifulSoup(docket_xml_content, 'lxml-xml')
        soup_case = soup.case_details

        court_obj = get_reformated_value_from_xml(soup_case.court, FormatType.COURT_OBJ)
        docket_number = get_reformated_value_from_xml(soup_case.docket_num, FormatType.STRING)
        pacer_case_num = get_reformated_value_from_xml(soup_case.pacer_case_num, FormatType.INTEGER)
        date_terminated = get_reformated_value_from_xml(soup_case.date_case_terminated, FormatType.DATE)
        date_last_filing = get_reformated_value_from_xml(soup_case.date_last_filing, FormatType.DATE)
        case_name = get_reformated_value_from_xml(soup_case.case_name, FormatType.STRING)
        date_filed = get_reformated_value_from_xml(soup_case.date_filed, FormatType.DATE)
        case_cause = get_reformated_value_from_xml(soup_case.case_cause, FormatType.STRING)
        nature_of_suit = get_reformated_value_from_xml(soup_case.nature_of_suit, FormatType.STRING)
        jury_demand = get_reformated_value_from_xml(soup_case.jury_demand, FormatType.STRING)
        jurisdiction = get_reformated_value_from_xml(soup_case.jurisdiction, FormatType.STRING)

        # Checking if the mandatory arguments exist
        if None not in (court_obj, pacer_case_num, case_name) :
            # Getting the Judge Object for assigned_to
            assigned_to = None
            judge_names_list = get_reformated_value_from_xml(soup_case.assigned_to, FormatType.JUDGE_OBJ)
            if judge_names_list:
                judge_obj = get_judge_obj(judge_names_list, court_obj, date_filed)
                if judge_obj:
                    assigned_to = judge_obj
                else:
                    unsaved_judge_dict[(' '.join(judge_names_list), court_obj)] = True

            # Getting the Judge Object for referred_to
            referred_to = None
            judge_names_list = get_reformated_value_from_xml(soup_case.referred_to, FormatType.JUDGE_OBJ)
            if judge_names_list:
                judge_obj = get_judge_obj(judge_names_list, court_obj, date_filed)
                if judge_obj:
                    referred_to = judge_obj
                else:
                    unsaved_judge_dict[(' '.join(judge_names_list), court_obj)] = True

            try:
                docket_obj = Docket.objects.get(court=court_obj, pacer_case_id=pacer_case_num)
            except ObjectDoesNotExist:
                try:
                    docket_obj = Docket.objects.get(court=court_obj, docket_number=docket_number)
                except ObjectDoesNotExist:
                    docket_obj = Docket.objects.create(court=court_obj, pacer_case_id=pacer_case_num,
                                                       docket_number=docket_number)
                    # Adding the source as RECAP.
                    docket_obj.source = DocketSource.RECAP
                else:
                    # adding the pacer_case_num id the docket is found without the pacer_case_num (Existing CL dockets)
                    docket_obj.pacer_case_id = pacer_case_num

            # Updating the Docket contents.
            docket_obj.date_filed = date_filed
            docket_obj.date_terminated = date_terminated
            docket_obj.date_last_filing = date_last_filing
            docket_obj.assigned_to = assigned_to
            docket_obj.referred_to = referred_to
            docket_obj.case_name = case_name
            docket_obj.cause = case_cause
            docket_obj.nature_of_suit = nature_of_suit
            docket_obj.jury_demand = jury_demand
            docket_obj.jurisdiction_type = jurisdiction

            # Path of the docket file local as well as in the Internet Archive
            docket_obj.filepath_local = os.path.abspath(recap_docket_xml_filepath)
            # Constructing the Internet Archive Docket File path
            docket_obj.filepath_ia = IA_XML_DOCKET_PATH_FORMAT_STRING % (docket_url_name, docket_url_name)
            docket_obj.save()

            for document_tag in soup.document_list.find_all('document'):
                document_num = int(document_tag['doc_num'])
                attachment_num = int(document_tag['attachment_num'])

                if attachment_num == 0:
                    document_type = DocumentType.PACER_DOCUMENT
                else:
                    document_type = DocumentType.ATTACHMENT

                try:
                    docket_entry_obj = DocketEntry.objects.get(docket=docket_obj, entry_number = document_num)
                except ObjectDoesNotExist:
                    if document_type == DocumentType.PACER_DOCUMENT:
                        docket_entry_obj = DocketEntry(docket=docket_obj, entry_number = document_num)
                    else:
                        raise Exception("ERROR : DocketEntry object does not exist. "
                                        "Attachment found without its associated document")

                if document_type == DocumentType.PACER_DOCUMENT:
                    # Parsing DocketEntry contents in case the document type is PACER_DOCUMENT
                    date_filed = get_reformated_value_from_xml(document_tag.date_filed, FormatType.DATE)
                    docket_entry_text = get_reformated_value_from_xml(document_tag.long_desc, FormatType.STRING)
                    # Updating the DocketEntry object
                    docket_entry_obj.date_filed = date_filed
                    docket_entry_obj.description = docket_entry_text
                    docket_entry_obj.save()

                # Obtaining the document contents.
                pacer_document_id = get_reformated_value_from_xml(document_tag.pacer_doc_id, FormatType.STRING)
                sha1_value = get_reformated_value_from_xml(document_tag.sha1, FormatType.STRING)

                # pacer doc id is made as unique.
                # If SHA1 value is not found, the document won't exist in the Internet Archive.
                # Therefore we skip the document when no pacer_doc_id or SHA1 is not found.
                if not (pacer_document_id and sha1_value):
                    # RECAP does not have a document associated with this docket entry.
                    # Therefore continuing the loop
                    continue
                try:
                    document_obj = RECAPDocument.objects.get(pacer_doc_id=pacer_document_id)
                except ObjectDoesNotExist:
                    document_obj = RECAPDocument(pacer_doc_id=pacer_document_id, docket_entry=docket_entry_obj)

                uploaded_date = get_reformated_value_from_xml(document_tag.upload_date, FormatType.DATETIME)
                is_available = get_reformated_value_from_xml(document_tag.available, FormatType.BOOLEAN)

                filepath_ia = IA_PDF_DOCUMENT_PATH_FORMAT_STRING.format(docket_url_name, document_num, attachment_num)

                # Updating the document object values.
                document_obj.date_upload = uploaded_date
                document_obj.document_type = document_type
                document_obj.document_number = document_num
                document_obj.is_available = is_available
                document_obj.sha1 = sha1_value
                document_obj.filepath_ia = filepath_ia
                if document_type == DocumentType.ATTACHMENT:
                    document_obj.attachment_number = attachment_num
                document_obj.save()

    else:
        raise Exception("Could not read the XML contents")

    return unsaved_judge_dict


if __name__ == '__main__':
    import django
    django.setup()

    args = get_args()
    parser(args.docket_xml)

