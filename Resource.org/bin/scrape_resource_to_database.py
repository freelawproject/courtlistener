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
from alert.alertSystem.models import Court

from lxml.html import fromstring
import urllib2
from urlparse import urljoin

def scrape_and_parse():
    """Probably lots of ways to go about this, but I think the easiest will be the following:
     - look at the index page of all volumes, and follow all the links it has.
     - for each volume, look at its index page, and follow the link to all cases
     - for each case, collect information wisely.
     - put it all in the DB
     - rock the casbah.
    """
    url = "file:///home/mlissner/Documents/Cal/FinalProject/Resource.org/US/index.html"
    
    ct = Court.objects.get(courtUUID = 'scotus')
    
    req = urllib2.urlopen(url).read()
    tree = fromstring(req)

    volumeLinks = tree.xpath('//table/tbody/tr/td[1]/a')
    
    i = 0
    while i < len(volumeLinks):
        # we iterate over every case in the volume
        
        volumeURL = volumeLinks[i].text + "/index.html"
        volumeURL = urljoin(url, volumeURL)
        
        req = urllib2.urlopen(volumeURL).read()
        volumeTree = fromstring(req)
        caseLinks = volumeTree.xpath('//table/tbody/tr/td[1]/a')
        
        j = 0
        while j < len(caseLinks):
            # iterate over each case, throwing it in the DB
            
            # like the scraper, we begin with the caseLink field
            caseLink = caseLink[j].get('href')
            
            print caseLink
            j += 1
            
            """
            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = aTagsRegex.search(caseLink).group(1)
            caseLink = urljoin(url, caseLink)

            myFile, doc, created = makeDocFromURL(caseLink, ct)

            if not created:
                # it's an oldie, punt!
                result += "Duplicate found at " + str(i) + "\n"
                dupCount += 1
                if dupCount == 3:
                    # third dup in a a row. BREAK!
                    break
                i += 1
                continue
            else:
                dupCount = 0

            # using caseLink, we can get the caseNumber and documentType
            caseNum = caseNumRegex.search(caseLink).group(1)

            # and the docType
            documentType = caseNumRegex.search(caseLink).group(2)
            if 'opn' in documentType:
                # it's unpublished
                doc.documentType = "P"
            elif 'so' in documentType:
                doc.documentType = "U"

            # next, the caseNameShort (there's probably a better way to do this.
            caseNameShort = aTags[i].parent.parent.nextSibling.nextSibling\
                .nextSibling.nextSibling.contents[0]

            # next, we can do the caseDate
            caseDate = aTags[i].parent.parent.nextSibling.nextSibling\
                .nextSibling.nextSibling.nextSibling.nextSibling.contents[0]\
                .replace('&nbsp;', ' ').strip()

            # some caseDate cleanup
            splitDate = caseDate.split('-')
            caseDate = datetime.date(int(splitDate[2]),int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            # check for duplicates, make the object in their absence
            cite, created = hasDuplicate(caseNum, caseNameShort)

            # last, save evrything (pdf, citation and document)
            doc.citation = cite
            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
            doc.save()

            i += 1"""
            
            pass
        
        i += 1

def main():
    print scrape_and_parse()

    return 0


if __name__ == '__main__':
    main()
