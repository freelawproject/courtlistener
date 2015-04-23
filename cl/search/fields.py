import calendar
import datetime
import time
from calendar import monthrange

from django.core import validators
from django.core.exceptions import ValidationError
from django.utils import formats
from django.utils import six
from django.utils.encoding import force_text
from django.forms import DateField

INPUT_FORMATS = (
    '%Y%m%d',    # '20061025'
    '%Y-%m-%d',  # '2006-10-25'
    '%Y-%m',     # '2006-10'
    '%Y',        # '2006'
    '%m-%d-%Y',  # '10-25-2006'
    '%m-%Y',     # '10-2006'
    '%m-%d-%y',  # '10-25-06'
    '%m-%y',     # '10-06'
    '%m/%d/%Y',  # '10/25/2006'
    '%m/%Y',     # '10/2006'
    '%m/%d/%y',  # '10/25/06'
    '%m/%y',     # '10/06'
    '%Y/%m/%d',  # '2006/10/26'
    '%Y/%m',     # '2006/10'
)


class FloorDateField(DateField):
    """Simply overrides the DateField to give it a better name. Corrects
    placeholder value where browsers fail to implement it correctly.
    """
    input_formats = INPUT_FORMATS + formats.get_format('DATE_INPUT_FORMATS')

    def to_python(self, value):
        """
        Validates that the input can be converted to a date. Returns a Python
        datetime.date object.
        """
        if value in validators.EMPTY_VALUES or value == 'YYYY-MM-DD':
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value

        unicode_value = force_text(value, strings_only=True)
        if isinstance(unicode_value, six.text_type):
            value = unicode_value.strip()
        # If unicode, try to strptime against each input format.
        if isinstance(value, six.text_type):
            for format in self.input_formats:
                try:
                    # strptime provides the floor by default
                    return datetime.date(*time.strptime(value, format)[:3])
                except (ValueError, TypeError):
                    continue
        raise ValidationError(self.error_messages['invalid'],
                              code='invalid')


class CeilingDateField(DateField):
    """Implements a DateField where partial input is accepted.

    Uses django.forms.fields.DateField as a starting point, and then allows
    users to input partial dates such as 2011-12. However, instead of assuming
    such dates correspond with the first of the month, it assumes that such
    dates represent the *last* day of the month. This allows a search for all
    documents "After 2010" to work.
    """
    input_formats = INPUT_FORMATS + formats.get_format('DATE_INPUT_FORMATS')

    @staticmethod
    def _calculate_extra_days(date_format, d):
        """Given a date and a format, calculate how many days to add to it to
        create the correct ceiling date.
        """
        if date_format.count('%') == 1:
            if calendar.isleap(d.year):
                num_days = 366
            else:
                num_days = 365
        elif date_format.count('%') == 2:
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

    def to_python(self, value):
        """
        Validates that the input can be converted to a date. Returns a
        Python datetime.datetime object.
        """
        if value in validators.EMPTY_VALUES or value == "YYYY-MM-DD":
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        unicode_value = force_text(value, strings_only=True)
        if isinstance(unicode_value, six.text_type):
            value = unicode_value.strip()
        # If unicode, try to strptime against each input format.
        if isinstance(value, six.text_type):
            for format in self.input_formats:
                try:
                    valid_date = datetime.date(*time.strptime(value, format)[:3])
                except ValueError:
                    continue
                additional_days = self._calculate_extra_days(format, valid_date)

                return valid_date + datetime.timedelta(days=additional_days)
        raise ValidationError(self.error_messages['invalid'],
                              code='invalid')
