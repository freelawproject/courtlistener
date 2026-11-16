"""Helpers for converting dates and times to a court's timezone."""

from datetime import date, datetime, time

import pytz
from django.utils.timezone import is_naive

from cl.recap.constants import COURT_TIMEZONES


def convert_to_court_timezone(
    court_id: str, datetime_filed: datetime
) -> datetime:
    """Convert a docket entry datetime filed to the court timezone it belongs to.

    Args:
        datetime_filed: The docket entry datetime filed
        court_id: The court id to which docket entries belong, used for
            timezone conversion.

    Returns:
        A datetime object in the court timezone.
    """
    court_timezone = pytz.timezone(COURT_TIMEZONES.get(court_id, "US/Eastern"))
    return datetime_filed.astimezone(court_timezone)


def localize_date_and_time(
    court_id: str, date_filed: date | datetime
) -> tuple[date, time | None]:
    """Localize the date and time into local court timezone, split it into date and time.

    If given a "naive datetime" (no timezone information), assume the
    time is in the court's local time. and return timezone-aware date
    and time objects. If given a timezone-aware datetime, convert it
    to the court's local timezone and return timezone-aware date and
    time objects.

    Args:
        court_id: The court_id to get the timezone from.
        date_filed: The date or datetime instance provided by the source.

    Returns:
        A tuple of date_filed and time_filed or None if no time available.
    """
    if isinstance(date_filed, datetime):
        if is_naive(date_filed):
            datetime_filed_local = localize_naive_datetime_to_court_timezone(
                court_id, date_filed
            )
        else:
            datetime_filed_local = convert_to_court_timezone(
                court_id, date_filed
            )
        time_filed = datetime_filed_local.time()
        date_filed = datetime_filed_local.date()
        return date_filed, time_filed
    return date_filed, None


def localize_naive_datetime_to_court_timezone(
    court_id: str, naive_datetime: datetime
) -> datetime:
    """Convert a naive datetime to the provided court timezone it belongs to.

    Args:
        naive_datetime: The naive datetime to localize.
        court_id: The court_id to get the timezone from.

    Returns:
        A datetime object in the court timezone.
    """
    court_timezone = pytz.timezone(COURT_TIMEZONES.get(court_id, "US/Eastern"))
    d = court_timezone.localize(naive_datetime)
    return d
