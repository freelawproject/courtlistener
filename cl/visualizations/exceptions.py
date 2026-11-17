"""Exceptions for building visualizations."""


class TooManyNodes(Exception):
    """Raised when a visualization's network has too many nodes."""

    class SetupException(Exception):
        def __init__(self, message):
            """Build the exception with a message."""
            Exception.__init__(self, message)
