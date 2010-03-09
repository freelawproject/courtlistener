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

from alert.alertSystem.models import *
from django.http import HttpResponse, Http404
from django.core.files import File
import datetime, hashlib, re, StringIO, urllib2
from BeautifulSoup import BeautifulSoup



def downloadPDF(LinkToPdf):
    """Receive a URL as an argument, then download the PDF that's in it, and
    place it intelligently into the database. Can accept either relative or
    absolute URLs

    returns None
    """


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

    # some data validation, for good measure - this should already be done via our url regex
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

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)

        tdTags = soup.findAll('td')

        ct = Court.objects.get(courtUUID='ca1')

        i = 0
        while i < len(tdTags)-4:
            # some beautiful soup work here...
            caseDate = tdTags[i+1].contents[0].strip().strip('&nbsp;')
            caseLink = tdTags[i+2].contents[0].get('href')
            caseNumber = tdTags[i+3].contents[1].contents[0].strip().strip('&nbsp;')
            caseNameShort = tdTags[i+4].contents[0].strip().strip('&nbsp;')

            # increment our while loop counter, i, by the number of columns in the table
            i = i + 4

            doc = Document()

            # great, now we do some parsing and building, beginning with the caseLink
            if "http:" not in caseLink:
                caseLink = url.split('/')[0] + "//" + url.split('/')[2] + caseLink

            doc.download_URL = caseLink

            # using caseLink, we can download the cases
            fileHandle = urllib2.urlopen(caseLink)
            html = fileHandle.read()
            doc.documentPlainText = html
            fileHandle.close()

            # and using the case text, we can generate our sha1 hash
            sha1Hash = hashlib.sha1(html).hexdigest()
            doc.documentSHA1 = sha1Hash


            # next up is the caseDate
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int(splitDate[2]),int(splitDate[0]),int(splitDate[1]))
            doc.dateFiled = caseDate


            # next, we do caseNumber and caseNameShort
            cite = Citation()
            cite.caseNumber = caseNumber
            cite.caseNameShort = caseNameShort

            try:
                # if this raises an exception, we haven't scraped this yet, so we should.
                # Otherwise, we have scraped it, and we should continue.
                Citation.objects.get(caseNumber = caseNumber, caseNameShort = caseNameShort)
                #print "duplicate found!"
                continue
            except:
                # it's not a duplicate, move on to the saving stage
                pass

            # and finally, we link up the foreign keys and save the data
            doc.court = ct
            cite.save()
            doc.citation = cite
            doc.save()



    elif (courtID == 2):
        # second circuit
        url = "http://www.ca2.uscourts.gov/decisions"
        ct = Court.objects.get(courtUUID='ca2')

        """
        queries can be made on their system via HTTP POST, but I can't figure out
        how to URL hack it. I've made a request for help (2010-03-06)
        http://www.ca2.uscourts.gov/decisions?IW_DATABASE=OPN&IW_FIELD_TEXT=OPN&IW_SORT=-Date&IW_BATCHSIZE=25
        """

    elif (courtID == 3):
        """
        This URL provides the latest 25 cases, so I need to pick out the new
        ones and only get those. I can do this efficiently by trying to do each,
        and then giving up once I hit one that I've done before. This will work
        because they are in reverse chronological order.
        """

        url = "http://www.ca3.uscourts.gov/recentop/week/recprec.htm"
        ct = Court.objects.get(courtUUID='ca3')

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)


        # all links ending in pdf, case insensitive
        regex = re.compile("pdf$", re.IGNORECASE)
        aTags = soup.findAll(attrs={"href": regex})

        # we will use these vars in our while loop, better not to compile them each time
        regexII = re.compile('\d{2}/\d{2}/\d{2}')
        regexIII = re.compile('\d{2}-\d{4}')
        i = 0

        while i < len(aTags):
            caseLink = aTags[i].get('href')
            print caseLink
            caseNameShort = aTags[i].contents[0].strip().strip('&npsp;')

            junk = aTags[i].previous.previous.previous

            try:
                # this error seems to happen upon dups...not sure why yet
                caseDate = regexII.search(junk).group(0)
                caseNumber = regexIII.search(junk).group(0)
            except:
                i = i+1
                continue

            # these will hold our final document and citation
            doc = Document()
            cite = Citation()

            # next, we do caseNumber and caseNameShort
            cite.caseNumber = caseNumber
            cite.caseNameShort = caseNameShort

#            try:
#                """if this raises an exception, we haven't scraped this yet, so
#                we should. Otherwise, we have scraped it, and we should break
#                from the remainder of the loop. This works because the cases are
#                in chronological order"""
#                Citation.objects.get(caseNumber = caseNumber, caseNameShort = caseNameShort)
#                print "duplicate found!"
#                break
#            except:
#                # it's not a duplicate, move on to the saving stage
#                pass

            cite.save()
            doc.citation = cite

            # next up is the caseDate
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int("20" + splitDate[2]),int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            # the download URL for the PDF
            if "http:" not in caseLink:
                # in case it's a relative URL
                caseLink = url.split('/')[0] + "//" + url.split('/')[2] + caseLink

            doc.download_URL = caseLink

            """PROBLEM: SHA1 is FAKED!!!!"""
            # and using the case text, we can generate our sha1 hash
            sha1Hash = hashlib.sha1("webFile" + str(i)).hexdigest()
            doc.documentSHA1 = sha1Hash
            
            # link the foreign keys, save and iterate
            doc.court = ct
            
            # next, we download, save, delete and do a bunch of other stuff.            
            webFile = urllib2.urlopen(caseLink)
            webFile.name = "blarg2"
            localFile = open("/tmp/pdf.pdf", 'wb')
            localFile.write(webFile.read())
            #localFile.name = "blarg3"
            localFile.close()
            localFile = open("/tmp/pdf.pdf", 'r')
            myFile = File(localFile)
            myFile.name = "blarg"
            doc.local_path.save(caseNameShort + "pdf", myFile)
            
            
            
            """PROBLEM: THE STUFF BELOW IS LIKELY CRUD THAT NEEDS CLEANING"""
            #Chart.objects.create(xml=default_storage.save(f.name, myfile)) 
            
            # using caseLink, we can download the case

            #localFile = open(caseNameShort, 'wb')
            #localFile.write(webFile.read())

            #webFile.close()
            
            
            #pdf = File(localFile)
            #doc.local_path = File(open("/tmp/test.txt")) # this works!





            """PROBLEM: NOT SURE IF THIS IS NECESSARY!"""
            doc.save()

            i = i+1





    """

    ...etc for each

    """


    return HttpResponse("it worked")
