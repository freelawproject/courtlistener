import re
from datetime import date
from typing import Any

from elasticsearch.exceptions import ConflictError
from elasticsearch.helpers import BulkIndexError, bulk
from elasticsearch_dsl import connections

from cl.lib.command_utils import logger
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


def get_parties_from_case_name_bankr(case_name: str) -> list[str]:
    """Extracts the parties involved in a bankruptcy case from the case name.

    This function attempts to identify the parties by splitting the case name
    string based on common separators. It also performs some cleanup to
    remove extraneous information like court designations in parentheses,
    trailing HTML, and text related to "BELOW" or "ABOVE" designations.

    If the case name begins with "in re" or "in the matter of", an empty list
    is returned, as these typically don't contain party information in the
    standard format.

    :param case_name: The bankruptcy case name string.
    :return: A list of strings, where each string represents a party involved
    in the case. If no recognized separator is found, the function returns
    a list containing the cleaned case name as a single element.
    """
    # Handle cases beginning with "in re" or "in the matter of".
    # These usually don't contain party information in the expected format.
    if re.match(
        r"^(in re|in the matter of|unknown case title)",
        case_name,
        re.IGNORECASE,
    ):
        return []

    # Removes text enclosed in parentheses at the end of the string.
    cleaned_case_name = re.sub(r"\s*\([^)]*\)$", "", case_name)

    # Removes any HTML at the end of the string.
    cleaned_case_name = re.sub(r"\s*<.*$", "", cleaned_case_name)

    # Removes text following "-BELOW" or "-ABOVE" at the end of the string.
    cleaned_case_name = re.sub(r"\s*(-BELOW|-ABOVE).*$", "", cleaned_case_name)

    # Removes text following "- Adversary Proceeding" at the end of the string.
    cleaned_case_name = re.sub(
        r"\s*- Adversary Proceeding.*$", "", cleaned_case_name
    )

    case_name_separators = VALID_CASE_NAME_SEPARATORS.copy()
    case_name_separators.append(" and ")
    for separator in case_name_separators:
        if separator in case_name:
            return cleaned_case_name.split(separator, 1)
    return [cleaned_case_name]


def check_bulk_indexing_exception(
    errors: list[dict[str, Any]], exception: str
) -> bool:
    """Check for a specific exception type in bulk indexing errors.
    :param errors: A list of dictionaries representing errors from a bulk
    indexing operation.
    :param exception: The exception type string to check for in the error
    details.
    :return: True if the specified exception is found in any of the error
    dictionaries; otherwise, returns False.
    """
    for error in errors:
        if error.get("update", {}).get("error", {}).get("type") == exception:
            return True
    return False


def index_documents_in_bulk(documents_to_index: list[dict[str, Any]]) -> None:
    """Index documents in Elasticsearch using the bulk API.

    :param documents_to_index: A list of dictionaries representing the documents
    to be indexed in bulk.
    :return: None.
    """

    client = connections.get_connection(alias="no_retry_connection")
    # Execute the bulk update
    ids = [doc["_id"] for doc in documents_to_index]
    try:
        bulk(client, documents_to_index)
    except BulkIndexError as exc:
        # Catch any BulkIndexError exceptions to handle specific error message.
        # If the error is a version conflict, raise a ConflictError for retrying it.
        if check_bulk_indexing_exception(
            exc.errors, "version_conflict_engine_exception"
        ):
            raise ConflictError(
                "ConflictError indexing cites.",
                "",
                {"ids": ids},
            )
        if check_bulk_indexing_exception(
            exc.errors, "document_missing_exception"
        ):
            missing_opinion = exc.errors[0].get("update", {}).get("_id", None)
            logger.warning(
                "Opinion with ID %s is not indexed in ES.", missing_opinion
            )
        else:
            # If the error is of any other type, raises the original
            # BulkIndexError for debugging.
            raise exc
