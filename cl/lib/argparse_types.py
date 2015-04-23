import argparse
import csv
import os
from cl.audio.models import Audio
from cl.search.models import Document
from dateutil import parser
from django.utils.timezone import is_naive, make_aware, utc



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
    if s == 'opinions':
        return Document
    elif s == 'audio':
        return Audio
    else:
        raise argparse.ArgumentTypeError("Unable to parse type, %s" % s)
