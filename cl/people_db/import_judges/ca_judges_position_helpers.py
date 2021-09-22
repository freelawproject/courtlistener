import logging
import time
import json
import copy
from datetime import date

from cl.people_db.import_judges.ca_judges_import_helpers import (
    find_court,
    get_appointer,
    get_how_selected,
    get_position_type,
    get_termination_reason,
)
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
