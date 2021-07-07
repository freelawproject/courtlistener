import argparse
import os

from dateutil import parser
from django.utils.timezone import is_naive, make_aware, utc

# Note: for files see argparse.FileType!


def valid_date(s):
    try:
        return parser.parse(s).date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Unable to parse date, {s}")


def valid_date_time(s):
    try:
        d = parser.parse(s)
        if is_naive(d):
            d = make_aware(d, utc)
        return d
    except ValueError:
        raise argparse.ArgumentTypeError(f"Unable to parse date/time, {s}")


def readable_dir(prospective_dir):
    if not os.path.isdir(prospective_dir):
        raise argparse.ArgumentTypeError(
            f"readable_dir:{prospective_dir} is not a valid path"
        )
    if os.access(prospective_dir, os.R_OK):
        return prospective_dir
    else:
        raise argparse.ArgumentTypeError(
            f"readable_dir:{prospective_dir} is not a readable dir"
        )
