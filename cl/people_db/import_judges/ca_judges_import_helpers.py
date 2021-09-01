import json
import os
import re

from django.db import transaction
from django.db.models import Count

from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.lookup_utils import lookup_judge_by_full_name
from cl.people_db.models import Attorney
from cl.people_db.models import AttorneyOrganizationAssociation as AttyOrgAss
from cl.people_db.models import Position, Role
from cl.search.models import Docket


def load_json_file(file_name):
    """Loads Json File

    :param file_name: string
    :return json
    """
    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open(f"{dir_path}/{file_name}") as f:
        deserialized = json.load(f)
    return deserialized


def get_middle_name(last_first_middle_name, first_name, last_name):
    """Extracts middle name from the last_first_middle string

    Given that we have a first name, and a last name, we can
    subtract both of those from the string and return only the
    remaining text.

    The last_first_middle name is the in format of:
    Abbe, John Q.
    Aranda, Benjamin J. III
    Cherniss, Sidney A., Jr.
    Nelson, Mark G., Sr.

    :param last_first_middle_name: string
    :param first_name: string
    :param last_name: string
    :return string
    """

    without_first = last_first_middle_name.replace(first_name, "")
    without_first_and_last = without_first.replace(last_name, "")

    # after first and last name is stripped, what remains is
    # ", G." or ", Dennis"
    regex = re.compile("(?<=\,\s).+$")
    match = regex.search(without_first_and_last)
    if match:
        return match.group()
    else:
        return None


def get_how_selected(jud_exp_pending_status):
    """Maps pending status to the Selection Method Enum

    :param jud_exp_pending_status: string
    :return enum / string
    """

    if jud_exp_pending_status == "Appointed":
        # SELECTION_METHODS['Appointment']
        # need to check to make sure legislatures don't appoint
        # returns 'a_gov' or 'a_legis'
        return Position.APPOINTMENT_GOVERNOR
    elif jud_exp_pending_status == "Elected":
        # SELECTION_METHODS['Election']
        # need to figure out if party or non-party
        # returns 'e_part' or 'e_non_part'
        return Position.ELECTION_NON_PARTISAN


def get_appointer(jud_exp_pending_sub_type):
    """Extracts Appointer Name from the pending sub_type

    :param jud_exp_pending_sub_type: string
    :return string
    """

    # if type is 'Unknown' or 'Board of Supv' or 'Consolidation' or '(Blanks)'
    # or 'Chief Judge' it is an edge case
    edge_cases = [
        "Unknown",
        "Board of Supv",
        "Consolidation",
        "(Blanks)",
        "Chief Judge",
    ]

    if jud_exp_pending_sub_type in edge_cases:
        return ""

    # TODO: LOOKUP APPOINTER FOREIGN KEY
    # search positions for the appointer's name
    # handle stupid multiple "Brown" govs
    return jud_exp_pending_sub_type


# TODO: WRITE THIS FUNCTION
# def get_date_termination_and_termination_reason(position):
# status = position["experienceStatus"]
# reason = position["experienceReason"]
# date = position["experienceStatusEffectiveDate"]
#


def find_judge(lfm, positions, counties):
    """Find Judge in db

    Using the lookup_judge_by_full_name function we can pass in a
    humanname string in the last_first_middle format.

    We thus iterate over the courts, and try to find the judge. If we
    find one, we break and return the judge. If no judge is found, we
    return None

    :param lfm: string
    :param positions: PositionJson[]
    :param counties: CountiesJson {[countyName]: countyAbbreviation}[]
    :return Judge or None
    """

    # iterate over the positions and for each
    courts = []
    judge = None
    for position in positions:
        c = find_court(position, counties)
        if c:
            courts.append(c)
    # find the court id
    # search for the judge
    for court in courts:
        found = lookup_judge_by_full_name(lfm, court)
        if found:
            judge = found
            break
    # if judge exists, break and return the judge
    # else keep going
    # return none if nothing found
    if judge is None:
        logging.info(f"Unable to find a judge for name {lfm}")
    else:
        logging.info(f"Found judge with id {judge.id}")
    return judge


