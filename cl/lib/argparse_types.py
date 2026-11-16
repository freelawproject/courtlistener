"""Argument types for validating command-line arguments."""

import argparse
import os
from datetime import UTC, date, datetime

from dateutil import parser
from django.utils.timezone import is_naive, make_aware

# Note: for files see argparse.FileType!


def valid_date(s: str) -> date:
    """Parse an argument as a date.

    Raises:
        argparse.ArgumentTypeError: If the argument can't be parsed.
    """
    try:
        return parser.parse(s).date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Unable to parse date, {s}")


def valid_date_time(s: str) -> datetime:
    """Parse an argument as a datetime, treating naive values as UTC.

    Raises:
        argparse.ArgumentTypeError: If the argument can't be parsed.
    """
    try:
        d = parser.parse(s)
        if is_naive(d):
            d = make_aware(d, UTC)
        return d
    except ValueError:
        raise argparse.ArgumentTypeError(f"Unable to parse date/time, {s}")


def readable_dir(prospective_dir: str) -> str:
    """Check that an argument is a readable directory.

    Raises:
        argparse.ArgumentTypeError: If the path isn't a directory or isn't
            readable.
    """
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


def _argparse_volumes(volumes_arg: str) -> list[int]:
    """Custom argparse handling for volumes.

    Args:
        volumes_arg: The volume argparse for harvard imports

    Returns:
        Range of values
    """
    if ":" not in volumes_arg:
        return [int(volumes_arg)]
    volumes = [int(e) if e.strip() else 2000 for e in volumes_arg.split(":")]
    if len(volumes) == 1:
        start = stop = volumes[0]
    else:
        start, stop = volumes[0], volumes[1] + 1
    return list(range(start, stop))
