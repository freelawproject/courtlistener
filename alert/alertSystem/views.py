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
from django.core.files.base import ContentFile
import datetime, hashlib, re, StringIO, urllib2
from BeautifulSoup import BeautifulSoup



def downloadPDF(LinkToPdf, caseNameShort):
    """Receive a URL and a casename as an argument, then downloads the PDF
    that's in it, and places it intelligently into the database. Can accept
    either relative or absolute URLs

    returns a StringIO that is the PDF, I think
    """


    webFile = urllib2.urlopen(LinkToPdf)

    stringThing = StringIO.StringIO()
    stringThing.write(webFile.read())

    myFile = ContentFile(stringThing.getvalue())

    webFile.close()
    return myFile




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

            # link the court early - it helps later
            doc.court = ct

            # next, we do caseNumber and caseNameShort
            cite.caseNumber = caseNumber
            cite.caseNameShort = caseNameShort

            try:
                """if this raises an exception, we haven't scraped this yet, so
                we should. Otherwise, we have scraped it, and we should break
                from the remainder of the loop. This works because the cases are
                in chronological order"""
                Citation.objects.get(caseNumber = caseNumber, caseNameShort = caseNameShort)
                print "duplicate found!"
                break
            except:
                # it's not a duplicate, move on to the saving stage
                pass

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

            # save the file to the db and hard drive
            myFile = downloadPDF(caseLink, caseNameShort)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

    elif (courtID == 4):
        """Fourth circuit everybody, fourth circuit! Off we go."""
        
        url = "http://pacer.ca4.uscourts.gov/opinions_today.htm"
        ct = Court.objects.get(courtUUID='ca4')

        html = urllib2.urlopen(url).read()
        
        # sadly, beautifulsoup chokes on the lines lines of this file because 
        # the HTML is so bad. Stop laughing - the HTML IS awful, but it's not
        # funny. Anyway, to make this thing work, we must pull out the target
        # attributes. And so we do.
        regex = re.compile("target.*>", re.IGNORECASE)
        html = re.sub(regex, ">", html)


        soup = BeautifulSoup(html)
        
        # all links ending in pdf, case insensitive
        regex = re.compile("pdf$", re.IGNORECASE)
        aTags = soup.findAll(attrs={"href": regex})
        
        i = 0
        regexII = re.compile('\d{2}/\d{2}/\d{4}')
        regexIII = re.compile('\d{4}(.*)')
        
        while i < len(aTags):
            # these will hold our final document and citation
            doc = Document()
            cite = Citation()

            # link the court early - it helps later
            doc.court = ct
            
            # next, we'll sort out the caseLink field, and save it
            caseLink = aTags[i].get('href')

            if "http:" not in caseLink:
                # in case it's a relative URL
                caseLink = url.split('/')[0] + "//" + url.split('/')[2] + "/" + caseLink
            
            doc.download_URL = caseLink

            # using caselink, we can get the caseNumber and documentType
            fileName = caseLink.split('/')[-1]
            caseNumber, documentType = fileName.split('.')[0:2]
            
            # next, we do the caseDate and caseNameShort, so we can quit before
            # we get too far along.
            junk = aTags[i].contents[0].strip().strip('&nbsp;')
            try:
                # this error seems to happen upon dups...not sure why yet
                caseDate = regexII.search(junk).group(0).strip()
                caseNameShort = regexIII.search(junk).group(1).strip()
            except:
                i += 1
                continue
            
            # some caseDate cleanup
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int(splitDate[2]),int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate
            
            doc.documentType = documentType
            cite.caseNumber = caseNumber
            cite.caseNameShort = caseNameShort
            
            # let's check for duplicates before we proceed
            try:
                """if this raises an exception, we haven't scraped this yet, so
                we should. Otherwise, we have scraped it, and we should move to 
                the next case"""
                Citation.objects.get(caseNumber = caseNumber, caseNameShort = caseNameShort)
                print "duplicate found!"
                i += 1
                continue
            except:
                # it's not a duplicate, move on to the saving stage
                pass
            
            # if that goes well, we can save.
            cite.save()
            doc.citation = cite
            
            # finally, we should download the PDF, and save it locally.
            myFile = downloadPDF(caseLink, caseNameShort)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1            
            

    """

    ...etc for each

    """


    return HttpResponse("it worked")
