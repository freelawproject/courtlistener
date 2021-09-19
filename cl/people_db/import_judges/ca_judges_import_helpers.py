import logging
import json
import logging
import os
import re
from datetime import date
from typing import List, Optional, Union

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Count, Q
from nameparser import HumanName

from cl.people_db.models import Person, Position, Role
from cl.search.models import Court


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
    """Extracts Appointer Position FK from the pending sub_type

    :param jud_exp_pending_sub_type: string
        # Edge cases
        "Board of Supv",
        "Unknown",
        "Consolidation",
        "(Blanks)",
        "Chief Justice", (For "Administrative Presiding Justice[s]"),
        "Lucas", (Maybe Malcom Lucas, Chief Justice of Cal SCOTUS)

        # Govs
        "Rolph",
        "Olson",
        "Warren",
        "Knight",
        "Brown",
        "Reagan",
        "Brown Jr.",
        "Deukmejian",
        "Wilson",
        "Davis",
        "Schwarzenegger",
        "Newsom"

    :return string | None
    """
    appointer_pos_fk = None

    name_to_cl_id = {
        "Rolph": "cal-gov-27",
        "Olson": "cal-gov-29",
        "Warren": "fjc-0420",
        "Knight": "cal-gov-31",
        "Brown": "cal-gov-32",
        "Reagan": "pres-038",
        "Brown, Jr.": "cal-gov-34",
        "Deukmejian": "cal-gov-35",
        "Wilson": "cal-gov-36",
        "Davis": "cal-gov-37",
        "Schwarzenegger": "cal-gov-38",
        "Newsom": "cal-gov-40",
    }

    cl_id = name_to_cl_id.get(jud_exp_pending_sub_type)

    if cl_id:
        person = Person(cl_id=cl_id)
        all_positions = person.positions.all()
        for position in all_positions:
            if position.position_type == Position.GOVERNOR:
                appointer_pos_fk = position.pk

    return appointer_pos_fk


def get_termination_reason(status):
    """Convert inactive status reason to TERMINATION_REASONS enum

    :param status - one of
        Deceased
        Defeated
        Non-Voluntary
        Other
        Promoted
        Resigned
        Retired
        Term Ended
        Transferred
        [Blank]

    :return enum | None
    """

    status_to_enum = {
        "Deceased": "ded",
        "Defeated": "lost",
        "Non-Voluntary": "retire_mand",
        "Promoted": "other_pos",
        "Resigned": "resign",
        "Retired": "retire_vol",
        "Term Ended": "termed_out",
        "Transferred": "other_pos",
    }
    return status_to_enum.get(status)


def find_judge(lfm, positions, counties):
    """Find Judge in db

    Using the lookup_judge_by_full_name function we can pass in a
    humanname string in the last_first_middle format.

    We search for a match of first, middle, or last and

    :param lfm: string
    :param positions: PositionJson[]
    :param counties: CountiesJson {[countyName]: countyAbbreviation}[]
    :return Judge or None
    """

    judge = None
    for position in positions:
        date_text = position["judicialExperienceActiveDate"]
        event_date = validate_string_date(date_text)
        found = lookup_judge_by_full_name(lfm, event_date)
        if found:
            judge = found
            break
    if judge is not None:
        logging.info(f"Found judge with id {judge.id}")
    return judge


def validate_string_date(date_text):
    """returns either a datetime object or None

    try to parse the date_text. Return None if not valid

    :param date_text
    :returns datetime object | None
    """
    date_obj = None
    if date_text != "":
        try:
            date_obj = parse(date_text)
        except ValueError:
            logging.info("Deceased Date {date_text} not a valid date")
    return date_obj


