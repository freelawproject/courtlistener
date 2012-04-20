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
# append these to the path to make the dev machines and the server happy (respectively)
sys.path.append("/var/www/court-listener")

from django import db
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.template.defaultfilters import slugify
from django.utils.encoding import smart_str, smart_unicode
from alert.search.models import Court, Citation, Document
from alert.lib.parse_dates import parse_dates
from alert.tinyurl.encode_decode import num_to_ascii
from juriscraper.lib.string_utils import clean_string, harmonize, titlecase, trunc
from alert.lib.scrape_tools import hasDuplicate
from dup_finder import check_dup

from lxml.html import fromstring, tostring
from urlparse import urljoin
import datetime
import re
import subprocess
import time
import urllib2

# Set to False to disable automatic browser usage. Else, set to the
# command you want to run, e.g. 'firefox'
BROWSER = 'firefox-trunk'
SIMULATE = True


def write_dups(source, dups, DEBUG=False):
    '''Writes duplicates to a file so they are logged.

    This function recieves a queryset and then writes out the values to a log.
    '''
    log = open('../logs/dup_log.txt', 'a')
    if dups[0] != None:
        log.write(source)
        print "Logging match: " + source,
        for dup in dups:
            # write out each doc
            log.write('|' + str(dup['id']) + " - " + num_to_ascii(int(dup['id'])))
            if DEBUG:
                print '|' + str(dup['id']) + ' - ' + num_to_ascii(int(dup['id'])),
    else:
        log.write("%s" % source)
        if DEBUG:
            print "No dups found for %s" % source,
    print ""
    log.write('\n')
    log.close()


def scrape_and_parse():
    '''Traverses the dumps from resource.org, and puts them in the DB.

    Probably lots of ways to go about this, but I think the easiest will be the following:
     - look at the index page of all volumes, and follow all the links it has.
     - for each volume, look at its index page, and follow the link to all cases
     - for each case, collect information wisely.
     - put it all in the DB
    '''


    ##########################
    ### Duplicate checking ###
    ##########################
    if need_dup_check_for_date_and_court(caseDate, court):
        print "Running complex dup check."
        # There exist scraped cases in this court and date.
        # Strip HTML.
        entities = re.compile(r'&(([a-z]{1,5})|(#\d{1,4}));')
        content = entities.sub('', body)
        br = re.compile(r'<br/?>')
        content = br.sub(' ', content)
        p = re.compile(r'<.*?>')
        content = p.sub('', content)
        dups = check_dup(court.pk, caseDate, caseName, content, docketNumber, sha1Hash, DEBUG=True)
        if len(dups) == 0:
            # No dups found. Move on.
            pass
        elif len(dups) == 1:
            # Duplicate found.
            write_dups(sha1Hash, dups, DEBUG=True)
        elif len(dups) > 1:
            # Multiple dups found. Seek human review.
            write_dups(sha1Hash, dups, DEBUG=True)
    else:
        print "No complex check needed."



    #################################
    ### Document saving routines ####
    #################################
    if not SIMULATE:
        try:
            doc, created = Document.objects.get_or_create(documentSHA1=sha1Hash)
        except MultipleObjectsReturned:
            # this shouldn't happen now that we're using SHA1 as the dup
            # check, but the old data is problematic, so we must catch this.
            created = False

        if created:
            # we only do this if it's new
            doc.documentHTML = body
            doc.documentSHA1 = sha1Hash
            doc.download_URL = download_URL
            doc.dateFiled = caseDate
            doc.source = "R"
            doc.documentType = documentType

            # Make a citation
            cite = Citation(case_name=caseName,
                            docketNumber=docketNumber,
                            westCite=westCite)
            cite.save()
            doc.citation = cite
            doc.save()

        if not created:
            # This happens if we have a match on the sha1, which really
            # shouldn't happen, since F3 sha's come from the text, and ours
            # come from the binary.
            print "Duplicate found at volume " + str(i + 1) + \
                " and row " + str(j + 1) + "!!!!"
            print "Found document %s in the database with doc id of %d!" % (doc, doc.documentUUID)
            exit(1)


        # Clear query cache, as it presents a memory leak
        db.reset_queries()

    return 0
