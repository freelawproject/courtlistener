#!/usr/bin/python

__author__ = 'mlissner'

import argparse
from datetime import datetime

INPUT_FORMATS = [
    '%Y-%m-%d',  # '2006-10-25'
    '%m-%d-%Y',  # '10-25-2006'
    '%m-%d-%y',  # '10-25-06'
    '%m/%d/%Y',  # '10/25/2006'
    '%m/%d/%y',  # '10/25/06'
    '%Y/%m/%d',  # '2006/10/26'
]


def make_date(date_string):
    for format in INPUT_FORMATS:
        try:
            return datetime.strptime(date_string, format).date()
        except ValueError:
            continue
            # If we made it this far, we can't handle the date.
    raise argparse.ArgumentTypeError("Unable to parse date, %s" % date_string)


def main():
    parser = argparse.ArgumentParser(description='Describe me')
    parser.add_argument('-m', '--my-foo', default=True, required=False,
                        action='store_true',
                        help='Do we foo it?')
    parser.add_argument('-f', '--file', type=file,
                        help='The path to the file.')
    parser.add_argument('-d', '--date', type=make_date,
                        help='How far back should we eat pie?')
    args = parser.parse_args()


if __name__ == '__main__':
    main()
