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


"""TODO: place these imports intelligently throughout the functions"""
from alert.alertSystem.models import *
from alert import settings
from alert.alertSystem.titlecase import titlecase
from django.http import HttpResponse, Http404
from django.core.files import File
from django.core.files.base import ContentFile
from django.shortcuts import render_to_response
from django.template import RequestContext
import datetime, hashlib, re, StringIO, subprocess, urllib, urllib2
from BeautifulSoup import BeautifulSoup
from lxml.html import fromstring
from lxml import etree

def downloadPDF(LinkToPdf):
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


def make_url_absolute(url, rel_url):
    """give it a URL and a URL you suspect to be a relative one. It'll strip the
    domain name out of the first URL, and, if needed, attach it to the suspected
    rel_url.

    returns an absolute version of rel_url
    """

    # for the relative URLs that don't start with a slash, we need this check
    startingSlash = re.compile('^(/)|(htt)')
    if not startingSlash.search(rel_url):
        rel_url = "/" + rel_url

    if 'http:' not in rel_url:
        #it's a relative url, fix it.
        rel_url = url.split('/')[0] + "//" + url.split('/')[2] + rel_url
    return rel_url


def hasDuplicate(caseNum, caseName):
    """takes a caseName and a caseNum, and checks if the object exists in the
    DB. If it doesn't, then it puts it in. If it does, it returns it.
    """
    
    caseName = caseName.replace('&nbsp;', ' ').strip()
    
    # check for duplicates, make the object in their absence
    cite, created = Citation.objects.get_or_create(
        caseNameShort = str(caseName), caseNumber = str(caseNum))
    return cite, created


