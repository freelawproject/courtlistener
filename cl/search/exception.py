from enum import Enum
from http import HTTPStatus

from elasticsearch.exceptions import SerializationError
from rest_framework.exceptions import APIException


class QueryType(Enum):
    QUERY_STRING = "QUERY_STRING"
    FILTER = "FILTER"


class SyntaxQueryError(SerializationError):
    QUERY_STRING = QueryType.QUERY_STRING
    FILTER = QueryType.QUERY_STRING.FILTER

    def __init__(self, error_type):
        self.error_type = error_type


class UnbalancedParenthesesQuery(SyntaxQueryError):
    """Data passed in has unbalanced parentheses"""

    message = "The query contains unbalanced parentheses."


class UnbalancedQuotesQuery(SyntaxQueryError):
    """Data passed in has unbalanced quotes"""

    message = "The query contains unbalanced quotes."


class BadProximityQuery(SyntaxQueryError):
    """Data passed in has contains a not supported search proximity token"""

    message = "The query contains an unrecognized proximity token."


class ElasticServerError(APIException):
    """Exception for handling internal server errors specifically related to
    Elasticsearch requests.
    """

    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    default_detail = (
        "Internal Server Error. Please try again later or review your query."
    )
    default_code = "internal_server_error"


class ElasticBadRequestError(APIException):
    """Exception for handling ES query parsing errors."""

    status_code = HTTPStatus.BAD_REQUEST
    default_detail = (
        "Elasticsearch Bad request error. Please review your query."
    )
    default_code = "bad_request"
