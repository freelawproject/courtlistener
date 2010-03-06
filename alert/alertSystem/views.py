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

import datetime, re, urllib2
from BeautifulSoup import BeautifulSoup
from alert.alertSystem.models import *
from django.http import HttpResponse, Http404

def downloadPDF(LinkToPdf, url):
    """Receive a URL as an argument, then download the PDF that's in it, and 
    place it intelligently into the database. Can accept either relative or
    absolute URLs
    
    returns None
    """ 
    
    # checks if it is a relative URL, and reassembles it, if necessary.
    if "http" not in LinkToPdf:
        LinkToPdf = url.split('/')[0] + "//" + url.split('/')[2] + LinkToPdf

    print "downloading from " + LinkToPdf + "..."

    webFile = urllib2.urlopen(LinkToPdf)

    #uses the original filename. Will clobber existing file of the same name
    localFile = open(url.split('/')[-1], 'wb')
    localFile.write(webFile.read())

    #cleanup
    webFile.close()
    localFile.close()



def makeSoupAndGetPDFs(url):
    """This function takes the URL, finds the PDFs in the HTML, and then hands
    those off to the downloadPDF function.
    
    returns None
    """
    
    html = urllib2.urlopen(url)
    soup = BeautifulSoup(html)
    #print soup

    # all links ending in pdf, case insensitive
    regex = re.compile("pdf$", re.IGNORECASE)
    pdfs = soup.findAll(attrs={"href": regex})

    #print pdfs

    for pdf in pdfs:
        linkText = str(pdf.contents[0])
        #print linktext

        linkToPdf = str(pdf.get("href"))
        
        downloadPDF(linkToPdf, url)



def scrape(request, courtID):
    """
    The master function. This will receive a court ID, determine the correct 
    action to take (scrape for PDFs, download content, etc.), then hand it off 
    to another function that will handle the nitty-gritty crud. 

    returns None
    """

    # some data validation, for good measure
    try:
        courtID = int(courtID)
    except:
        raise Http404()
    
    # next, we attack the court requested.
    if (courtID == 1):
        """
        first circuit doesn't actually do PDFs. They do links to HTML content.
        From what I can tell, this content is generated with pdftohtml. The 
        process for this court is therefore as follows:
        1. visit the site
        2. follow the links on the site
        3. download the html, parsing it for text. 
        """
        url = "http://www.ca1.uscourts.gov/cgi-bin/newopn.pl"
        scrapedTimeRetrieved = datetime.datetime.now()
        
        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)
        
        # find the <a> tags that link to PACER, since those have the case number
        aTags = soup.findAll('a', attrs={"href": "pacer"})
        
        # for each of them, follow the link, and place the text in our DB
        for a in aTags:
            scrapedCaseNumber = str(a.contents[0])
            
            
            

        excerptSummary = ExcerptSummary(
            autoExcerpt = ,
            courtSummary = ,
        )

        citation = Citation(
            caseNameShort = ,
            caseNameFull =  ,
            caseNumber = scrapedCaseNumber,
        )
            
        document = Document(
            documentSHA1 = ,
            dateFiled = ,
            court = ,
            judge = ,
            party = ,
            citation = , 
            excerptSummary = ,
            download_URL = ,
            time_retrieved = scrapedTimeRetrieved,
            local_path = ,
            documentPlainText = ,
            documentType = ,
            
        )    
        
    elif (courtID == 2):
        # second circuit
        url = "http://www.ca2.uscourts.gov/decisions"
    elif (courtID == 3):
        url = "http://michaeljaylissner.com"
    """

    ...etc for each

    """
    
    print "url = " + url


        
 

    return HttpResponse("it worked")
