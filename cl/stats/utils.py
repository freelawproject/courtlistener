from collections import OrderedDict

from django.db.models import F
from django.utils.timezone import now

from cl.stats.models import Stat

MILESTONES = OrderedDict((
    ('XXS',  [1e0, 5e0]),         # 1 - 5
    ('XS',   [1e1, 2.5e1, 5e1,   # 10 - 500
              1e2, 2.5e2, 5e2]),
    ('SM',   [1e3, 2.5e3, 5e3,   # 1_000 - 50_000
              1e4, 2.5e4, 5e4]),
    ('MD',   [1e5, 2.5e5, 5e5]),  # 100_000 - 500_000
    ('LG',   [1e6, 2.5e6, 5e6]),  # 1M - 5M
    ('XL',   [1e7, 2.5e7, 5e7]),  # 10M - 50M
    ('XXL',  [1e8, 2.5e8, 5e8]),  # 100M - 500M
    ('XXXL', [1e9, 2.5e9, 5e9]),  # 1B - 5B
))

MILESTONES_FLAT = sorted([item for sublist in MILESTONES.values()
                          for item in sublist])


def get_milestone_range(start, end):
    """Return the flattened MILESTONES by range of their keys.

    >>> get_milestone_range('MD', 'LG')
    [1e5, 2.5e5, 5e5, 1e6, 2.5e6, 5e6]
    """
    out = []
    extending = False
    for key, values in MILESTONES.items():
        if key == start:
            extending = True
        if extending is True:
            out.extend(values)
            if key == end:
                break
    return out


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
