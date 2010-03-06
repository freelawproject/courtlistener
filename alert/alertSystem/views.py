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

import urllib2, re
from BeautifulSoup import BeautifulSoup
from alert.alertSystem.models import *
from django.http import HttpResponse, Http404

 


def scrape(request, courtID):
    """
    a function that is given a court number to scrape, and which scrapes that
    page. It's going to get ugly, so bear with me. Scraping ain't always
    pretty.

    returns None
    """



    # First, we are going to scrape the appropriate page, then we are going to
    # hand that page off to the appropriate parsing code.
    try:
        courtID = int(courtID)
    except:
        raise Http404()
    
    if (courtID == 1):
        # first circuit
        url = "http://www.ca1.uscourts.gov/cgi-bin/newopn.pl"
    elif (courtID == 2):
        # second circuit
        url = "http://www.ca2.uscourts.gov/decisions"
    elif (courtID == 3):
        url = "http://michaeljaylissner.com"
    """

    ...etc for each

    """

    print "url = " + url

    html = urllib2.urlopen(url)
    soup = BeautifulSoup(html)
    #print soup

    # all links ending in pdf, case insensitive
    regex = re.compile("pdf$", re.IGNORECASE)
    pdfs = soup.findAll(attrs={"href": regex})

    #print pdfs

    for pdf in pdfs:
        linktext = str(pdf.contents[0])
        #print linktext

        linkURL = str(pdf.get("href"))

        # reassembles the URL, if a relative link is used
        if "http" not in linkURL:
            linkURL = url.split('/')[0] + "//" + url.split('/')[2] + linkURL

        print "downloading from " + linkURL + "..."

        webFile = urllib2.urlopen(linkURL)

        #uses the original filename. Will clobber existing file of the same name
        localFile = open(url.split('/')[-1], 'wb')
        localFile.write(webFile.read())

        #cleanup
        webFile.close()
        localFile.close()

    return HttpResponse("it worked")
