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


default_bad_request_error_msg = (
    "Elasticsearch Bad request error. Please review your query."
)
unbalanced_parentheses_error_msg = "The query contains unbalanced parentheses."
unbalanced_quotes_error_msg = "The query contains unbalanced quotes."
bad_proximity_query_error_msg = (
    "The query contains an unrecognized proximity token."
)


class UnbalancedParenthesesQuery(SyntaxQueryError):
    """Data passed in has unbalanced parentheses"""

    message = unbalanced_parentheses_error_msg


class UnbalancedQuotesQuery(SyntaxQueryError):
    """Data passed in has unbalanced quotes"""

    message = unbalanced_quotes_error_msg


class BadProximityQuery(SyntaxQueryError):
    """Data passed in has contains a not supported search proximity token"""

    message = bad_proximity_query_error_msg


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
    default_detail = default_bad_request_error_msg
    default_code = "bad_request"


class UnbalancedParenthesesQueryAPIError(ElasticBadRequestError):
    """APIException for handling unbalanced parentheses in ES queries."""

    default_detail = unbalanced_parentheses_error_msg


class UnbalancedQuotesQueryAPIError(ElasticBadRequestError):
    """APIException for handling unbalanced quotes in ES queries."""

    default_detail = unbalanced_quotes_error_msg


class BadProximityQueryAPIError(ElasticBadRequestError):
    """APIException for handling bad proximity values in ES queries."""

    default_detail = bad_proximity_query_error_msg
