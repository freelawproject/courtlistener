from datetime import date

from cl.people_db.models import Position


def is_date_before(date1, date2):
    """Take two dates in the format 2010-22-11 and
    returns true if date 1 is earlier than or equal to date 2

    :param date1
    :param date2
    :return boolean
    """
    y1, m1, d1 = date1.split("-")
    y2, m2, d2 = date2.split("-")

    pydate1 = date(y1, m1, d1)
    pydate2 = date(y2, m2, d2)

    return pydate1 <= pydate2


def create_positions(positions, counties):

    new_pos = []
    final_pos = []
    # first, parse the position objects
    for pos in positions:

        how_selected = get_how_selected(
            pos["judicialExperiencePendingStatus"]
        )

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

    sorted_positions = recursively_sort(new_pos)


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


def positions_need_restructuring(position1, position2):
    """returns true if the dates overlap, it is a supervisory position,
    and the status categories match a selected position

    :param position1
    :param position2
    :return boolean
    """
    # check if position date_start is after the prior date_termination
    dates_valid = is_date_before(
        position1["date_termination"], position2["date_start"]
    )
    # check if the new position is a supervisory one
    is_supervisor = is_supervising_position(position2["position_type"])

    # sanity check -- make sure the pending status is "Selected" and inactive status is "Term Ended"
    # as this indicates that it was likely a supervisory promotion
    has_right_statuses = (
        position2["pending_status"] == "Selected"
        and position2["inactive_status"] == "Term Ended"
    )

    if not dates_valid and is_supervisor and has_right_statuses:
        return true
    else:
        return false


def recursively_sort(old_array, new_array=[]):

    if len(old_array) > 0:

        # sort the old_array by date started
        old_array.sort(
            key=lambda p: time.mktime(
                time.strptime(p["date_started"], "%Y-%m-%d")
            )
        )

        # if this is the first item in the new array, return it
        if len(new_array) == 0:
            # add the earliest item to the new_array and recurse
            first = old_array.pop(0)
            new_array.append(first)
            recursively_sort(old_array, new_array)
        else:
            # we check if the next item to add is
            # before the end date of the last item in the new_array
            # prev_entry = pos1
            # current_entry = pos2
            pos1 = new_array[-1]
            pos2 = old_array.pop(0)

            needs_restructuring = positions_need_restructuring(pos1, pos2)

            if needs_restructuring:
                # we remove the last date from the new_array to split into
                # item 1 (before the promotion) and item 3 (after the promotion)
                pos_to_split = new_array.pop()

                new_pos_1 = pos_to_split
                # set the new termination date for position
                new_pos_1["date_termination"] = pos2["start_date"]
                # set the new termination reason
                new_pos_1["termination_reason"] = "other_pos"
                # push to new_array
                new_array.append(new_pos_1)

                # push the middle item
                new_array.append(pos2)

                # build item 3 by replacing the start date with item 2 end date
                new_pos_3 = pos_to_split
                new_pos_3["date_started"] = pos2["date_termination"]

                new_array.append(new_pos_3)

                # recurse
                recursively_sort(old_array, new_array)

            else:
                new_array.append(pos2)
                recursively_sort(old_array, new_array)
    else:
        # recursion over, return array
        return new_array
