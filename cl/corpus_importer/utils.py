from datetime import date
from typing import Optional

from django.utils.timezone import now

from cl.search.models import Docket


def mark_ia_upload_needed(d: Docket, save_docket: bool) -> None:
    """Mark the docket as needing upload if it's not already marked.

    The point here is that we need to know the first time an item was updated,
    not the *most recent* time it was updated. This way, we know how long it
    has been since it was last uploaded to Internet Archive, and whether it's
    time for us to do so.

    :param d: The docket to mark
    :param save_docket: Whether to save the docket or just modify it in place
    :return: None
    """
    if not d.ia_needs_upload:
        d.ia_needs_upload = True
        d.ia_date_first_change = now()
    if save_docket:
        d.save()


def get_start_of_quarter(d: Optional[date] = None) -> date:
    """Get the start date of the  calendar quarter requested

    :param d: The date to get the start date for. If None, then use current
    date/time.
    """
    if d is None:
        d = now().date()

    d_year = d.year
    quarter_dates = [
        date(d_year, 1, 1),
        date(d_year, 4, 1),
        date(d_year, 7, 1),
        date(d_year, 10, 1),
    ]
    return max([q for q in quarter_dates if q <= d])
