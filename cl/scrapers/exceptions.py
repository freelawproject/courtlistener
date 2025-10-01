import logging

from juriscraper.lib.exceptions import AutoLoggingException

from cl.lib.command_utils import logger


class ConsecutiveDuplicatesError(AutoLoggingException):
    """Occurs when consecutive `SingleDuplicateError` are found,
    which may be used as a signal to break the scraping loop
    """

    message = "DupChecker emulate break triggered."
    logger = logger


class SingleDuplicateError(AutoLoggingException):
    """Occurs when an opinion or audio file already exists
    in our database
    """

    message = "Skipping opinion due to duplicated content hash"
    logger = logger


class MergingError(AutoLoggingException):
    """Raised when metadata merging finds different values"""

    logging_level = logging.ERROR
    logger = logger
