import calendar
import datetime
import time
from calendar import monthrange

from django.core import validators
from django.core.exceptions import ValidationError
from django.utils import formats
from django.utils.translation import ugettext_lazy as _
from django.forms import DateField
from django.forms.fields import Field
from django.forms.widgets import DateTimeInput


class FloorDateField(DateField):
    """Simply overrides the DateField to give it a better name. Corrects
    placeholder value where browsers fail to implement it correctly."""
    def __init__(self, input_formats=None, *args, **kwargs):
        super(FloorDateField, self).__init__(*args, **kwargs)
        self.input_formats = input_formats

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
        for format in self.input_formats or formats.get_format('DATE_INPUT_FORMATS'):
            try:
                value = value.strip()
                return datetime.date(*time.strptime(value, format)[:3])
            except ValueError:
                continue
        raise ValidationError(self.error_messages['invalid'])


class CeilingDateField(Field):
    """Implements a DateField where partial input is accepted.

    Uses django.forms.fields.DateField as a starting point, and then allows
    users to input partial dates such as 2011-12. However, instead of assuming
    such dates correspond with the first of the month, it assumes that such
    dates represent the *last* day of the month. This allows a search for all
    documents "After 2010" to work.
    """
    widget = DateTimeInput
    default_error_messages = {
        'invalid': _(u'Enter a valid date/time.'),
    }

    def __init__(self, input_formats=None, *args, **kwargs):
        super(CeilingDateField, self).__init__(*args, **kwargs)
        self.input_formats = input_formats

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
        for format in self.input_formats or formats.get_format('DATETIME_INPUT_FORMATS'):
            try:
                value = value.strip()
                valid_date = datetime.date(*time.strptime(value, format)[:3])
            except ValueError:
                continue
            if format.count('%') == 1:
                # The user only provided a year. Add one year to their input.
                if calendar.isleap(valid_date.year):
                    num_days = 366 - 1
                else:
                    num_days = 365 - 1
            elif format.count('%') == 2:
                # The user provided a year and a month. Add a month to their input.
                num_days = monthrange(valid_date.year, valid_date.month)[1] - 1
            else:
                # A full date was provided (for completeness)
                num_days = 0
            return valid_date + datetime.timedelta(days=num_days)
        raise ValidationError(self.error_messages['invalid'])