def scrapeCourt(courtID, result):
    if (courtID == 1):
        """
        PDFs are available from the first circuit if you go to their RSS feed.
        So go to their RSS feed we shall.
        """
        url = "http://www.ca1.uscourts.gov/opinions/opinionrss.php"
        ct = Court.objects.get(courtUUID='ca1')

        req = urllib2.urlopen(url)
        
        # this code gets rid of errant ampersands - they throw big errors.
        contents = req.read()
        if '&' in contents:
            punctuationRegex = re.compile(" & ")
            contents = re.sub(punctuationRegex, " &amp; ", contents)        
            tree = etree.fromstring(contents)
        else:
            tree = etree.fromstring(contents)

        caseLinks = tree.xpath("//item/link")
        descriptions = tree.xpath("//item/description")
        docTypes = tree.xpath("//item/category")
        caseNamesAndNumbers = tree.xpath("//item/title")

        caseDateRegex = re.compile("(\d{2}/\d{2}/\d{4})",
            re.VERBOSE | re.DOTALL)
        caseNumberRegex = re.compile("(\d{2}-.*?\W)(.*)$")


        i = 0
        while i < len(caseLinks):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = caseLinks[i].text
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # next: docType
            docType = docTypes[i].text.strip()
            if "unpublished" in docType.lower():
                doc.documentType = "U"
            elif "published" in docType.lower():
                doc.documentType = "P"
            else:
                # it's an errata, or something else we don't care about
                i += 1
                continue

            # next: caseDate
            caseDate = caseDateRegex.search(descriptions[i].text).group(1)
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            # next: caseNumber
            caseNumber = caseNumberRegex.search(caseNamesAndNumbers[i].text)\
                .group(1)

            # next: caseNameShort
            caseNameShort = caseNumberRegex.search(caseNamesAndNumbers[i].text)\
                .group(2)

            # check for dups, make the object if necessary, otherwise, get it
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result

    elif (courtID == 2):
        """
        queries can be made on their system via HTTP POST.
        """

        # second circuit
        url = "http://www.ca2.uscourts.gov/decisions"
        ct = Court.objects.get(courtUUID='ca2')

        today = datetime.date.today()
        formattedToday = str(today.year) + str(today.month) + str(today.day)

        data = "IW_DATABASE=OPN&IW_FIELD_TEXT=*&IW_FILTER_DATE_AFTER=" +\
            formattedToday + "&IW_FILTER_DATE_BEFORE=&IW_BATCHSIZE=20&" +\
            "IW_SORT=-DATE"

        req = urllib2.Request(url, data)
        response = urllib2.urlopen(req)
        html = response.read()
        soup = BeautifulSoup(html)

        aTagsRegex = re.compile('(.*?.pdf).*?', re.IGNORECASE)
        aTags = soup.findAll(attrs={'href' : aTagsRegex})

        caseNumRegex = re.compile('.*/(.*?)_(.*?).pdf')

        i = 0
        while i < len(aTags):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = aTagsRegex.search(caseLink).group(1)
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

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
            caseName = aTags[i].parent.parent.nextSibling.nextSibling\
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
            cite, created = hasDuplicate(caseNum, caseName)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseName + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            doc.citation = cite

            # finalize everything
            doc.save()

            # next
            i += 1

        return result

    elif (courtID == 3):
        """
        This URL provides the latest 25 cases, so I need to pick out the new
        ones and only get those. I can do this efficiently by trying to do each,
        and then giving up once I hit one that I've done before. This will work
        because they are in reverse chronological order.
        """
        
        # if these URLs change, the docType identification (below) will need 
        # to be updated. It's lazy, but effective.
        urls = ("http://www.ca3.uscourts.gov/recentop/week/recprec.htm", 
            "http://www.ca3.uscourts.gov/recentop/week/recnon2day.htm",)
        ct = Court.objects.get(courtUUID='ca3')
        
        for url in urls:
            html = urllib2.urlopen(url)
            soup = BeautifulSoup(html)

            # all links ending in pdf, case insensitive
            regex = re.compile("pdf$", re.IGNORECASE)
            aTags = soup.findAll(attrs={"href": regex})

            # we will use these vars in our while loop, better not to compile them
            # each time
            regexII = re.compile('\d{2}/\d{2}/\d{2}')
            regexIII = re.compile('\d{2}-\d{4}')

            i = 0
            while i < len(aTags):
                # these will hold our final document and citation
                doc = Document()
                doc.court = ct

                # caseLink and caseNameShort
                caseLink = aTags[i].get('href')
                caseNameShort = aTags[i].contents[0]

                # caseDate and caseNumber
                junk = aTags[i].previous.previous.previous
                try:
                    # this error seems to happen upon dups...not sure why yet
                    caseDate = regexII.search(junk).group(0)
                    caseNumber = regexIII.search(junk).group(0)
                except:
                    i = i+1
                    continue

                # Make a decision about the docType.
                if "recprec.htm" in str(url):
                    doc.documentType = "P"
                elif "recnon2day.htm" in str(url):
                    doc.documentType = "U"

                # next, we check for a dup. If there is one, we can break from the
                # loop, since this court posts in alphabetical order.
                cite, created = hasDuplicate(caseNumber, caseNameShort)
                if not created:
                    result += "duplicate found at: " + str(i) + "<br>"
                    break

                doc.citation = cite

                # next up is the caseDate
                splitDate = caseDate.split('/')
                caseDate = datetime.date(int("20" + splitDate[2]),int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate

                # the download URL for the PDF
                caseLink = make_url_absolute(url, caseLink)

                doc.download_URL = caseLink

                # save the file to the db and hard drive
                myFile = downloadPDF(caseLink)
                doc.local_path.save(caseNameShort + ".pdf", myFile)

                # and using the PDF we just downloaded, we can generate our sha1 hash
                data = doc.local_path.read()
                sha1Hash = hashlib.sha1(data).hexdigest()
                doc.documentSHA1 = sha1Hash

                # finalize everything
                doc.save()

                i += 1

        return result

    elif (courtID == 4):
        """The fourth circuit is THE worst form of HTML I've ever seen. It's
        going to break a lot, but I've done my best to clean it up, and make it
        reliable."""

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
            doc.court = ct

            # next, we'll sort out the caseLink field, and save it
            caseLink = aTags[i].get('href')
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # using caselink, we can get the caseNumber and documentType
            fileName = caseLink.split('/')[-1]
            caseNumber, documentType = fileName.split('.')[0:2]
            # the caseNumber needs a hyphen inserted after the second digit
            caseNumber = caseNumber[0:2] + "-" + caseNumber[2:]

            # next, we do the caseDate and caseNameShort, so we can quit before
            # we get too far along.
            junk = aTags[i].contents[0].replace('&nbsp;', ' ').strip()
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


            # let's check for duplicates before we proceed
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, we can save.
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result


    elif (courtID == 5):
        """Fifth circuit scraper. Similar process as to elsewhere, as you might
        expect at this point"""

        url = "http://www.ca5.uscourts.gov/Opinions.aspx"
        ct = Court.objects.get(courtUUID='ca5')

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)


        #all links ending in pdf, case insensitive
        aTagRegex = re.compile("pdf$", re.IGNORECASE)
        aTags = soup.findAll(attrs={"href": aTagRegex})

        opinionRegex = re.compile(r"\opinions.*pub")
        unpubRegex = re.compile(r"\opinions\unpub")

        i = 0
        while i < len(aTags):
            # this page has PDFs that aren't cases, we must filter them out
            if opinionRegex.search(str(aTags[i])) == None:
                # it's not an opinion, increment and punt
                i += 1
                continue

            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # using caseLink, we can get the caseNumber and documentType
            caseNumber = aTags[i].contents[0]

            if unpubRegex.search(str(aTags[i])) == None:
                # it's published, else it's unpublished
                documentType = "P"
            else:
                documentType = "U"

            doc.documentType = documentType

            # next, we do the caseDate
            caseDate = aTags[i].next.next.contents[0].contents[0]

            # some caseDate cleanup
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int(splitDate[2]),int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            # next, we do the caseNameShort
            caseNameShort = aTags[i].next.next.next.next.next.contents[0]\
                .contents[0]

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, we save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()


            # next
            i += 1

        return result


    elif (courtID == 6):
        """Results are available without an HTML POST, but those results lack a
        date field. Hence, we must do an HTML POST."""

        url = "http://www.ca6.uscourts.gov/cgi-bin/opinions.pl"
        ct = Court.objects.get(courtUUID = 'ca6')

        today = datetime.date.today()
        formattedToday = str(today.month) + '/' + str(today.day) + '/' +\
            str(today.year)

        postValues = {
            'CASENUM' : '',
            'TITLE' : '',
            'FROMDATE' : formattedToday,
            'TODATE' : formattedToday,
            'OPINNUM' : ''
            }

        data = urllib.urlencode(postValues)
        req = urllib2.Request(url, data)
        response = urllib2.urlopen(req)
        html = response.read()

        soup = BeautifulSoup(html)

        aTagsRegex = re.compile('pdf$', re.IGNORECASE)
        aTags = soup.findAll(attrs={'href' : aTagsRegex})

        i = 0
        while i < len(aTags):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # using caseLink, we can get the caseNumber and documentType
            caseNumber = aTags[i].next.next.next.next.next.contents[0].strip()\
                .replace('&nbsp;','')
            
            # using the filename, we can determine the documentType...
            fileName = aTags[i].contents[0]
            if 'n' in fileName:
                # it's unpublished
                doc.documentType = "U"
            elif 'p' in fileName:
                doc.documentType = "P"

            # next, we can do the caseDate
            caseDate = aTags[i].next.next.next.next.next.next.next.next\
                .contents[0].replace('&nbsp;', ' ').strip()

            # some caseDate cleanup
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int(splitDate[0]),int(splitDate[1]),
                int(splitDate[2]))
            doc.dateFiled = caseDate

            # next, the caseNameShort (there's probably a better way to do this.
            caseNameShort = aTags[i].next.next.next.next.next.next.next.next\
                .next.next.next

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, we save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            # next
            i += 1

        return result


    elif (courtID == 7):
        """another court where we need to do a post. This will be a good
        starting place for getting the judge field, when we're ready for that"""

        url = "http://www.ca7.uscourts.gov/fdocs/docs.fwx"
        ct = Court.objects.get(courtUUID = 'ca7')

        data = "yr=&num=&Submit=Today&dtype=Opinion&scrid=Select+a+Case"
        req = urllib2.Request(url, data)
        response = urllib2.urlopen(req)
        html = response.read()

        soup = BeautifulSoup(html)

        aTagsRegex = re.compile('pdf$', re.IGNORECASE)
        aTags = soup.findAll(attrs={'href' : aTagsRegex})

        i = 0
        while i < len(aTags):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = aTags[i].get("href")
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # using caseLink, we can get the caseNumber and documentType
            caseNumber = aTags[i].previous.previous.previous.previous.previous\
                .previous.previous.previous.previous.previous.strip()

            # next up: caseDate
            caseDate = aTags[i].previous.previous.previous.contents[0].strip()
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            # next up: caseNameShort
            caseNameShort = aTags[i].previous.previous.previous.previous\
                .previous.previous.previous

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, we save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result


    elif (courtID == 8):
        url = "http://www.ca8.uscourts.gov/cgi-bin/new/today2.pl"
        ct = Court.objects.get(courtUUID = 'ca8')

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)

        aTagsRegex = re.compile('pdf$', re.IGNORECASE)
        aTags = soup.findAll(attrs={'href' : aTagsRegex})

        caseNumRegex = re.compile('(\d{2})(\d{4})(u|p)', re.IGNORECASE)
        caseDateRegex = re.compile('(\d{2}/\d{2}/\d{4})(.*)(</b>)')
        i = 0
        while i < len(aTags):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # using caseLink, we can get the caseNumber and documentType
            junk = aTags[i].contents[0]
            caseNumber = caseNumRegex.search(junk).group(1) + "-" +\
                caseNumRegex.search(junk).group(2)
            documentType = caseNumRegex.search(junk).group(3).upper()

            doc.documentType = documentType

            # caseDate is next on the block
            junk = str(aTags[i].next.next.next)
            caseDate = caseDateRegex.search(junk).group(1)\
                .replace('&nbsp;', ' ').strip()
            caseNameShort = caseDateRegex.search(junk).group(2)
                

            # some caseDate cleanup
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int(splitDate[2]),int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, we save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result


    elif (courtID == 9):
        """This court, by virtue of having a javascript laden website, was very
        hard to parse properly. BeautifulSoup couldn't handle it at all, so lxml
        has to be used. lxml seems pretty useful, but it was a pain to learn."""

        url = "http://www.ca9.uscourts.gov/opinions/?o_mode=view" +\
              "&amp;o_sort_field=24&amp;o_sort_field_by=19&amp;o_sort_type=" +\
              "asc&o_page_size=10"

        ct = Court.objects.get(courtUUID = 'ca9')

        req = urllib2.urlopen(url).read()
        tree = fromstring(req)

        caseLinks = tree.xpath('//table[3]/tbody/tr/td/a')
        caseNumbers = tree.xpath('//table[3]/tbody/tr/td[2]/label')
        caseDates = tree.xpath('//table[3]/tbody/tr/td[6]/label')

        i = 0
        while i < len(caseLinks):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = caseLinks[i].get('href')
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # next, we'll do the caseNumber
            caseNumber = caseNumbers[i].text

            # next up: document type (static for now)
            doc.documentType = "P"

            # next up: caseDate
            splitDate = caseDates[i].text.split('/')
            caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            #next up: caseNameShort
            caseNameShort = titlecase(caseLinks[i].text.lower())

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue


            # if that goes well, we save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result


    elif (courtID == 10):
        url = "http://www.ck10.uscourts.gov/opinions/new/daily_decisions.rss"
        ct = Court.objects.get(courtUUID = 'ca10')
        
        req = urllib2.urlopen(url)
        
        # this code gets rid of errant ampersands - they throw big errors.
        contents = req.read()
        if '&' in contents:
            punctuationRegex = re.compile(" & ")
            contents = re.sub(punctuationRegex, " &amp; ", contents)        
            tree = etree.fromstring(contents)
        else:
            tree = etree.fromstring(contents)

        caseLinks = tree.xpath("//item/link")
        descriptions = tree.xpath("//item/description")
        docTypes = tree.xpath("//item/category")
        caseNames = tree.xpath("//item/title")
        
        caseDateRegex = re.compile("(\d{2}/\d{2}/\d{4})",
            re.VERBOSE | re.DOTALL)
        caseNumberRegex = re.compile("(\d{2}-\d{4})(.*)$")

        i = 0
        while i < len(caseLinks):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = caseLinks[i].text
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # next: docType
            docType = docTypes[i].text.strip()
            if "unpublished" in docType.lower():
                doc.documentType = "U"
            elif "published" in docType.lower():
                doc.documentType = "P"
            else:
                # it's an errata, or something else we don't care about
                i += 1
                continue

            # next: caseDate
            caseDate = caseDateRegex.search(descriptions[i].text).group(1)
            splitDate = caseDate.split('/')
            caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            # next: caseNumber
            caseNumber = caseNumberRegex.search(descriptions[i].text)\
                .group(1)

            # next: caseNameShort
            caseNameShort = caseNames[i].text

            # check for dups, make the object if necessary, otherwise, get it
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result


    elif (courtID == 11):
        """Trying out an RSS feed this time, since the feed looks good."""
        url = "http://www.ca11.uscourts.gov/rss/pubopnsfeed.php"
        ct = Court.objects.get(courtUUID = 'ca11')

        req = urllib2.urlopen(url)
        
        # this code gets rid of errant ampersands - they throw big errors.
        contents = req.read()
        if '&' in contents:
            punctuationRegex = re.compile(" & ")
            contents = re.sub(punctuationRegex, " &amp; ", contents)        
            tree = etree.fromstring(contents)
        else:
            tree = etree.fromstring(contents)

        caseLinks = tree.xpath('//item/link')
        description = tree.xpath('//item/description')
        caseNames = tree.xpath('//item/title')

        # some regexes
        caseNumRegex = re.compile('''
            case            # the word case
            .*?             # some junk, not greedy
            (\d{2}-\d{5})   # two digits a hyphen then five more
            ''', re.IGNORECASE | re.VERBOSE)

        caseDateRegex = re.compile('''
            date                    # the word date
            .*?                     # some junk, not greedy
            (\d{2}-\d{2}-\d{4})     # two digits - two digits - four digits
            ''', re.IGNORECASE | re.VERBOSE)

        i = 0
        while i < len(caseLinks):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = caseLinks[i].text
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # these are only published opinions
            doc.documentType = "P"

            # next, we'll do the caseNumber
            caseNumber = caseNumRegex.search(description[i].text).group(1)

            # next up: caseDate
            caseDate = caseDateRegex.search(description[i].text).group(1)
            splitDate = caseDate.split('-')
            caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                int(splitDate[1]))
            doc.dateFiled = caseDate

            #next up: caseNameShort
            caseNameShort = caseNames[i].text

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, we save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result


    elif (courtID == 12):
        url = "http://www.cadc.uscourts.gov/bin/opinions/allopinions.asp"
        ct = Court.objects.get(courtUUID = 'cadc')

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)

        aTagsRegex = re.compile('pdf$', re.IGNORECASE)
        aTags = soup.findAll(attrs={'href' : aTagsRegex})

        caseNumRegex = re.compile("(\d{2}-\d{4})")


        i = 0
        while i < len(aTags):
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = make_url_absolute(url, caseLink)
            doc.download_URL = caseLink

            # using caseLink, we can get the caseNumber
            caseNumber =  caseNumRegex.search(caseLink).group(1)

            # we can hard-code this b/c the D.C. Court paywalls all
            # unpublished opinions.
            doc.documentType = "P"

            # caseDate is next on the block
            caseDate = datetime.date.today()
            doc.dateFiled = caseDate

            caseNameShort = aTags[i].next.next.next

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                i += 1
                continue

            # if that goes well, we save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result


    elif (courtID == 13):
        url = "http://www.cafc.uscourts.gov/dailylog.html"
        ct = Court.objects.get(courtUUID = "cafc")

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)

        aTagsRegex = re.compile('pdf$', re.IGNORECASE)
        trTags = soup.findAll('tr')
        
        # start on the first row, since the first is headers.
        i = 1
        # stop after 20, because it gets out of control otherwise.
        while i <= 20:
            # these will hold our final document and citation
            doc = Document()
            doc.court = ct

            try:
                caseLink = trTags[i].td.nextSibling.nextSibling.nextSibling\
                    .nextSibling.nextSibling.nextSibling.a.get('href').strip('.')
                caseLink = make_url_absolute(url, caseLink)
                if 'opinion' not in caseLink:
                    # we have a non-case PDF. punt
                    i += 1
                    continue
            except:
                # the above fails when things get funky, in that case, we punt
                i += 1
                continue

            doc.download_URL = caseLink

            # next: caseNumber
            caseNumber = trTags[i].td.nextSibling.nextSibling.contents[0]\
                .strip('.pdf')

            # next: dateFiled
            dateFiled = trTags[i].td.contents
            splitDate = dateFiled[0].split("/")
            dateFiled = datetime.date(int(splitDate[0]), int(splitDate[1]),
                int(splitDate[2]))
            doc.dateFiled = dateFiled

            # next: caseNameShort
            caseNameShort = trTags[i].td.nextSibling.nextSibling.nextSibling\
                .nextSibling.nextSibling.nextSibling.a.contents[0]

            # next: documentType
            documentType = trTags[i].td.nextSibling.nextSibling.nextSibling\
                .nextSibling.nextSibling.nextSibling.nextSibling.nextSibling\
                .contents[0].contents[0]
            doc.documentType = documentType

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)
            if not created:
                result += "duplicate found at: " + str(i) + "<br>"
                break

            # if that goes well, we save to the DB
            doc.citation = cite

            # finally, we should download the PDF and save it locally.
            myFile = downloadPDF(caseLink)
            doc.local_path.save(caseNameShort + ".pdf", myFile)

            # and using the PDF we just downloaded, we can generate our sha1 hash
            data = doc.local_path.read()
            sha1Hash = hashlib.sha1(data).hexdigest()
            doc.documentSHA1 = sha1Hash

            # finalize everything
            doc.save()

            i += 1

        return result
    


