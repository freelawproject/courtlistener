import json
import logging
import os
import re
from datetime import date
from typing import Optional

from dateutil.parser import parse
from django.db.models import Q
from nameparser import HumanName

from cl.people_db.models import SUFFIX_LOOKUP, Person


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


def alias_or_person(person: Person) -> Optional[Person]:
    """Given a found person, check if that person is an alias

    if so, get the actual Person and return it
    else, return the Person passed into the function
    """
    if person.is_alias:
        return person.is_alias_of
    else:
        return person


def lookup_judge_by_full_name(
    lfm: str,
    event_date: Optional[date] = None,
) -> Optional[Person]:
    """Uniquely identifies a judge by name and event_date.

    :param lfm: The judge's name, as a str of the full name.
    :param event_date: The date when the judge did something
    :return Either the judge that matched the name in the court at the right
    time, or None.
    """
    name = HumanName(lfm)

    # First we search by name_last, name_first, and suffix
    filter_sets = [
        Q(name_last__iexact=name.last),
        Q(name_first__iexact=name.first),
    ]

    if name.suffix:
        suffix = SUFFIX_LOOKUP.get(name.suffix.lower())
        if suffix:
            filter_sets.append(Q(name_suffix__iexact=suffix))

    candidates = Person.objects.filter(*filter_sets)

    if len(candidates) == 0:
        # No luck finding somebody. Abort.
        return None
    elif len(candidates) == 1:
        # Got somebody unique!
        return alias_or_person(candidates.first())
    elif len(candidates) > 1:
        logging.info(
            f"Found more than one candidate. Adding middle name to filter"
        )
        # if we have more than one candidate, we add in the middle_name q
        # queryset un the search
        if name.middle:
            initial = len(name.middle.strip(".,")) == 1
            if initial:
                filter_sets.append(
                    Q(name_middle__istartswith=name.middle.strip(".,"))
                )
            else:
                filter_sets.append(Q(name_middle__iexact=name.middle))

        second_pass = Person.objects.filter(*filter_sets)

        if len(second_pass) == 0:
            return None
        elif len(second_pass) == 1:
            return alias_or_person(second_pass.first())
        elif len(second_pass) > 1:
            logging.info(
                f"Found %s candidates, returning None", len(second_pass)
            )

    return None
