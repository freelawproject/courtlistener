import logging
from typing import Optional

from cl.lib.command_utils import logger


class AutoLoggingException(Exception):
    """Exception with defaults for logging, to be subclassed

    We log expected exceptions to better understand what went wrong
    Logger calls with level `logging.ERROR` are sent to Sentry, and
    it's useful to send a `fingerprint` to force a specific grouping by court

    Other `logger` calls are just printed on the console when using a
    VerboseCommand with proper verbosity levels
    """

    logging_level = logging.DEBUG
    message = ""
    logger = logger

    def __init__(
        self,
        message: str = "",
        logger: Optional[logging.Logger] = None,
        logging_level: Optional[int] = None,
        fingerprint: Optional[list[str]] = None,
    ):
        if not message:
            message = self.message
        if not logger:
            logger = self.logger
        if not logging_level:
            logging_level = self.logging_level

        log_kwargs = {}
        if fingerprint:
            log_kwargs["extra"] = {"fingerprint": fingerprint}

        logger.log(logging_level, message, **log_kwargs)
        super().__init__(message)


class ConsecutiveDuplicatesError(AutoLoggingException):
    """Occurs when consecutive `SingleDuplicateError` are found,
    which may be used as a signal to break the scraping loop
    """

    message = "DupChecker emulate break triggered."


class SingleDuplicateError(AutoLoggingException):
    """Occurs when an opinion or audio file already exists
    in our database
    """

    message = "Skipping opinion due to duplicated content hash"


class BadContentError(AutoLoggingException):
    """Parent class for errors raised when downloading binary content"""


class UnexpectedContentTypeError(BadContentError):
    """Occurs when the content received from the server has
    a different content type than the ones listed on
    site.expected_content_types
    """

    logging_level = logging.ERROR


class NoDownloadUrlError(BadContentError):
    """Occurs when a DeferredList fetcher fails."""

    logging_level = logging.ERROR


class EmptyFileError(BadContentError):
    """Occurs when the content of the response has lenght 0"""

    logging_level = logging.ERROR
