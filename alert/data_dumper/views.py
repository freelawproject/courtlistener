# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import calendar
import os

from alert.lib.db_tools import *
from alert.settings import DUMP_DIR
from datetime import date
from datetime import datetime
from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext

def dump_index(request, year=None, month=None, day=None):
    '''Shows index pages for the dumps.

    If no date is provided, it's the root index page. Show general information.
    If a year is provided, show the possible annual dumps, and whether they
    have already been generated. Ditto for month and day.
    '''

    ################################
    #### THIS CODE IS OLD ##########
    ##### REWRITE NEEDED ###########
    ################################
    os.chdir(DUMP_DIR)

    dump_files = os.listdir('.')
    dump_files.sort()
    dumps_info = []
    latest_dumps_info = []
    for dump_file in dump_files:
        # For each file, gather up the information about it
        dump = []
        # Creation date
        dump.append(datetime.fromtimestamp(os.path.getctime(dump_file)))
        # Filename
        dump.append(dump_file)
        # Filesize
        dump.append(os.stat(dump_file)[6])

        if 'latest' in dump_file:
            latest_dumps_info.append(dump)
        else:
            dumps_info.append(dump)

    return render_to_response('dumps/dumps.html', {'dumps_info': dumps_info,
        'latest_dumps_info': latest_dumps_info}, RequestContext(request))


def get_date_range(year, month, day):
    ''' Create a date range to be queried.

    Given a year and optionally a month or day, return a date range. If only a
    year is given, return start date of January 1, and end date of December
    31st. Do similarly if a year and month are supplied or if all three values
    are provided.
    '''
    # Sort out the start dates
    if day == None:
        start_day = 1
    else:
        start_day = day
    if month == None:
        start_month = 1
    else:
        start_month = month

    start_year = year
    start_date = '%d-%02d-%02d' % (start_year, start_month, start_day)

    annual  = False
    monthly = False
    daily   = False
    # Sort out the end dates
    if day == None and month == None:
        # it's an annual query
        annual = True
        end_month = 12
        end_day = 31
    elif day == None:
        # it's a month query
        daily = True
        end_month = month
        end_day = calendar.monthrange(year, end_month)[1]
    else:
        # all three values provided!
        daily = True
        end_month = month
        end_day = day

    end_year = year
    end_date = '%d-%02d-%02d' % (end_year, end_month, end_day)

    return start_date, end_date, annual, monthly, daily


def set_cache_dump_or_die(start_date, end_date):
    '''Sets whether the dump should be cached/loaded from cache.

    Tests if the end date is before or after today. If it's after or equal,
    then we don't want to cache the file to disk. If it's before, we do.

    If the end date and the start date are after today, then we throw an error,
    since this means the date is in the future.

    Uses string comparisons for dates, but it should be fine.
    '''
    today = date.today()
    today_str  = '%d-%02d-%02d' % (today.year, today.month, today.day)

    if today_str <= end_date:
        cache_dump = False
    else:
        cache_dump = True

    if not cache_dump and (today_str < start_date):
        # It's the future. They fail.
        return HttpResponseBadRequest('<h1>Requested date is in the future.</h1>')

    return cache_dump


def serve_or_gen_dump(request, year, month=None, day=None, court):
    start_date, end_date, annual, monthly, daily = get_date_range(year, month, day)
    cache_dump = set_cache_dump_or_die(start_date, end_date)

    if daily:
        filepath = os.path.join(year, month, day, court + '.xml.gz')
    elif monthly:
        filepath = os.path.join(year, month, court + '.xml.gz')
    elif annual:
        filepath = os.path.join(year, court + '.xml.gz')

    # see if it's available on disk
    try:
        if cache_dump:
            f = open(os.path.join(DUMP_DIR, filepath), 'rb')
            return HttpResponseRedirect(os.path.join('dumps', filepath))

    except IOError:
        # The file doesn't yet exist on disk. Make it and redirect to it.

        # If no results for that date, return 404.


    if court == 'all':
        # dump everything.
        docs_to_dump = queryset_iterator(Document.objects.all())
    else:
        # dump just the requested court
        docs_to_dump = queryset_iterator(Document.objects.filter(court = court))
    pass
