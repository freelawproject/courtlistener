class ScrapeFailed(Exception):
    """Raised when a scraper fails for some reason."""

    pass


class CourtQueryError(Exception):
    """A court-report operation failed at a retryable step.

    Chain the original exception so callers can choose their retry policy
    without catching unrelated failures from the surrounding workflow.
    """


class IQuerySaveError(Exception):
    """Saving iquery metadata failed before storing its tags and HTML."""


class ConfigurationException(Exception):
    """Raised when required configuration is not set."""

    pass


class SubscriptionFailure(Exception):
    """Raised when subscribing to case updates fails."""

    pass


class NoSuchKey(Exception):
    """Raised when an S3 key does not exist."""

    pass
