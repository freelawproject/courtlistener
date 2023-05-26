from datetime import date, datetime, time

import pytz
from django.conf import settings
from django.utils.timezone import is_aware


def midnight_pt(d: date) -> datetime:
    """Cast a naive date object to midnight Pacific Time, PST or PDT according
    to the date.
    """
    pst = pytz.timezone("US/Pacific")
    d = datetime.combine(d, time())
    d = pst.localize(d)
    return d


def dt_as_local_date(dt: datetime) -> date:
    """Convert a datetime to a localized date

    Datetimes are stored in the DB in UTC. Dates are handled a bit differently:

      1. If a tz-aware datetime is added to a date field in the DB, it's
         converted to UTC, then the time and tz info is removed, leaving only
         the date.

      2. If a date is added to the DB, it's just added as is (no conversion is
         needed or indeed possible).

    This function takes a datetime — typically in UTC — and converts it to a
    date that's in the server's localtime.

    This is useful for comparing dates in the DB to datetimes in the DB (not
    that I recommend it).

    :param dt: A tz-aware datetime object to convert
    :returns A date object
    """
    assert is_aware(dt), "dt must be a timezone-aware datetime object"
    return dt.astimezone(pytz.timezone(settings.TIME_ZONE)).date()
