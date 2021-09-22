import copy
import json
import logging
import time
from datetime import date

from cl.people_db.models import Position


def convert_date_to_gran_format(date_text):
    return time.strftime("%Y-%m-%d", time.strptime(date_text, "%m/%d/%Y"))


def string_to_date(date_text, format):
    return time.mktime(time.strptime(date_text, format))


def is_date_before(date1, date2):
    """Take two dates in the format 2010-22-11 and
    returns true if date 1 is earlier than date 2

    :param date1
    :param date2
    :return boolean
    """
    pydate1 = string_to_date(date1, "%m/%d/%Y")
    pydate2 = string_to_date(date2, "%m/%d/%Y")

    return pydate1 < pydate2


def process_positions(positions, counties):

    new_pos = []
    # first, parse the position objects
    logging.info(f"Processing %s positions", len(positions))
    for pos in positions:

        how_selected = get_how_selected(pos["judicialExperiencePendingStatus"])

        appointer = None
        if how_selected == Position.APPOINTMENT_GOVERNOR:
            appointer = get_appointer(pos["judicialExperiencePendingSubType"])

        new_pos.append(
            {
                "appointer": appointer,
                "court": find_court(pos, counties),
                "date_start": pos["judicialExperienceActiveDate"],
                "date_termination": pos["judicialExperienceInactiveDate"],
                "how_selected": how_selected,
                "job_title": pos["judicialPositionJobTitle"],
                "organization_name": pos["orgName"],
                "position_type": get_position_type(
                    pos["judicialPositionJobTitle"]
                ),
                "termination_reason": get_termination_reason(
                    pos["judicialExperienceInactiveStatus"]
                ),
                ## extra fields,
                "pending_status": pos["judicialExperiencePendingStatus"],
                "inactive_status": pos["judicialExperienceInactiveStatus"],
            }
        )

    return recursively_sort(new_pos, [])


def is_supervising_position(position_type):
    # if position of type
    # Presiding Judge
    # Presiding Justice
    # Administrative Presiding
    # Supervising
    # Assistant Presiding
    # and pending_status === 'Selected'
    # and inactive_status === 'Term Ended'
    # then restructure the fields

    selected_positions = [
        Position.PRESIDING_JUDGE,
        Position.PRESIDING_JUSTICE,
        Position.ADMINISTRATIVE_PRESIDING_JUSTICE,
        Position.SUPERVISING_JUDGE,
        Position.ASSISTANT_PRESIDING_JUDGE,
    ]
    return position_type in selected_positions


def recursively_sort(old_array, new_array):

    logging.info("recursively sorting - %s items remaining", len(old_array))
    logging.info("recursively sorting - %s items added", len(new_array))

    if len(old_array) == 0:
        return new_array
    else:
        # sort the old_array by date started
        old_array.sort(
            key=lambda p: string_to_date(p["date_start"], "%m/%d/%Y")
        )

        # if this is the first item in the new array, return it
        if len(new_array) == 0:
            # add the earliest item to the new_array and recurse
            first = old_array.pop(0)
            new_array.append(first)
            return recursively_sort(old_array, new_array)
        else:
            # we check if the next item to add is
            # before the end date of the last item in the new_array
            # prev_entry = pos1
            # current_entry = pos2
            pos1 = copy.copy(new_array[-1])
            pos2 = old_array.pop(0)

            # if no termination date on both, it means both positions are still open
            # e.g., judge is likely currently serving as presiding judge
            if not pos1["date_termination"] and not pos2["date_termination"]:
                # if pos 1 started before position 2, then we shorten pos1
                # to end when pos2 started
                og_pos1 = new_array.pop()

                if is_date_before(pos1["date_start"], pos2["date_start"]):
                    og_pos1["date_termination"] = pos2["date_start"]
                    og_pos1["termination_reason"] = "other_pos"

                new_array.append(og_pos1)
                new_array.append(pos2)
            # if position2 has no date_termination it means that the person is still serving in the current
            # position but hte last position has ended
            elif not pos2["date_termination"]:
                # if the pos2 date start is after the position1 termination_date, we fix
                if is_date_before(
                    pos1["date_termination"], pos2["date_start"]
                ):
                    pos2["date_start"] = pos1["date_termination"]

                new_array.append(pos2)

            # since we sort in order, if position 2 has a date_termination but pos 1 doesn't
            # that means that pos 1 definitely ended
            # need to make the end date of pos 1 the start date of pos 2
            elif not pos1["date_termination"]:
                og_pos1 = new_array.pop()

                og_pos1["date_termination"] = pos2["date_start"]
                og_pos1["termination_reason"] = "other_pos"

                new_array.append(og_pos1)
                new_array.append(pos2)

            # if the pos date_start is earlier than the pos1_termination date, fix
            elif is_date_before(pos2["date_start"], pos1["date_termination"]):
                new_pos_1 = new_array.pop()
                new_pos_3 = copy.copy(new_pos_1)

                new_pos_1["date_termination"] = pos2["date_start"]
                new_pos_1["termination_reason"] = "other_pos"

                new_pos_3["date_start"] = pos2["date_termination"]

                new_array.append(new_pos_1)
                new_array.append(pos2)
                new_array.append(new_pos_3)
            else:
                # if we're all good, just add the second pos to the array
                new_array.append(pos2)

            return recursively_sort(old_array, new_array)


def get_how_selected(jud_exp_pending_status):
    """Maps pending status to the Selection Method Enum

    Possible options are
    Appointed
    Elected
    Hired (applies only to Hon. Gerald Mohun who was elected)
    Selected (i.e., appointed by judges to be a Presiding or Administrative Judge)
    Unification (i.e. courts were restructured)


    :param jud_exp_pending_status: string
    :return enum / string
    """

    how_selected_map = {
        "Appointed": Position.APPOINTMENT_GOVERNOR,
        "Elected": Position.ELECTION_NON_PARTISAN,
        "Hired": Position.ELECTION_NON_PARTISAN,
        "Selected": Position.APPOINTMENT_JUDGE,
        "Unification": Position.COURT_TRANSFER,
    }

    return how_selected_map.get(jud_exp_pending_status)


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

    :return enum | None
    """

    status_to_enum = {
        "Deceased": "ded",
        "Defeated": "lost",
        "Non-Voluntary": "retire_mand",
        # edge case Other refers to consolidated courts
        "Other": "abolished",
        "Promoted": "other_pos",
        "Resigned": "resign",
        "Retired": "retire_vol",
        "Term Ended": "termed_out",
        "Transferred": "other_pos",
    }
    return status_to_enum.get(status)


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
