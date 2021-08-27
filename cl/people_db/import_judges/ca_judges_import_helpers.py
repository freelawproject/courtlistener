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
    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open(f"{dir_path}/{file_name}") as f:
        deserialized = json.load(f)
    return deserialized


def get_middle_name(last_first_middle_name, first_name, last_name):
    # lfm in format of Abbe, John Q.
    # Aranda, Benjamin J. III
    # Cherniss, Sidney A., Jr.
    # Nelson, Mark G., Sr.
    # replace first and last names with empty strings
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

    return jud_exp_pending_sub_type


# def get_termination_date_and_reason(position):
# status = position["experienceStatus"]
# reason = position["experienceReason"]
# date = position["experienceStatusEffectiveDate"]
#


def find_judge(lfm, positions, counties):
    # from the positions, grab the name in the format "last, first middle"

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
        print(f"Unable to find a judge for name {lfm}")
    else:
        print(f"Found judge with id {judge.id}")
    return judge


def find_or_create_judge(judgeJson, counties):
    positions = judgeJson["positions"]
    # from the positions, grab the name in the format "last, first middle"
    lfm = positions[0]["lastFirstMiddleName"]
    print(f"Searching for judge with last, first middle {lfm}")
    judge = find_judge(lfm, positions, counties)
    # if no judge, create it
    if judge is None:
        first_position = positions[0]
        name_first = first_position["firstName"]
        name_last = first_position["lastName"]
        name_middle = get_middle_name(lfm, name_first, name_last)
        date_dod = first_position["deceasedDate"]

        print(f"name_first: {name_first}")
        print(f"name_last: {name_last}")
        print(f"name_middle: {name_middle}")
        print(f"date_dod: {date_dod}")

        # judge = Person(
        #   name_first=name_first
        #   name_last=name_last
        #   name_middle=name_middle
        #   date_dod=date_dod
        # )
        # judge.save()

    return judge


# def parse_name(last_first_middle, first, last):
# examples

# Lookup court by name
def find_court(position, counties):
    # Association
    # County Counsel
    # Court Not CA Judiciary [i.e., Federal]
    # Court of Appeal
    # JCC Agency
    # Justice Court
    # Law Firm
    # Municipal Court
    # Non-Judicial Other
    # Superior Court
    # Supreme Court

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


# given an org_name for a court that is county based
# i.e., Municipal, Superior, Justice
# e.g., "Butte Justice Court", "Los Angeles Municipal Court", "Santa Clara Superior Court"
# split by space and if 2nd to last is "Superior" or "Justice" or "Municipal"
# and last is "Court"
# find the corresponding court in the abbreviations
def lookup_court_abbr(org_name, counties):
    state_courts = ["Justice", "Municipal", "Superior"]
    parts = org_name.split(" ")
    if parts[-1] == "Court" and parts[-2] in state_courts:
        name_parts = parts[:-2]
        new_name = " ".join(name_parts)
        abbrev = counties[new_name]
        return abbrev


def lookup_appellate_court_district(fourth_word):
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


"""
  Shape of Loaded File JSON
  {
    count: string,
    judges: Judge[]
  }
"""

"""
  Shape of Judge JSON
  {
    fullName: string
    positions: Position[]
  }
"""

"""
  Shape of Position JSON
  All properties are strings
  {
    id,
    salutation,
    jobTitle,
    title,
    fullName,
    lastFirstMiddleName,
    firstName,
    lastName,
    judicialIndicator,
    orgType,
    orgName,
    orgDivision,
    experienceStatus,
    experienceStatusReason,
    experienceStatusEffectiveDate,
    expId,
    barAdmissionDate,
    deceasedDate,
    judicialPositionId,
    judicialPositionJobClass,
    judicialPositionJobTitle,
    judicialPositionOrgType,
    judicialPositionOrgName,
    judicialPositionLocationName,
    judicialExperienceDivsionName,
    judicialPositionOrgCounty,
    judicialPositionActiveDate,
    judicialPositionInactiveDate,
    judicialExperiencePendingStatus,
    judicialExperiencePendingSubType,
    JudicialExperienceInactiveStatus,
    judicialExperienceAppointmentDate,
    judicialExperienceActiveDate,
    judicialExperienceInactiveDate,
    judicialExperienceTermEndDate,
  }
"""
