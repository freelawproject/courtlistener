# -*- coding: utf-8 -*-

from dateutil.parser import _timelex, parser
from datetime import datetime

p = parser()
info = p.info

def timetoken(token):
    try:
        float(token)
        return True
    except ValueError:
        pass
    return any(f(token) for f in (info.jump, info.weekday, info.month, info.hms, info.ampm, info.pertain, info.utczone, info.tzoffset))


def timesplit(input_string):
    batch = []
    for token in _timelex(input_string):
        if timetoken(token):
            if info.jump(token):
                continue
            batch.append(token)
        else:
            if batch:
                yield " ".join(batch)
                batch = []
    if batch:
        yield " ".join(batch)


def parse_dates(s, debug=False):
    '''Parse dates out of a string

    Based on http://stackoverflow.com/questions/7028689/, this method runs is
    a wrapper for the above two functions. It simply takes a string, splits it
    accordingly, and then finds dates within it.

    Since there are many false positives, it tries to remove them while catching
    any errors. To do this, dates in the year 1900 or on Christmas are never
    returned.

    returns a list of dates
    '''
    # Default is set to Christmas, 1900.
    DEFAULT = datetime(1900, 12, 25)
    dates = []
    for item in timesplit(s):
        #print "Found:", item
        try:
            date = p.parse(item, default=DEFAULT)
            if date.year != DEFAULT.year and (date.month != DEFAULT.month and date.day != DEFAULT.day):
                if debug:
                    print "Item %s parsed as: %s" % (item, date)
                dates.append(date)
        except ValueError:
            pass
        except TypeError:
            pass

    return dates

