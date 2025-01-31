import re
from datetime import date

from cl.lib.date_time import midnight_pt


def extract_field_values(m2m_list, field):
    """Extracts values from a list of objects.

    This function iterates over a list of objects, extracts the specified field value
    from each object, and returns a new list of values.
    If the field value is a `datetime.date` object, it is converted to midnight Pacific Time.

    Args:
        m2m_list: A list of objects.
        field_name: The name of the field to extract values from.

    Returns:
        A list of extracted field values
    """
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

VALID_CASE_NAME_SEPARATORS = [" v ", " v. ", " vs. ", " vs "]


def get_parties_from_case_name(case_name: str) -> list[str]:
    """Extracts the parties from case_name by splitting on common case_name
    separators.

    :param case_name: The case_name to be split.
    :return: A list of parties. If no valid separator is found, returns an
    empty list.
    """
    for separator in VALID_CASE_NAME_SEPARATORS:
        if separator in case_name:
            return case_name.split(separator, 1)
    return []


def get_parties_from_bankruptcy_case_name(case_name: str) -> list[str]:
    """Extracts the parties involved in a bankruptcy case from the case name.

    This function attempts to identify the parties by splitting the case name
    string based on common separators. It also performs some cleanup to
    remove extraneous information like court designations in parentheses,
    trailing HTML, and text related to "BELOW" or "ABOVE" designations.

    Args:
        case_name: The bankruptcy case name string.

    Returns:
        A list of strings, where each string represents a party involved
        in the case.  If no recognized separator is found, the function
        returns a list containing the cleaned case name as a single element.
    """
    # Removes text enclosed in parentheses at the end of the string.
    cleaned_case_name = re.sub(r"\s*\([^)]*\)$", "", case_name)

    # Removes any HTML at the end of the string.
    cleaned_case_name = re.sub(r"\s*<.*$", "", cleaned_case_name)

    # Removes text following "-BELOW" or "-ABOVE" at the end of the string.
    cleaned_case_name = re.sub(r"\s*(-BELOW|-ABOVE).*$", "", cleaned_case_name)

    case_name_separators = VALID_CASE_NAME_SEPARATORS.copy()
    case_name_separators.append(" and ")
    for separator in case_name_separators:
        if separator in case_name:
            return cleaned_case_name.split(separator, 1)
    return [cleaned_case_name]
