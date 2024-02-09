from enum import Enum

from elasticsearch.exceptions import SerializationError


class QueryType(Enum):
    QUERY_STRING = "QUERY_STRING"
    FILTER = "FILTER"


class SyntaxQueryError(SerializationError):
    QUERY_STRING = QueryType.QUERY_STRING
    FILTER = QueryType.QUERY_STRING.FILTER

    def __init__(self, message, error_type):
        super().__init__(message)
        self.error_type = error_type


class UnbalancedParenthesesQuery(SyntaxQueryError):
    """Data passed in has unbalanced parentheses"""


class UnbalancedQuotesQuery(SyntaxQueryError):
    """Data passed in has unbalanced quotes"""


class BadProximityQuery(SyntaxQueryError):
    """Data passed in has contains a not supported search proximity token"""
