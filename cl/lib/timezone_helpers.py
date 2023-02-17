from datetime import date, datetime, time

import pytz

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
        datetime_filed_local = convert_to_court_timezone(court_id, date_filed)
        time_filed = datetime_filed_local.time()
        date_filed = datetime_filed_local.date()
        return date_filed, time_filed
    return date_filed, None
