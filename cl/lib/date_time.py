import pytz

from datetime import datetime, time


def midnight_pst(d):
    """Cast a naive date object to midnight PST"""
    pst = pytz.timezone('US/Pacific')
    d = datetime.combine(d, time()).replace(tzinfo=pst)
    return d