def find_or_create_judge(judgeJson, counties):
    """Find Judge in db

    Check to see if a judge exists by running the find_judge function.
    If no judge is returned, go ahead and create the judge and return
    the Model instance.

    :param judgeJson: JudgeJson
    :param counties: CountiesJson {[countyName]: countyAbbreviation}[]
    :return Judge
    """

    positions = judgeJson["positions"]
    # from the positions, grab the name in the format "last, first middle"
    lfm = positions[0]["lastFirstMiddleName"]
    logging.info(f"Searching for judge with last, first middle {lfm}")
    judge = find_judge(lfm, positions, counties)
    # if no judge, create it
    if judge is None:
        first_position = positions[0]
        name_first = first_position["firstName"]
        name_last = first_position["lastName"]
        name_middle = get_middle_name(lfm, name_first, name_last)
        date_dod = first_position["deceasedDate"]

        logging.info(f"name_first: {name_first}")
        logging.info(f"name_last: {name_last}")
        logging.info(f"name_middle: {name_middle}")
        logging.info(f"date_dod: {date_dod}")

        # judge = Person(
        #   name_first=name_first
        #   name_last=name_last
        #   name_middle=name_middle
        #   date_dod=date_dod
        # )
        # judge.save()

    return judge


def find_court(position, counties):
    """Lookup the court based on the court name and type

    Using the orgType and orgName we search for the corresponding
    court and return the court's pk

    OrgTypes
    Association
    County Counsel
    Court Not CA Judiciary [i.e., Federal]
    Court of Appeal
    JCC Agency
    Justice Court
    Law Firm
    Municipal Court
    Non-Judicial Other
    Superior Court
    Supreme Court

    :param position: PositionJson
    :param counties: CountiesJson
    :return string (court pk)
    """

    org_type = position["orgType"]
    org_name = position["orgName"]

    if re.search(r"Appeal$", org_type):
        # name will be in format
        # Court of Appeal First Appellate District
        # Court of Appeal Fifth Appellate District
        parts = org_name.split(" ")
        lookup = lookup_appellate_court_district(parts[3])
        if lookup:
            return f"calctapp{lookup}d"
        else:
            return
            # throw error

    elif re.search(r"Justice\sCourt", org_type):
        county = lookup_court_abbr(org_name, counties)
        return f"caljustct{county}"

    elif re.search(r"Municipal", org_type):
        county = lookup_court_abbr(org_name, counties)
        return f"calmunct{county}"

    elif re.search(r"Superior\sCourt", org_type):
        county = lookup_court_abbr(org_name, counties)
        return f"calsuppct{county}"

    elif re.search(r"Supreme\sCourt", org_type):
        return "cal"

    # if no court matches, but org_name contains district regex
    # it's a District Federal Court (exact district not provided)
    elif re.search(r"U\.[\s]?S\.\sDistrict", org_name):

        return "district_federal"

    else:
        # TODO: HANDLE EDGE CASES
        return None


def lookup_court_abbr(org_name, counties):
    """Lookup the abbreviation for a county court

    Given an org_name for a court that is county based
    i.e., Municipal, Superior, Justice
    e.g., "Butte Justice Court", "Los Angeles Municipal Court", "Santa Clara Superior Court"
    split by space and if 2nd to last is "Superior" or "Justice" or "Municipal"
    and last is "Court"

    :param org_name: string
    :param counties: CountyJSON
    """

    state_courts = ["Justice", "Municipal", "Superior"]
    parts = org_name.split(" ")
    if parts[-1] == "Court" and parts[-2] in state_courts:
        name_parts = parts[:-2]
        new_name = " ".join(name_parts)
        abbrev = counties[new_name]
        return abbrev


def lookup_appellate_court_district(fourth_word):
    """Get a number from an ordinal

    :param fourth_word: string
    :return string
    """

    appellate_courts = {
        "First": "1",
        "Second": "2",
        "Third": "3",
        "Fourth": "4",
        "Fifth": "5",
        "Sixth": "6",
    }
    lookup = appellate_courts[fourth_word]
    return lookup


# TODO: WRITE THIS FUNCTION
def get_position_type(jobTitle):
    """Map the provided jobTitle string to the Position Type Enum

    :param jobTitle: one of the following possible values:
        Court of Appeal Administrative Presiding Justice
        Court of Appeal Associate Justice
        Court of Appeal Presiding Justice
        Justice Court Judge
        Municipal Court Judge
        Superior Court Assistant Presiding Judge
        Superior Court Judge
        Superior Court Presiding Judge
        Superior Court Supervising Judge
        Supreme Court Associate Justice
        Supreme Court Chief Justice

    :return Position enum / string
    """
