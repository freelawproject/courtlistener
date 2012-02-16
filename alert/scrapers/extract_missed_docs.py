# -*- coding: utf-8 -*-
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
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.


import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.search.models import Court
from alert.search.models import Document

# adding alert to the front of this breaks celery. Ignore pylint error.
from scrapers.tasks import extract_doc_content

import datetime
import time
import traceback
from optparse import OptionParser


def extract_all_docs(court, filter_time):
    '''
    Here, we do the following:
     1. For a given court, find all of its documents
     2. Determine if the document has been parsed already
     3. If it has, punt, if not, open the PDF and parse it.

    returns a string containing the result
    '''

    print "NOW PARSING COURT: %s" % court

    # select all documents from this jurisdiction that lack plainText and were
    # downloaded from the court.
    docs = Document.objects.filter(documentPlainText="", documentHTML="",
                                   court__courtUUID=court, source="C",
                                   dateFiled__gte=filter_time)

    num_docs = docs.count()
    if num_docs == 0:
        print "Nothing to parse for this court."
    else:
        print "%s documents in this court." % (num_docs,)
        for doc in docs:
            extract_doc_content.delay(doc.pk)


def main():
    usage = "usage: %prog -c COURTID -t datetime"
    parser = OptionParser(usage)
    parser.add_option('-c', '--court', dest='court_id', metavar="COURTID",
        help="The court to extract. Use 0 to extract all courts.")
    parser.add_option('-t', '--time', dest='filter_time', metavar='filter_time',
        help=("Take action for all documents newer than this time. Format as ",
              "follows: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD"))
    options, _ = parser.parse_args()

    court = options.court_id

    filter_time = options.filter_time
    if filter_time is not None:
        try:
            # Parse the date string into a datetime object
            filter_time = datetime.datetime(*time.strptime(options.filter_time, "%Y-%m-%d %H:%M:%S")[0:6])
        except ValueError:
            try:
                filter_time = datetime.datetime(*time.strptime(options.filter_time, "%Y-%m-%d")[0:5])
            except ValueError:
                parser.error("Unable to parse time. Please use format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD")
    else:
        # Without a time filter, this query is locking, taking a long time.
        parser.error('Time is a required argument.')

    if court == 'all':
        # get the court IDs from models.py
        courts = Court.objects.filter(in_use=True).values_list('courtUUID', flat=True)
        for court in courts:
            # This catches all exceptions regardless of their trigger, so
            # if one court dies, the next isn't affected.
            try:
                extract_all_docs(court, filter_time)
            except Exception:
                print '*****Uncaught error parsing court*****\n"' + traceback.format_exc() + "\n\n"
    else:
        # We just do the court requested
        extract_all_docs(court, filter_time)

    exit(0)

if __name__ == '__main__':
    main()
