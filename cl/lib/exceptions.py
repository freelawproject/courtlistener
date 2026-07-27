class ScrapeFailed(Exception):
    """Raised when a scraper fails for some reason."""

    pass


class SubscriptionFailure(Exception):
    """Raised when subscribing to case updates fails."""

    pass


class NoSuchKey(Exception):
    """Raised when an S3 key does not exist."""

    pass