def find_or_create_judge(judgeJson, counties, index):
    """Find Judge in db

    Check to see if a judge exists by running the find_judge function.
    If no judge is returned, go ahead and create the judge and return
    the Model instance.

    :param judgeJson: JudgeJson
    :param counties: CountiesJson {[countyName]: countyAbbreviation}[]
    :param index (for the cl_id)
    :return Judge
    """

    positions = judgeJson["positions"]

    first_position = positions[0]

    name_first = first_position["firstName"]
    name_last = first_position["lastName"]
    lfm = first_position["lastFirstMiddleName"]

    logging.info(f"Searching for judge with last, first middle {lfm}")
    judge = find_judge(lfm, positions, counties)
    # if no judge, create it
    if judge is None:
        logging.info("No judge found. Creating ...")

        judge_info = {
            # start at 00001
            "cl_id": f"cal-jud-{format(index + 1, '05d')}",
            "name_first": name_first,
            "name_last": name_last,
        }

        name_middle = get_middle_name(lfm, name_first, name_last)

        if name_middle:
            judge_info["name_middle"] = name_middle

        # deceased date in format of 09/04/2000
        date_dod = validate_string_date(first_position["deceasedDate"])
        if date_dod:
            judge_info["date_dod"] = date_dod.strftime("%Y-%m-%d")
            judge_info["date_granularity_dod"] = "%Y-%m-%d"

        logging.info(f"Judge info %s", json.dumps(judge_info))
        judge = Person.objects.create(**judge_info)

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

    # If the orgType is "Court Not CA Judiciary" it's
    # a Federal District Court Position
    # for either "Lucy Koh" or "Gary Austin"
    # whose District Court positions are already in
    # the database, so re return None
    if re.search(r"Court\sNot\sCA", org_type):
        return None

    elif re.search(r"Appeal$", org_type):
        # name will be in format
        # Court of Appeal First Appellate District
        # Court of Appeal Fifth Appellate District
        appellate_court_districts = {
            "First": "1",
            "Second": "2",
            "Third": "3",
            "Fourth": "4",
            "Fifth": "5",
            "Sixth": "6",
        }
        name_parts = org_name.split(" ")
        abbrev = appellate_court_districts.get(name_parts[3])
        if abbrev:
            return Court(id=f"calctapp{abbrev}d")
        else:
            raise Exception("Invalid appellate court name: {org_name}}")

    elif re.search(r"Justice\sCourt", org_type):
        county = lookup_court_abbr(org_name, counties)
        return Court(id=f"caljustct{county}")

    elif re.search(r"Municipal", org_type):
        county = lookup_court_abbr(org_name, counties)
        return Court(id=f"calmunct{county}")

    elif re.search(r"Superior\sCourt", org_type):
        county = lookup_court_abbr(org_name, counties)
        return Court(id=f"calsuppct{county}")

    elif re.search(r"Supreme\sCourt", org_type):
        return Court(id="cal")

    elif re.search(r"Association", org_type):
        # TODO
        # The edge case "Association" has two entries,
        # both for "B. Tam Nomoto Schumann" who was
        # "promoted" to "Superior Court" in 1997 and who
        # "retired" in 2013
        return None

    elif re.search(r"County\sCounsel", org_type):
        # TODO
        # The edge case "County Counsel" has one entry
        # for "Dennis W. Bunting" who "retired" from his
        # Superior Court Post in Solano County in 1994
        return None

    elif re.search(r"JCC\sAgency", org_type):
        # TODO
        # The edge case "JCC Agency" has three entries
        # all for "Leonard P. Edwards" who served as a
        # Municipal Court Judge in Santa Clara until 09/1981,
        # when he was was "promoted" to Superior Court Judge
        # for Santa Clara County, and who "retired" in 2006
        return None

    elif re.search(r"Law\sFirm", org_type):
        # TODO
        # The edge case "Law Firm" has one entry for
        # "Elaine M. Rushing" who "retired" from her post
        # as a Superior Court Judge for Sonomy County in 2011
        return None

    elif re.search(r"Non-Judicial", org_type):
        # TODO
        # The edge case "Non-Judicial Other" has eight entries
        # Four are for "Candace D. Cooper"
        # Was to "Municipal LA County Judge" prior to 1987
        # "Promoted" to Superior LA County Judge in 1987
        # "Promoted" to Court of Appeals District 2 in 1999
        # "Transferred" to Court of Appeals District 4 in 2001

        # One for "Judith C. Chirlin"
        # She "retired" from the Superior Court for LA County in 2009

        # Three for "Jamie A. Jacobs-May"
        # Was Municipal Court for Santa Clara from 89 on
        # "Non-Volunary" became a Superior Court judge (due to merger) in 1998
        # "Selected" as "Presiding Judge" in 2009
        # "Retired" in 2010
        return None

    else:
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

    :return enum \ None
    """

    if re.search(r"^Court of Appeal", jobTitle):

        if re.search(r"Administrative\sPresiding\sJustice", jobTitle):
            return Position.ADMINISTRATIVE_PRESIDING_JUSTICE

        elif re.search(r"Presiding\sJustice", jobTitle):
            return Position.PRESIDING_JUSTICE

        elif re.search(r"Associate\sJustice", jobTitle):
            return Position.ASSOCIATE_JUSTICE

    elif re.search(r"^Supreme\sCourt", jobTitle):

        if re.search(r"Associate", jobTitle):
            return Position.ASSOCIATE_JUSTICE

        elif re.search(r"Chief", jobTitle):
            return Position.CHIEF_JUSTICE

    elif re.search(r"^Superior\sCourt", jobTitle):

        if re.search(r"Supervising", jobTitle):
            return Position.SUPERVISING_JUDGE

        elif re.search(r"Assistant\sPresiding", jobTitle):
            return Position.ASSISTANT_PRESIDING_JUDGE

        elif re.search(r"Presiding", jobTitle):
            return Position.PRESIDING_JUDGE

        else:
            return Position.JUDGE

    elif re.search(r"^Justice\sCourt", jobTitle):
        return Position.TRIAL_JUDGE

    elif re.search(r"^Municipal\sCourt", jobTitle):
        return Position.TRIAL_JUDGE

    else:
        return None


def lookup_judge_by_full_name(
    lfm: str,
    event_date: Optional[date] = None,
) -> Optional[Person]:
    """Uniquely identifies a judge by name and event_date.

    :param name: The judge's name, either as a str of the full name or as
    a HumanName object. Do NOT provide just the last name of the judge. If you
    do, it will be considered the judge's first name. You MUST provide their
    full name or a HumanName object. To look up a judge by last name, see the
    look_up_judge_by_last_name function. The str parsing used here is the
    heuristic approach used by nameparser.HumanName.

    :param event_date: The date when the judge did something
    :return Either the judge that matched the name in the court at the right
    time, or None.
    """
    name = HumanName(lfm)

    # check based on last name and court first
    filter_sets = [
        [Q(name_last__iexact=name.last)],
    ]
    # Then narrow by date
    if event_date is not None:
        filter_sets.append(
            [
                Q(
                    positions__date_start__lt=event_date
                    + relativedelta(years=1)
                )
                | Q(positions__date_start=None),
                Q(
                    positions__date_termination__gt=event_date
                    - relativedelta(years=1)
                )
                | Q(positions__date_termination=None),
            ]
        )

    # Then by first name
    if name.first:
        filter_sets.append([Q(name_first__iexact=name.first)])

    # Do middle name or initial next.
    if name.middle:
        initial = len(name.middle.strip(".,")) == 1
        if initial:
            filter_sets.append(
                [Q(name_middle__istartswith=name.middle.strip(".,"))]
            )
        else:
            filter_sets.append([Q(name_middle__iexact=name.middle)])

    # And finally, by suffix
    if name.suffix:
        suffix = SUFFIX_LOOKUP.get(name.suffix.lower())
        if suffix:
            filter_sets.append([Q(name_suffix__iexact=suffix)])

    # Query people DB, slowly adding more filters to the query. If we get zero
    # results, no luck. If we get one, great. If we get more than one, continue
    # filtering. If we expend all our filters and still have more than one,
    # just return None.
    applied_filters = []
    for filter_set in filter_sets:
        applied_filters.extend(filter_set)
        candidates = Person.objects.filter(*applied_filters)
        if len(candidates) == 0:
            # No luck finding somebody. Abort.
            return None
        elif len(candidates) == 1:
            # Got somebody unique!
            return candidates.first()
        elif len(candidates) > 1:
            logging.info(
                f"Found %s candidates, returning None", len(candidates)
            )
    return None
