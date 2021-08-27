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


def _argparse_volumes(volumes_arg: str) -> range:
    """Custom argparse handling for volumes

    :param volumes_arg: The volume argparse for harvard imports
    :return: Range of values
    """
    volumes = [int(e) if e.strip() else 2000 for e in volumes_arg.split(":")]
    if len(volumes) == 1:
        start = stop = volumes[0]
    else:
        start, stop = volumes[0], volumes[1] + 1
    return range(start, stop)
