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
sys.path.append("/var/www/court-listener-resource-org-scrape")

from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.utils.encoding import smart_str, smart_unicode
from alert.alertSystem.models import Court, Citation, Document
from alert.lib.string_utils import titlecase
from alert.lib.string_utils import trunc
from alert.lib.scrape_tools import hasDuplicate

from lxml.html import fromstring, tostring
from urlparse import urljoin
import datetime
import gc
import re
import subprocess
import time
import urllib2


def load_fix_files():
    '''Loads the fix files into memory so they can be accessed efficiently.'''
    court_fix_file = open('f2_court_fix_file.txt', 'r')
    date_fix_file  = open('f2_date_fix_file.txt', 'r')
    court_fix_dict = {}
    date_fix_dict = {}
    for line in court_fix_file:
        key, value = line.split('|')
        court_fix_dict[key] = value
    for line in date_fix_file:
        key, value = line.split('|')
        date_fix_dict[key] = value

    court_fix_file.close()
    date_fix_file.close()
    return court_fix_dict, date_fix_dict


def check_fix_list(sha1, fix_dict):
    ''' Given a sha1, return the correction for a case. Return false if no values.

    Corrections are strings that the parser can interpret as needed. Items are
    written to this file the first time the cases are imported, and this file
    can be used to import F2 into later systems.
    '''
    try:
        return fix_dict[sha1].strip()
    except KeyError:
        return False