def getPDFContent(path):
    """Get the contents of a PDF file, and put them in a variable"""

    process = subprocess.Popen(
        ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"], shell=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    content, err = process.communicate()
    return content, err



def parseCourt(courtID, result):
    """Here, we do the following:
        1. For a given court, find all of its documents
        2. Determine if the document has been parsed already
        3. If it has, punt, if not, open the PDF and parse it.

    returns a string containing the result"""

    # a tuple for converting our courtID to a courtUUID...bad code.
    courts = ('ca1','ca2','ca3','ca4','ca5','ca6','ca7','ca8','ca9','ca10',
        'ca11','cadc','cafc')

    # select all documents from this jurisdiction that lack plainText (this
    # achieves duplicate checking.
    selectedDocuments = Document.objects.filter(documentPlainText = "",
        court__courtUUID = courts[courtID-1])


    for doc in selectedDocuments:
        # for each of these documents, open it, parse it.
        result.append("Parsed: " + doc.citation.caseNameShort)

        relURL = str(doc.local_path)
        relURL = settings.MEDIA_ROOT + relURL
        doc.documentPlainText = getPDFContent(relURL)[0]
        doc.save()

    return result



def scrape(request, courtID):
    """
    The master function. This will receive a court ID, determine the correct
    action to take, then hand it off to another function that will handle the
    nitty-gritty crud.

    If the courtID is 0, then we scrape all courts, one after the next.

    returns HttpResponse containing the result
    """


    # we show this string to users if things go smoothly
    result = "It worked<br>"
    scrapeResult = ""

    # some data validation, for good measure - this should already be done via
    # our url regex
    try:
        courtID = int(courtID)
    except:
        raise Http404()

    # next, we attack the court requested.
    if (courtID == 0):
        # we do ALL of the courts (useful for testing)
        i = 1
        while i <= 13:
            result += "NOW SCRAPING COURT: " + str(i) + "<br>"
            result = scrapeCourt(i, result) + "<br><br>"
            i += 1

    else:
        result = scrapeCourt(courtID, result)

    if not settings.DEBUG:
        # if debug is not set to True, we don't display useful messages.
        result = "Done."

    return HttpResponse(result)


def parse(request, courtID):
    """Open a PDF, pull out the contents, parse them, and put them in intresting
    places in the DB

    returns HttpResponse of the result"""

    result = ["It worked"]

    # some data validation, for good measure - this should already be done via
    # our url regex
    try:
        courtID = int(courtID)
    except:
        raise Http404()

    if courtID == 0:
        # we parse the documents from all jurisdictions
        i = 1
        while i <= 13:
            result.append("NOW PARSING COURT: " + str(i))
            result = (parseCourt(i, result))
            i += 1

    else:
        result = (parseCourt(courtID, result))

    if not settings.DEBUG:
        # if debug is not set to True, we don't display useful stuff.
        result = ["Done."]

    return render_to_response('parse.html', {'result': result}, RequestContext(request))

def viewCases(request, court, case):
    """Take a court and a caseNameShort, and display what we know about that
    case.
    """


    # get the court and citation information
    ct = Court.objects.get(courtUUID = court)

    # try looking it up by casename. Failing that, try the caseNumber.
    try:
        cites = Citation.objects.filter(caseNameShort = case)
        if len(cites) == 0:
            # if we can't find it by case name, try by case number
            cites = Citation.objects.filter(caseNumber = case)
    except:
        # this is caught in the template, so no worries.
        pass


    docs = []
    if len(cites) > 0:
        # get any documents with that citation at that court. If there is more
        # than one citation, we only need the first, so we slice to that one.
        for cite in cites:
            docs.append(Document.objects.get(court = ct, citation = cite))

        return render_to_response('display_cases.html', {'title': case,
            'docs': docs, 'court': ct}, RequestContext(request))

    else:
        # we have no hits, punt
        return render_to_response('display_cases.html', {'title': case,
            'court': ct}, RequestContext(request))

def viewDocumentListByCourt(request, court):
    """Show documents for a court, ten at a time"""
    from django.core.paginator import Paginator, InvalidPage, EmptyPage
    if court == "all":
        # we get all records, sorted by dateFiled.
        docs = Document.objects.order_by("-dateFiled")
        ct = "All courts"
    else:
        ct = Court.objects.get(courtUUID = court)
        docs = Document.objects.filter(court = ct).order_by("-dateFiled")

    # we will show ten docs/page
    paginator = Paginator(docs, 10)
    
    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
    
    # If page request is out of range, deliver last page of results.
    try:
        documents = paginator.page(page)
    except (EmptyPage, InvalidPage):
        documents = paginator.page(paginator.num_pages)

    return render_to_response('view_documents_by_court.html', {'title': ct,
        "documents": documents}, RequestContext(request))
