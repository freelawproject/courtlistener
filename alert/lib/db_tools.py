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

from datetime import date
from datetime import datetime
from datetime import timedelta
from alert.settings import *

def queryset_generator(queryset, chunksize=1000):
    '''
    from: http://djangosnippets.org/snippets/1949/
    Iterate over a Django Queryset ordered by the primary key

    This method loads a maximum of chunksize (default: 1000) rows in its
    memory at the same time while django normally would load all rows in its
    memory. Using the iterator() method only causes it to not preload all the
    classes.

    Note that the implementation of the iterator does not support ordered query sets.
    '''
    if DEVELOPMENT:
        chunksize = 5

    documentUUID = 0
    last_pk = queryset.order_by('-pk')[0].documentUUID
    queryset = queryset.order_by('pk')
    while documentUUID < last_pk:
        for row in queryset.filter(documentUUID__gt=documentUUID)[:chunksize]:
            documentUUID = row.documentUUID
            yield row

def queryset_generator_by_date(queryset, date_field, start_date, end_date, chunksize=7):
    '''
    Takes a queryset, and chunks it by date. Useful if sorting by pk isn't 
    needed.
    
    Chunksize should be given in days, and start and end dates should be provided
    as strings in the form 2012-03-08.
    '''
    chunksize = timedelta(chunksize)
    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    bottom_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    top_date = bottom_date + chunksize - timedelta(1)
    while bottom_date <= end_date:
        print "bottom-date: %s" % bottom_date
        print "top_date: %s" % top_date
        keywords = {'%s__gte' % date_field : bottom_date,
                    '%s__lte' % date_field : top_date}
        bottom_date = bottom_date + chunksize
        top_date = top_date + chunksize
        if top_date > end_date:
            # Last iteration
            top_date = end_date
        for row in queryset.filter(**keywords):
            yield row





