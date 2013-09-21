from datetime import date
from alert.stats.models import Stat
from django.db.models import F


def tally_stat(name, inc=1, date_logged=date.today()):
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
