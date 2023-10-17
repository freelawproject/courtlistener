from datetime import date, datetime, time

import pytz
from django.utils.timezone import is_naive

from cl.recap.constants import COURT_TIMEZONES


def convert_to_court_timezone(
    court_id: str, datetime_filed: datetime
) -> datetime:
    """Convert a docket entry datetime filed to the court timezone it belongs
    to.

    :param datetime_filed: The docket entry datetime filed
    :param court_id: The court id to which docket entries belong, used for
    timezone conversion.
    :return: A datetime object in the court timezone.
    """
    court_timezone = pytz.timezone(COURT_TIMEZONES.get(court_id, "US/Eastern"))
    return datetime_filed.astimezone(court_timezone)


def localize_date_and_time(
    court_id: str, date_filed: date | datetime
) -> tuple[date, time | None]:
    """Localize the date and time into local court timezone, split it into
    date and time.

    :param court_id: The court_id to get the timezone from.
    :param date_filed: The date or datetime instance provided by the source.
    :return: A tuple of date_filed and time_filed or None if no time available.
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

    :param naive_datetime: The naive datetime to localize.
    :param court_id: The court_id to get the timezone from.
    :return: A datetime object in the court timezone.
    """

    court_timezone = pytz.timezone(COURT_TIMEZONES.get(court_id, "US/Eastern"))
    d = court_timezone.localize(naive_datetime)
    return d
