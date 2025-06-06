import calendar
import datetime
import time
from calendar import monthrange

from django.core import validators
from django.core.exceptions import ValidationError
from django.forms import ChoiceField, DateField
from django.utils import formats
from django.utils.encoding import force_str

INPUT_FORMATS = [
    "%Y%m%d",  # '20061025'
    "%Y-%m-%d",  # '2006-10-25'
    "%Y-%m",  # '2006-10'
    "%Y",  # '2006'
    "%m-%d-%Y",  # '10-25-2006'
    "%m-%Y",  # '10-2006'
    "%m-%d-%y",  # '10-25-06'
    "%m-%y",  # '10-06'
    "%m/%d/%Y",  # '10/25/2006'
    "%m/%Y",  # '10/2006'
    "%m/%d/%y",  # '10/25/06'
    "%m/%y",  # '10/06'
    "%Y/%m/%d",  # '2006/10/26'
    "%Y/%m",  # '2006/10'
]


class ParseFloorDateMixin:
    def _parse_floor_date(self, value):
        """Validates that the input can be converted to a date. Returns a Python
        datetime.date object or the original input if it cannot be converted.
        """
        if value in validators.EMPTY_VALUES or value == "MM/DD/YYYY":
            return None

        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value

        unicode_value = force_str(value, strings_only=True)
        if isinstance(unicode_value, str):
            value = unicode_value.strip()
        # If unicode, try to strptime against each input format.
        if isinstance(value, str):
            for format in self.input_formats:
                try:
                    # strptime provides the floor by default
                    return datetime.date(*time.strptime(value, format)[:3])
                except (ValueError, TypeError):
                    continue

        # Unable to parse the value as a date. Returning the original value.
        return value


class ParseCeilingDateMixin:
    """
    Uses django.forms.fields.DateField as a starting point, and then allows
    users to input partial dates such as 2011-12. However, instead of assuming
    such dates correspond with the first of the month, it assumes that such
    dates represent the *last* day of the month. This allows a search for all
    documents "After 2010" to work.
    """

    @staticmethod
    def _calculate_extra_days(date_format, d):
        """Given a date and a format, calculate how many days to add to it to
        create the correct ceiling date.
        """
        if date_format.count("%") == 1:
            if calendar.isleap(d.year):
                num_days = 366
            else:
                num_days = 365
        elif date_format.count("%") == 2:
            # The user provided a year and a month. Add the correct number of
            # days for that particular month in that particular year.
            num_days = monthrange(d.year, d.month)[1]
        else:
            # A full date was provided. No extra days needed.
            return 0

        # Subtract 1 from num_days because strptime will have converted the
        # date entered into the first of that month. To reach the end of the
        # year or month, you must add one less than number of days during that
        # time period.
        return num_days - 1

    def _parse_ceiling_date(self, value):
        """Validates that the input can be converted to a date. Returns a Python
        datetime.date object or the original input if it cannot be converted.
        """
        if value in validators.EMPTY_VALUES or value == "MM/DD/YYYY":
            return None

        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        unicode_value = force_str(value, strings_only=True)
        if isinstance(unicode_value, str):
            value = unicode_value.strip()
        # If unicode, try to strptime against each input format.
        if isinstance(value, str):
            for format in self.input_formats:
                try:
                    valid_date = datetime.date(
                        *time.strptime(value, format)[:3]
                    )
                except ValueError:
                    continue
                additional_days = self._calculate_extra_days(
                    format, valid_date
                )

                return valid_date + datetime.timedelta(days=additional_days)

        # Unable to parse the value as a date. Returning the original value.
        return value


class FloorDateOrRelativeField(DateField, ParseFloorDateMixin):
    """Simply overrides the DateField to give it a better name.
    Validates whether the input is a date object or returns the original value
    if it's a potential relative date, which will be validated upstream.
    """

    input_formats = INPUT_FORMATS + formats.get_format("DATE_INPUT_FORMATS")

    def to_python(self, value):
        # Potential relative date format. It will be validated upstream.
        return self._parse_floor_date(value)


class FloorDateField(DateField, ParseFloorDateMixin):
    """Simply overrides the DateField to give it a better name.
    Validates whether the input is a date object or raises a ValidationError if
    the input cannot be parsed into a valid date.
    """

    input_formats = INPUT_FORMATS + formats.get_format("DATE_INPUT_FORMATS")

    def to_python(self, value):
        parsed = self._parse_floor_date(value)
        if parsed is not None and not isinstance(parsed, datetime.date):
            raise ValidationError(
                self.error_messages["invalid"], code="invalid"
            )
        return parsed


class CeilingDateOrRelativeField(DateField, ParseCeilingDateMixin):
    """Implements a DateField where partial input is accepted.
    Validates whether the input is a date object or returns the original value
    if it's a potential relative date, which will be validated upstream.
    """

    input_formats = INPUT_FORMATS + formats.get_format("DATE_INPUT_FORMATS")

    def to_python(self, value):
        # Potential relative date format. It will be validated upstream.
        return self._parse_ceiling_date(value)


class CeilingDateField(DateField, ParseCeilingDateMixin):
    """Implements a DateField where partial input is accepted.
    Validates whether the input is a date object or raises a ValidationError if
    the input cannot be parsed into a valid date.
    """

    input_formats = INPUT_FORMATS + formats.get_format("DATE_INPUT_FORMATS")

    def to_python(self, value):
        parsed = self._parse_ceiling_date(value)
        if parsed is not None and not isinstance(parsed, datetime.date):
            raise ValidationError(
                self.error_messages["invalid"], code="invalid"
            )
        return parsed


class RandomChoiceField(ChoiceField):
    """A choice field, but it allows any value that starts with 'random_'"""

    def validate(self, value):
        super(ChoiceField, self).validate(value)
        if value and not self.valid_value(value):
            if value.startswith("random_"):
                # Such values are OK. Just return.
                return
            else:
                raise ValidationError(
                    self.error_messages["invalid_choice"],
                    code="invalid_choice",
                    params={"value": value},
                )
