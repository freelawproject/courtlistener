from django.utils.timezone import now
from cl.stats.models import Stat
from django.db.models import F


def tally_stat(name, inc=1, date_logged=now()):
    """Tally an event's occurrence to the database.

    Will assume the following overridable values:
       - the event happened today.
       - the event happened once.
    """
    s, created = Stat.objects.get_or_create(name=name, date_logged=date_logged,
                                            defaults={'count': inc})
    if created:
        return s.count
    else:
        count_cache = s.count
        s.count = F('count') + inc
        s.save()
        # s doesn't have the new value when it's updated with a F object, so we
        # fake the return value instead of looking it up again for the user.
        return count_cache + inc


def clear_stats(name, clear_date=now()):
    """Clears the stats for the name-date pair requested.

    If clear_date is None, it will clear all dates for the name.
    """
    if clear_date is None:
        Stat.objects.filter(name=name).delete()
    else:
        Stat.objects.filter(name=name, date_logged=clear_date).delete()


def set_stat(name, value, set_date=now()):
    """Sets the value for the name-date pair requested.

    Returns the value if possible, or None if unable to complete.
    """
    try:
        s = Stat.objects.get(name=name, date=set_date)
        s.count = value
        s.save()
        return s.count
    except Stat.DoesNotExist:
        return None
