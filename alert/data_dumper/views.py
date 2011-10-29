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

from alert.search.models import Court
from alert.search.models import Document
from alert.lib.db_tools import queryset_iterator
from alert.lib.dump_lib import make_dump_file
from alert.lib.dump_lib import get_date_range
from alert.lib.filesize import size
from alert.settings import DUMP_DIR

from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext

import os
from datetime import date

def dump_index(request):
    '''Shows an index page for the dumps.'''
    courts = Court.objects.all().order_by('startDate')
    try:
        dump_size = size(os.path.getsize(os.path.join(DUMP_DIR, 'all.xml.gz')))
    except os.error:
        dump_size = '2.1GB'
    return render_to_response('dumps/dumps.html', {'courts' : courts,
        'dump_size': dump_size}, RequestContext(request))


def serve_or_gen_dump(request, court, year=None, month=None, day=None):
    if year is None:
        if court != 'all':
            # Sanity check
            return HttpResponseBadRequest('<h2>Error 400: Complete dumps are \
                not available for individual courts.</h2>')
        else:
            # Serve the dump for all cases.
            return HttpResponseRedirect('/dumps/all.xml.gz')

    else:
        # Date-based dump
        start_date, end_date, annual, monthly, daily = get_date_range(
            year, month, day)

        # Ensure that it's a valid request.
        today = date.today()
        today_str = '%d-%02d-%02d' % (today.year, today.month, today.day)
        if (today_str < end_date) and (today_str < start_date):
            # It's the future. They fail.
            return HttpResponseBadRequest('<h2>Error 400: Requested date is in\
                the future. Please try again later.</h2>')
        elif today_str <= end_date:
            # Some of the data is in the past, some could be in the future.
            return HttpResponseBadRequest('<h2>Error 400: Requested date is \
                partially in the future. Please try again later.</h2>')

    filename = court + '.xml'
    if daily:
        filepath = os.path.join(year, month, day)
    elif monthly:
        filepath = os.path.join(year, month)
    elif annual:
        filepath = os.path.join(year)

    path_from_root = os.path.join(DUMP_DIR, filepath)

    # See if we already have it cached.
    try:
        _ = open(os.path.join(path_from_root, filename), 'rb')
        return HttpResponseRedirect(os.path.join('/dumps', filepath, filename))

    except IOError:
        # Time-based dump
        if court == 'all':
            # dump everything.
            docs_to_dump = queryset_iterator(Document.objects.filter(
                 dateFiled__gte=start_date, dateFiled__lte=end_date))
        else:
            # dump just the requested court
            docs_to_dump = queryset_iterator(Document.objects.filter(
               dateFiled__gte=start_date, dateFiled__lte=end_date,
               court=court))

        make_dump_file(docs_to_dump, path_from_root, filename)

        return HttpResponseRedirect(os.path.join('/dumps', filepath, filename)
                                    + '.gz')
