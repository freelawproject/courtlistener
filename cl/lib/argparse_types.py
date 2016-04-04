import argparse
import csv
import os

from dateutil import parser
from django.utils.timezone import is_naive, make_aware, utc

from cl.audio.models import Audio
from cl.search.models import Opinion, Docket


def valid_date(s):
    try:
        return parser.parse(s).date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Unable to parse date, %s" % s)

def valid_source(src):
    options_dict = {'recap': Docket.RECAP}

    lsrc = src.lower()
    if lsrc not in options_dict.keys():
        raise argparse.ArgumentTypeError("Unable to parse type %s"%src)
    else:
        return options_dict[lsrc]

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
    options = ('opinions', 'audio', 'dockets')
    if s.lower() == 'opinions':
        return Opinion
    elif s.lower() == 'audio':
        return Audio
    elif s.lower() == 'dockets':
        return Docket
    else:
        raise argparse.ArgumentTypeError(
            "Unable to parse type, %s. Valid options are %s" % (s, options))
