from datetime import date

from cl.lib.date_time import midnight_pt


def solr_list(m2m_list, field):
    new_list = []
    for obj in m2m_list:
        obj = getattr(obj, field)
        if obj is None:
            continue
        if isinstance(obj, date):
            obj = midnight_pt(obj)
        new_list.append(obj)
    return new_list


class InvalidDocumentError(Exception):
    """The document could not be formed"""

    def __init__(self, message):
        Exception.__init__(self, message)


# Used to nuke null and control characters.
null_map = dict.fromkeys(
    list(range(0, 10)) + list(range(11, 13)) + list(range(14, 32))
)


def get_parties_from_case_name(case_name: str) -> list[str]:
    """Extracts the parties from case_name by splitting on common case_name
    separators.

    :param case_name: The case_name to be split.
    :return: A list of parties. If no valid separator is found, returns an
    empty list.
    """

    valid_case_name_separators = [
        " v ",
        " v. ",
        " vs. ",
        " vs ",
    ]
    for separator in valid_case_name_separators:
        if separator in case_name:
            return case_name.split(separator, 1)
    return []