def scrape_and_parse():
    '''Traverses the dumps from resource.org, and puts them in the DB.

    Probably lots of ways to go about this, but I think the easiest will be the following:
     - look at the index page of all volumes, and follow all the links it has.
     - for each volume, look at its index page, and follow the link to all cases
     - for each case, collect information wisely.
     - put it all in the DB
    '''

    # begin by loading up the fix files into memory
    court_fix_dict, date_fix_dict = load_fix_files()

    results = []
    DEBUG = 4
    # Set to False to disable automatic browser usage. Else, set to the
    # command you want to run, e.g. 'firefox'
    BROWSER = 'firefox'
    court_fix_file = open('f2_court_fix_file.txt', 'a')
    date_fix_file = open('f2_date_fix_file.txt', 'a')
    vol_file = open('vol_file.txt', 'r+')
    case_file = open('case_file.txt', 'r+')

    url = "file:///var/www/court-listener/Resource.org/F2/index.html"
    openedURL = urllib2.urlopen(url)
    content = openedURL.read()
    openedURL.close()
    tree = fromstring(content)

    volumeLinks = tree.xpath('//table/tbody/tr/td[1]/a')

    try:
        i = int(vol_file.readline())
    except ValueError:
        # the volume file is emtpy or otherwise failing.
        i = 0
    vol_file.close()

    if DEBUG >= 1:
        print "Number of remaining volumes is: %d" % (len(volumeLinks)-i)
    while i < len(volumeLinks):
        # we iterate over every case in the volume
        volumeURL = volumeLinks[i].text + "/index.html"
        volumeURL = urljoin(url, volumeURL)
        if DEBUG >= 1:
            print "Current volumeURL is: %s" % volumeURL

        openedVolumeURL = urllib2.urlopen(volumeURL)
        content = openedVolumeURL.read()
        volumeTree = fromstring(content)
        openedVolumeURL.close()
        caseLinks  = volumeTree.xpath('//table/tbody/tr/td[1]/a')
        caseDates  = volumeTree.xpath('//table/tbody/tr/td[2]')
        sha1Hashes = volumeTree.xpath('//table/tbody/tr/td[3]/a')

        # The following loads a serialized placeholder from disk.
        try:
            j = int(case_file.readline())
        except ValueError:
            j = 0
        case_file.close()
        while j < len(caseLinks):
            # iterate over each case, throwing it in the DB
            if DEBUG >= 1:
                print ''
            # like the scraper, we begin with the caseLink field (relative for
            # now, not absolute)
            caseLink = caseLinks[j].get('href')

            # sha1 is easy
            sha1Hash = sha1Hashes[j].text
            if DEBUG >= 4:
                print "SHA1 is: %s" % sha1Hash

            # using the caselink from above, and the volumeURL, we can get the
            # documentHTML
            absCaseLink = urljoin(volumeURL, caseLink)
            html = urllib2.urlopen(absCaseLink).read()
            htmlTree = fromstring(html)
            bodyContents = htmlTree.xpath('//body/*[not(@id="footer")]')
            body = ""
            for element in bodyContents:
                body = body + tostring(element)
            if DEBUG >= 5:
                print body

            # need to figure out the court ID
            try:
                courtPs = htmlTree.xpath('//p[@class = "court"]')
                court = ""
                for courtP in courtPs:
                    court += tostring(courtP).lower()
            except IndexError:
                court = check_fix_list(sha1Hash, court_fix_dict)
                if not court:
                    print absCaseLink
                    if BROWSER:
                        subprocess.Popen([BROWSER, absCaseLink], shell=False).communicate()
                    court = raw_input("Please input court name (e.g. \"First Circuit of Appeals\"): ").lower()
                    court_fix_file.write("%s|%s\n" % (sha1Hash, court))
            if ('first' in court) or ('ca1' == court):
                court = 'ca1'
            elif ('second' in court) or ('ca2' == court):
                court = 'ca2'
            elif ('third' in court) or ('ca3' == court):
                court = 'ca3'
            elif ('fourth' in court) or ('ca4' == court):
                court = 'ca4'
            elif ('fifth' in court) or ('ca5' == court):
                court = 'ca5'
            elif ('sixth' in court) or ('ca6' == court):
                court = 'ca6'
            elif ('seventh' in court) or ('ca7' == court):
                court = 'ca7'
            elif ('eighth' in court) or ('ca8' == court):
                court = 'ca8'
            elif ('ninth' in court) or ('ca9' == court):
                court = 'ca9'
            elif ("tenth" in court) or ('ca10' == court):
                court = 'ca10'
            elif ('columbia' in court) or ('cadc' == court):
                court = 'cadc'
            elif ('patent' in court) or ('ccpa' == court):
                court = 'ccpa'
            elif (('emergency' in court) and ('temporary' not in court)) or ('eca' == court):
                court = 'eca'
            elif ('claims' in court) or ('cfc' == court):
                court = 'cfc'
            else:
                # No luck extracting the court name. Try the fix file.
                court = check_fix_list(sha1Hash, court_fix_dict)
                if not court:
                    # Not yet in the fix file. Ask for input, then append it to
                    # the fix file.
                    print absCaseLink
                    if BROWSER:
                        subprocess.Popen([BROWSER, absCaseLink], shell=False).communicate()
                    court = raw_input("Unknown court. Input the court code to proceed successfully (e.g. 'ca1'): ")
                    court_fix_file.write("%s|%s\n" % (sha1Hash, court))

            court = Court.objects.get(courtUUID = court)
            if DEBUG >= 4:
                print "Court is: %s" % court

            # next: westCite, docketNumber and caseName. Full casename is gotten later.
            westCite = caseLinks[j].text
            docketNumber = absCaseLink.split('.')[-2]
            caseName = smart_str(titlecase(trunc(caseLinks[j].get('title'), 100).lower()))
            if DEBUG >= 4:
                print "caseName (trunc'ed): " + caseName

            # date is kinda tricky...details here:
            # http://pleac.sourceforge.net/pleac_python/datesandtimes.html
            rawDate = caseDates[j].find('a')
            try:
                if rawDate != None:
                    date_text = rawDate.text
                    try:
                        caseDate = datetime.datetime(*time.strptime(date_text, "%B, %Y")[0:5])
                    except ValueError, TypeError:
                        caseDate = datetime.datetime(*time.strptime(date_text, "%B %d, %Y")[0:5])
                else:
                    # No value was found. Throw an exception.
                    raise ValueError
            except:
                # No date provided.
                caseDate = check_fix_list(sha1Hash, date_fix_dict)
                if not caseDate:
                    print absCaseLink
                    if BROWSER:
                        subprocess.Popen([BROWSER, absCaseLink], shell=False).communicate()
                    rawDate = raw_input("Unknown date. Input the date to proceed in the format January 1, 2011: ")
                    if rawDate == 'None':
                        caseDate = None
                    else:
                        try:
                            caseDate = datetime.datetime(*time.strptime(rawDate, "%Y")[0:5])
                        except ValueError, TypeError:
                            caseDate = datetime.datetime(*time.strptime(rawDate, "%B %d, %Y")[0:5])
                        date_fix_file.write("%s|%s\n" % (sha1Hash, rawDate))


            if DEBUG >= 3:
                print "caseDate is: %s" % (caseDate)

            try:
                doc, created = Document.objects.get_or_create(
                    documentSHA1 = sha1Hash, court = court)
            except MultipleObjectsReturned:
                # this shouldn't happen now that we're using SHA1 as the dup
                # check, but the old data is problematic, so we must catch this.
                created = False

            if created:
                # we only do this if it's new
                doc.documentHTML = body
                doc.documentSHA1 = sha1Hash
                doc.download_URL = "http://bulk.resource.org/courts.gov/c/US/"\
                    + str(i+1) + "/" + caseLink
                doc.dateFiled = caseDate
                doc.documentType = "Published"
                doc.source = "R"

                cite, new = hasDuplicate(caseName, westCite, docketNumber)
                cite.caseNameFull = titlecase(caseLinks[j].get('title').lower())
                cite.save()

                doc.citation = cite
                doc.save()

            if not created:
                # something is afoot. Throw a big error.
                print "Duplicate found at volume " + str(i+1) + \
                    " and row " + str(j+1) + "!!!!"
                print "Found document %s in the database with doc id of %d!" % (doc, doc.documentUUID)
                j += 1
                exit(1)

            # save our location within the volume.
            j += 1
            case_file = open('case_file.txt', 'w')
            case_file.write(str(j))
            case_file.close()
            gc.collect()

        # save the last volume completed.
        i += 1
        vol_file = open('vol_file.txt', 'w')
        vol_file.write(str(i))
        vol_file.close()
        gc.collect()

    return 0

def main():
    print scrape_and_parse()
    print "Completed all volumes successfully. Exiting."
    exit(0)


if __name__ == '__main__':
    main()
