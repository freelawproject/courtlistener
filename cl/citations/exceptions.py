from http import HTTPStatus

from rest_framework.exceptions import APIException


class MultipleChoices(APIException):
    status_code = HTTPStatus.MULTIPLE_CHOICES
    default_code = "multiple_choices"
