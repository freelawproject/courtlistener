"""Exceptions for the citation lookup API."""

from http import HTTPStatus

from rest_framework.exceptions import APIException


class MultipleChoices(APIException):
    """An API error with a 300 Multiple Choices status."""

    status_code = HTTPStatus.MULTIPLE_CHOICES
    default_code = "multiple_choices"
