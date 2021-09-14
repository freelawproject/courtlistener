from datetime import date


def is_date_before(date1, date2):
  """Take two dates in the format 2010-22-11 and
  returns true if date 1 is earlier than or equal to date 2

  :param date1
  :param date2
  :return boolean
  """
  y1, m1, d1 = date1.split('-')
  y2, m2, d2 = date2.split('-')

  pydate1 = date(y1, m1, d1)
  pydate2 = date(y2, m2, d2)

  return pydate1 <= pydate2

def create_positions(positions, counties):

  positions.sort(,
    key=lambda p: time.mktime(
      time.strptime(
        p["judicialExperienceActiveDate"],
        "%Y-%m-%d"
      )
    )
  )

  new_pos = []
  final_pos = []
  # first, parse the position objects
  for pos in positions:

    how_selected = get_how_selected(json["judicialExperiencePendingStatus"])

    appointer = how_selected == Position.APPOINTMENT_GOVERNOR
      ? get_appointer(json["judicialExperiencePendingSubType"])
      : null

    new_pos.append({
      "appointer": appointer,
      "court": find_court(pos, counties),
      "date_start": pos["judicialExperienceActiveDate"],
      "date_termination": pos["judicialExperienceInactiveDate"],
      "how_selected": how_selected,
      "job_title": pos["judicialPositionJobTitle"],
      "organization_name": pos["orgName"],
      "position_type": get_position_type(pos["judicialPositionJobTitle"]),
      "termination_reason": get_termination_reason(pos["judicialExperienceInactiveStatus"])
      ## extra fields,
      "pending_status": pos["judicialExperiencePendingStatus"],
      "inactive_status": pos["judicialExperienceInactiveStatus"]
    })

  for i, p in enumerable(new_pos):
    if i === 0:
      del p['pending_status']
      del p['inactive_status']
      final_pos.append(p)
    else:
      # check to see if restructuring is needed
      pos1_start = new_pos[i+1]["date_start"]
      pos1_end = new_pos[i+1]["date_termination"]
      pos2_start = p["date_start"]
      pos2_end = p["date_termination"]

      is_valid = is_date_before(pos1_end, pos2_start)

      if (is_valid):
        del p['pending_status']
        del p['inactive_status']
        final_pos.append(p)
      else:
        pos1_title = new_pos[i+1]["job_title"]
        pos2_title = p["job_title"]

        logging.info(f"End date of position {pos1_title} is after start of {pos2_title}")

        pos2_position_type = new_pos[i+1]["position_type"]
        # if position of type
        # Presiding Judge
        # Presiding Justice
        # Administrative Presiding
        # Supervising
        # Assistant Presiding

        # and pending_status === 'Selected'
        # and inactive_status === 'Term Ended'

        # then restructure the fields
