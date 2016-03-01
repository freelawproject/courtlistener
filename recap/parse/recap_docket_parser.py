#!/usr/bin/env python

from django.core.exceptions import ObjectDoesNotExist
from bs4 import BeautifulSoup
from datetime import datetime
# Adding the path to ENV for importing constants.
sys.path.append(os.path.abspath('..'))
from recap_constants import *
from cl.search.models import *
from cl.judges.models import Judge

class DocumentType:
    PACER_DOCUMENT = 1
    ATTACHMENT = 2

class FormatType:
    STRING = 0
    INTEGER = 1
    DATETIME = 2
    COURT_OBJ = 3
    JUDGE_OBJ = 4


def get_args():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--docket_xml', type=str, help='The XML docket file in RECAP/IA to parse\n')
    args = arg_parser.parse_args()

    if not args.docket_csv:
        arg_parser.print_help()
    return args

def get_reformated_value_from_xml(xml_tag, format_type):
    """

    :param xml_tag: the XML tag
    :param format_type: Teh format to which the XML tag needs to be converted
    :return return_obj: The converted form of the item
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

    elif format_type == FormatType.DATETIME:
        date_str = xml_tag.string if xml_tag else None
        if date_str:
            return_obj = datetime.strptime(date_str, "%Y-%m-%d")

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

    elif format_type == FormatType.JUDGE_OBJ:
        pass
        # Judge yet to be done because of the

    return return_obj

def parser(recap_docket_xml_filepath):

    docket_xml_content = None
    with open(recap_docket_xml_filepath, 'r') as docket_fp:
        docket_xml_content = docket_fp.read()

    if docket_xml_content:
        soup = BeautifulSoup(docket_xml_content)
        soup_case = soup.case_details

        court_obj = get_reformated_value_from_xml(soup_case.court, FormatType.COURT_OBJ)
        docket_number = get_reformated_value_from_xml(soup_case.docket_num, FormatType.STRING)
        pacer_case_num = get_reformated_value_from_xml(soup_case.pacer_case_num, FormatType.INTEGER)
        date_terminated = get_reformated_value_from_xml(soup_case.date_case_terminated. FormatType.DATETIME)
        case_name = get_reformated_value_from_xml(soup_case.case_name, FormatType.STRING)
        date_filed = get_reformated_value_from_xml(soup_case.date_filed, FormatType.DATETIME)
        case_cause = get_reformated_value_from_xml(soup_case.case_cause, FormatType.STRING)
        nature_of_suit = get_reformated_value_from_xml(soup_case.nature_of_suit, FormatType.STRING)
        jury_demand = get_reformated_value_from_xml(soup_case.jury_demand, FormatType.STRING)
        jurisdiction = get_reformated_value_from_xml(soup_case.jurisdiction, FormatType.STRING)
        # 'assigned_to' has to be implemented - PENDING


        try:
            docket_obj = Docket.objects.get(court=court_obj, docket_number=docket_number)
        except ObjectDoesNotExist:
            try:
                docket_obj = Docket.objects.get(court=court_obj, pacer_case_id=pacer_case_num)
            except ObjectDoesNotExist:
                docket_obj = Docket.objects.create(court=court_obj, pacer_case_id=pacer_case_num)

        for document_tag in soup.document_list.find_all('document'):
            document_number = int(document_tag['doc_num'])
            attachment_num = int(document_tag['attachment_num'])

            if attachment_num == 0:
                document_type = DocumentType.PACER_DOCUMENT
            else:
                document_type = DocumentType.ATTACHMENT

            if document_type == DocumentType.PACER_DOCUMENT:
                 try:
                     DocketEntry.objects.get(docket=)




    else:
        raise Exception("Could not read the XML contents")
