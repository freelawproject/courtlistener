#!/usr/bin/env python

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

import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import sys
sys.path.append("/var/www/court-listener")

from django import db
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.template.defaultfilters import slugify
from django.utils.encoding import smart_str, smart_unicode
from alert.alertSystem.models import Court, Citation, Document
from alert.lib.parse_dates import parse_dates
from alert.lib.string_utils import trunc
from alert.lib.scrape_tools import hasDuplicate

from lxml.html import fromstring, tostring
from urlparse import urljoin
import datetime
import re
import subprocess
import time
import urllib2


def build_date_range(dateFiled, range=5):
    '''Build a date range to be handed off to a sphinx query

    This builds an array that can be handed off to Sphinx in order to complete
    a date range filter. The range is set to a default of 5 days, which makes
    an 11-value array, but other values can be set as well.
    '''
    dateRange = []
    i = range
    # first we add range days before the dateFiled
    while i > 0:
        dateRange.append(dateFiled - i)
        i -= 1

    # next, we add the date itself
    dateRange.append(dateFiled)

    # finally, we add five days after
    i = 1
    while i <= range:
        dateRange.append(dateFiled + i)
        i += 1

    return dateRange


def load_stopwords():
    '''Loads Sphinx's stopwords file.

    Pulls in Sphinx's stopwords file and returns the words as an array to the
    calling function.
    '''
    #  /usr/local/sphinx/bin/indexer -c sphinx-scraped-only.conf scraped-document --buildstops word_freq.txt 1000 --buildfreqs
    stopwords_file = open('/var/www/court-listener/Resource.org/bin/word_freq.txt', 'r')
    stopwords = []
    for word in stopwords:
        stopwords.append(word)

    stopwords_file.close()
    return stopwords


def extract_words(content, count=15):
    '''Grab words from the content and returns them to the caller.

    This function attempts to choose words from the content that the calling
    function would return the fewest cases if searched for. There are two
    eliminations: stopwords and headers/footers. To avoid these, we pick words
    from the middle sections of the document, and eliminate stopwords.
    '''
    stopwords = load_stopwords()
    words = content.split()
    length = len(words)
    gap = int(length/(count + 1))
    i = 1
    query_words = []
    while i <= count:
        stopwords_hit_count = 0
        onwards = True
        while onwards:
            # checks that the new_word isn't a stopword, and moves forward
            # until a non-stopword is found.
            loc = ((gap + 1) * i) + stopwords_hit_count
            new_word = words[loc]
            if new_word in stopwords:
                stopwords_hit_count += 1
                if (loc + 1) > length:
                    # we've passed the end of the doc.
                    return query_words
                else:
                    onwards = True
            else:
                onwards = False
        i += 1
        query_words.append(new_word)

    return query_words


def check_dup(court, dateFiled, caseName, content):
    '''Checks for a duplicate that already exists in the DB

    This is the only major difference (so far) from the F2 import process. This
    function will take various pieces of meta data from the F3 scrape, and will
    compare them to what's already known in the database.

    Returns the duplicates as a queryset or None, depending on whether there's
    a dup.
    '''
    '''
    Known data at runtime:
        - content of case
            - pick three phrases from F3. If they're in the search index, that
              probably means a match.
                - q: how to pick these so that rare terms are selected?
                  a: pick them from the middle, 1/5 of the way and 4/5 of the
                     way through.
        - casename
            - Using the similarity matching algo we used to clean up SCOTUS
              dates, we can see how similar two casenames are.
            - need to determine a good threshold here.
        - date
            - Using this as a limiter could be useful. A one-month range on
              either side of the case should wean down the results.
        - docket number
            - Could be useful, but not available in all courts, nor consistent
              within F3.
        - west citation
            - Useless - we lack these in the DB.
        - sha1 of the case text
            - useless. We lack textual sha1s in our DB.
        - court
           - high certainty
           - excellent limiter
        - document type
            - medium certainty - is often correct in each case, but not always.
            - could serve as a useful signal, but not good enough.

    Process:
        1 find all cases from $court within a one month range of $date
        2 place three queries from 2/5, 3/5 and 4/5 of the way through, and
          gather the intersection of their results. Need to remove stopwords.
          If the words in the three selections are ever the same, find new ones.
          If there are fewer than 19 non-stopwords, then don't bother finding new
          words, since the words will have to overlap.
        3 intersect the results from step 1 and 2.
        4 of the remaining values, see if any have matching case names. If so,
          consider it a match.
        5 check the docket number. If it matches, up the probability of a match.


    Test doc:
      - http://courtlistener.com/ca1/23hD/ramallo-brothers-v-el-dia-inc/
      - http://bulk.resource.org/courts.gov/c/F3/490/490.F3d.86.06-2512.html
    '''
    # Phase 1: find all cases within 5 days of the found case in the given court
    query =  '@court %s' % court
    queryset = Document.search.query(query)
    docs_by_court_and_date = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
        .filter(dateFiled=build_date_range(dateFiled))

    # Phase 2: place queries onto the search index until a small result set is
    # found.
    init_num_words = 15
    words = extract_words(content, init_num_words)
    query = ' '.join(words)

    # Add five words until either you run out of words or you get less than
    # 100 results.
    results = 101
    extracted_words = init_num_words
    word_count = len(content.split())
    queryset = Document.search.query(query)
    while results > 100 and extracted_words < word_count:
        docs_by_word_query = queryset.set_options(mode="SPH_MATCH_EXTENDED2")
        results = docs_by_word_query.count()
        extracted_words += 5

    # Phase 3: intersect the results from phase 1 and 2.


def write_dups(source, dups):
    '''Writes duplicates to a file so they are logged.

    This function recieves a queryset and then writes out the values to a log.
    '''
    log = open('dup_log.txt', 'a')
    for dup in dups:
        # write out each doc
        log.write(str(source.pk) + '|' + str(dup.pk) + '\n')
    log.close()


def import_and_report_records():
    '''Traverses the first 1000 records and find their dups.

    This script is used to find dups within the database by comparing it to
    the sphinx index. This simulates the duplicate detection we will need to
    do when importing from other sources, and allows us to test it.
    '''
    # this may be very slow. Need to check the speed of this.
    count = MyModel.objects.count() - 1

    # do this 1000 times
    for _ in range(1000):
        id = randint(0, count)
        doc = Document.objects.get(pk = id)

        court = doc.court_id
        date = doc.dateFiled
        casename = doc.citation.caseNameFull
        content = doc.documentPlainText
        if content == "":
            # HTML content!
            content = doc.documentHTML
        dups = check_dup(court, date, casename, connect)

        if dups != None:
            # duplicate(s) were found, write them out to a log
            write_dups(doc, dups)

        # Clear query cache, as it presents a memory leak when in dev mode
        db.reset_queries()

    return 0

def main():
    print import_and_report_records()
    print "Completed 1000 records successfully. Exiting."
    exit(0)


if __name__ == '__main__':
    main()

