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
sys.path.append("/home/mlissner/Documents/Cal/FinalProject")
sys.path.append("/home/mlissner/FinalProject") 

# get our settings
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.utils.encoding import smart_str, smart_unicode
from alert.alertSystem.models import Court, Citation, Document, Party
from alert.alertSystem.titlecase import titlecase

from lxml.html import fromstring, tostring
from urlparse import urljoin
import datetime, time, re, urllib2

def trunc(s, length):
    """finds the rightmost space in a string, and truncates there. Lacking such
    a space, truncates at length"""

    if len(s) <= length:
        return s
    else:
        # find the rightmost space
        end = s.rfind(' ', 0 , length)
        if end == -1:
            # no spaces found, just use max position
            end = length
        return s[0:end]


def scrape_and_parse():
    """Probably lots of ways to go about this, but I think the easiest will be the following:
     - look at the index page of all volumes, and follow all the links it has.
     - for each volume, look at its index page, and follow the link to all cases
     - for each case, collect information wisely.
     - put it all in the DB
     - rock the casbah.
    """
    results = []
    DEBUG = 1
    url = "file:///home/mlissner/FinalProject/Resource.org/US/index.html"
    
    ct = Court.objects.get(courtUUID = 'scotus')
    
    req = urllib2.urlopen(url).read()
    tree = fromstring(req)

    volumeLinks = tree.xpath('//table/tbody/tr/td[1]/a')
    
    i = 95
    if DEBUG == 1: print len(volumeLinks)-i
    while i < (len(volumeLinks)):
        # we iterate over every case in the volume
        volumeURL = volumeLinks[i].text + "/index.html"
        volumeURL = urljoin(url, volumeURL)
        if DEBUG == 1: print "volumeURL: " + volumeURL
        
        req = urllib2.urlopen(volumeURL).read()
        volumeTree = fromstring(req)
        caseLinks = volumeTree.xpath('//table/tbody/tr/td[1]/a')
        caseDates = volumeTree.xpath('//table/tbody/tr/td[2]/a')
        sha1Hashes = volumeTree.xpath('//table/tbody/tr/td[3]/a')

        j = 0
        while j < len(caseLinks):
            # iterate over each case, throwing it in the DB
            
            # like the scraper, we begin with the caseLink field (relative for 
            # now, not absolute)
            caseLink = caseLinks[j].get('href')
            
            # sha1 is easy
            sha1Hash = sha1Hashes[j].text
            if DEBUG == 5: print sha1Hash
            
            try:
                doc, created = Document.objects.get_or_create(
                    documentSHA1 = sha1Hash, court = ct)
            except MultipleObjectsReturned:
                # this shouldn't happen now that we're using SHA1 as the dup
                # check, but the old data is problematic, so we must catch this.
                created = False
            
            if created:
                # we only do this if it's new
                doc.documentSHA1 = sha1Hash
                doc.download_URL = "http://bulk.resource.org/courts.gov/c/US/"\
                    + str(i+1) + "/" + caseLink
                doc.court = ct
                        
            if not created:
                # something is afoot. Throw a big error.
                results.append("Duplicate found at volume " + str(i+1) + \
                    " and row " + str(j+1) + "!!!!")
                j += 1
                continue
                        
            # using the caselink from above, and the volumeURL, we can get the
            # documentHTML
            absCaseLink = urljoin(volumeURL, caseLink) 
            html = urllib2.urlopen(absCaseLink).read()
            htmlTree = fromstring(html)
            bodyContents = htmlTree.xpath('//body/*[not(@id="footer")]')
            body = ""
            for element in bodyContents:
                body = body + tostring(element)
            if DEBUG == 5: print body
            doc.documentHTML = body
            
            
            # next: caseNum and caseName (short and full)
            caseNum = caseLinks[j].text
            caseName = smart_str(titlecase(trunc(caseLinks[j].get('title'), 100).lower()))
            if DEBUG == 5: print "caseName (trunc'ed): " + caseName
            
            cite, created = Citation.objects.get_or_create(
                caseNameShort = str(caseName), caseNumber = str(caseNum))
            cite.caseNameFull = titlecase(caseLinks[j].get('title').lower())
            cite.save()
            doc.citation = cite
            
            # date is kinda tricky...details here:
            # http://pleac.sourceforge.net/pleac_python/datesandtimes.html
            if DEBUG == 5: print rawDate
            try:
                rawDate = caseDates[j].text
                caseDate = datetime.datetime(*time.strptime(rawDate, "%B, %Y")[0:5])
                doc.dateFiled = caseDate
            except ValueError, TypeError:
                rawDate = caseDates[j].text
                caseDate = datetime.datetime(*time.strptime(rawDate, "%B %d, %Y")[0:5])
                doc.dateFiled = caseDate
            except IndexError:
                # date is missing, we must move on.
                results.append("date index error at volume " + str(i+1) + \
                    " and row " + str(j+1) + "!!!!")
                pass
            except:
                # something is afoot. Throw another big error.
                results.append("Date parsing error at volume " + str(i+1) + \
                    " and row " + str(j+1) + "!!!!")
                pass
            
            # an easy field
            doc.documentType = "P"
            
            # and another easy one
            doc.source = "R"
            
            doc.save()
            
            j += 1
        i += 1
        
    return results

def main():
    print scrape_and_parse()

    return 0


if __name__ == '__main__':
    main()
