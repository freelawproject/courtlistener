import argparse
import csv
import os

from dateutil import parser
from django.utils.timezone import is_naive, make_aware, utc

from cl.audio.models import Audio
from cl.people_db.models import Person
from cl.search.models import Opinion


def valid_date(s):
    try:
        return parser.parse(s).date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Unable to parse date, %s" % s)


def valid_date_time(s):
    try:
        d = parser.parse(s)
        if is_naive(d):
            d = make_aware(d, utc)
        return d
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Unable to parse date/time, %s" % s)


def csv_list(s):
    for row in csv.reader([s]):
        # Just return the first row, parsed into a list.
        return row


def readable_dir(prospective_dir):
    if not os.path.isdir(prospective_dir):
        raise argparse.ArgumentTypeError(
            "readable_dir:{0} is not a valid path".format(prospective_dir))
    if os.access(prospective_dir, os.R_OK):
        return prospective_dir
    else:
        raise argparse.ArgumentTypeError(
            "readable_dir:{0} is not a readable dir".format(prospective_dir))


def valid_obj_type(s):
    options = ('opinions', 'audio', 'people')
    if s.lower() == 'opinions':
        return Opinion
    elif s.lower() == 'audio':
        return Audio
    elif s.lower() == 'people':
        return Person
    else:
        raise argparse.ArgumentTypeError(
            "Unable to parse type, %s. Valid options are %s" % (s, options))
