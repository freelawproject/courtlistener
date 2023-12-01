from django.db.models import Min, Q

from cl.people_db.models import Person
from cl.search.models import SOURCES, Court, Opinion


def get_scotus_judges(d):
    """Get the panel of scotus judges at a given date."""
    return Person.objects.filter(  # Find all the judges...
        Q(positions__court_id="scotus"),  # In SCOTUS...
        Q(positions__date_start__lt=d),  # Started as of the date...
        Q(positions__date_retirement__gt=d)
        | Q(positions__date_retirement=None),  # Haven't retired yet...
        Q(positions__date_termination__gt=d)
        | Q(positions__date_termination=None),  # Nor been terminated...
        Q(date_dod__gt=d) | Q(date_dod=None),  # And are still alive.
    ).distinct()


def get_min_dates():
    """returns a dictionary with key-value (courtid, minimum date)"""
    min_dates = {}
    courts = Court.objects.exclude(
        dockets__clusters__source__contains=SOURCES.COLUMBIA_ARCHIVE
    ).annotate(earliest_date=Min("dockets__clusters__date_filed"))
    for court in courts:
        min_dates[court.pk] = court.earliest_date
    return min_dates


def get_path_list():
    """Returns a set of all the local_path values so we can avoid them in
    later imports.

    This way, when we run a second, third, fourth import, we can be sure not
    to import a previous item.
    """
    return set(
        (
            Opinion.objects.exclude(local_path="").values_list(
                "local_path", flat=True
            )
        )
    )


def get_courtdates():
    """returns a dictionary with key-value (courtid, founding date)"""
    start_dates = {}
    courts = Court.objects
    for court in courts:
        start_dates[court.pk] = court.start_date
    return start_dates


def get_min_nocite():
    """Return a dictionary indicating the earliest case with no citations for
    every court.

    {'ala': Some-date, ...}
    """
    min_dates = {}
    courts = Court.objects.filter(
        dockets__clusters__citations__isnull=True
    ).annotate(earliest_date=Min("dockets__clusters__date_filed"))
    for court in courts:
        min_dates[court.pk] = court.earliest_date
    return min_dates
