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

#TODO: Use of the time.strptime function would improve this code here and there.
#   info here: http://docs.python.org/library/time.html#time.strptime
import settings
from django.core.management import setup_environ
setup_environ(settings)

from alertSystem.models import *
from alertSystem.titlecase import titlecase

from django.core.exceptions import MultipleObjectsReturned
from django.core.files import File
from django.core.files.base import ContentFile
from django.utils.encoding import smart_str

import datetime, calendar, hashlib, re, StringIO, subprocess, time, urllib, urllib2
from BeautifulSoup import BeautifulSoup
from lxml.html import fromstring, tostring
from lxml import etree
from optparse import OptionParser
from urlparse import urljoin


def makeDocFromURL(LinkToPdf, ct):
    """Receives a URL and a court as arguments, then downloads the PDF
    that's in it, and makes it into a StringIO. Generates a sha1 hash of the
    file, and tries to add it to the db. If it's a duplicate, it gets the one in
    the DB. If it's a new sha1, it creates a new document.

    returns a StringIO of the PDF, a Document object, and a
        boolean indicating whether the Document was created
    """

    # get the PDF
    try:
        webFile = urllib2.urlopen(LinkToPdf)
        stringThing = StringIO.StringIO()
        stringThing.write(webFile.read())
        myFile = ContentFile(stringThing.getvalue())
        webFile.close()
    except:
        print "ERROR DOWNLOADING FILE!: " + str(LinkToPdf)
        error = True
        return "Bad", "Bad", "Bad", error

    # make the SHA1
    data = myFile.read()
    sha1Hash = hashlib.sha1(data).hexdigest()

    # using that, we check for a dup

    doc, created = Document.objects.get_or_create(documentSHA1 = sha1Hash,
        court = ct)

    if created:
        # we only do this if it's new
        doc.documentSHA1 = sha1Hash
        doc.download_URL = LinkToPdf
        doc.court = ct
        doc.source = "C"

    error = False

    return myFile, doc, created, error


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


def hasDuplicate(caseNum, caseName):
    """takes a caseName and a caseNum, and checks if the object exists in the
    DB. If it doesn't, then it puts it in. If it does, it returns it.
    """
    
    # data cleanup: Removes white space and a bunch of stray characters
    caseName = smart_str(caseName.replace('&rsquo;', '\'').replace('&rdquo;', "\"")\
        .replace('&ldquo;',"\"").replace('&nbsp;', ' ').replace('%20', ' ')\
        .strip().strip(';'))
    caseNum = caseNum.replace('&rsquo;', '\'').replace('&rdquo;', "\"")\
        .replace('&ldquo;',"\"").replace('&nbsp;', ' ').replace('%20', ' ')\
        .strip().strip(';')
    caseName = " ".join(caseName.split())
    caseNum = " ".join(caseNum.split())

    caseNameShort = trunc(caseName, 100)

    # check for duplicates, make the object in their absence
    cite, created = Citation.objects.get_or_create(
        caseNameShort = str(caseNameShort), caseNumber = str(caseNum))

    if caseNameShort == caseName:
        # no truncation.
        cite.caseNameFull = caseNameShort
    else:
        # truncation happened. Therefore, use the untruncated value as the full
        # name.
        cite.caseNameFull = caseName
    cite.save()

    return cite, created


def getPDFContent(path):
    """Get the contents of a PDF file, and put them in a variable"""

    process = subprocess.Popen(
        ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"], shell=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    content, err = process.communicate()
    return content, err


def scrapeCourt(courtID, result, verbose):
    if (courtID == 1):
        """
        PDFs are available from the first circuit if you go to their RSS feed.
        So go to their RSS feed we shall.

        This is the second version of this court. Good times.
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
        dupCount = 0
        while i < len(caseLinks):
            # First: docType, since we don't support them all...
            docType = docTypes[i].text.strip()
            if "unpublished" in docType.lower():
                documentType = "U"
            elif "published" in docType.lower():
                documentType = "P"
            elif "errata" in docType.lower():
                documentType = "E"
            else:
                # something weird we don't know about, punt
                i += 1
                continue

            # next, we begin with the caseLink field
            caseLink = caseLinks[i].text
            caseLink = urljoin(url, caseLink)

            # then we download the PDF, make the hash and document
            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

            if error:
                # things broke, punt this iteration
                i += 1
                continue

            if not created:
                # it's an oldie, punt!
                if verbose >= 1:
                    result += "Duplicate found at " + str(i) + "\n"
                dupCount += 1
                if dupCount == 3:
                    # third dup in a a row. BREAK!
                    break
                i += 1
                continue
            else:
                dupCount = 0

            # otherwise, we continue
            doc.documentType = documentType

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

            # last, save evrything (pdf, citation and document)
            doc.citation = cite
            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
            doc.save()

            i += 1

        return result

    elif (courtID == 2):
        """
        URL hacking FTW.
        """

        # second circuit
        urls = (
            "http://www.ca2.uscourts.gov/decisions?IW_DATABASE=OPN&IW_FIELD_TEXT=SUM&IW_SORT=-Date&IW_BATCHSIZE=100",
            "http://www.ca2.uscourts.gov/decisions?IW_DATABASE=SUM&IW_FIELD_TEXT=SUM&IW_SORT=-Date&IW_BATCHSIZE=100",
        ) 
        
        ct = Court.objects.get(courtUUID='ca2')
        
        for url in urls:
            html = urllib2.urlopen(url)
            soup = BeautifulSoup(html)

            aTagsRegex = re.compile('(.*?.pdf).*?', re.IGNORECASE)
            aTags = soup.findAll(attrs={'href' : aTagsRegex})

            caseNumRegex = re.compile('.*/(\d{1,2}-\d{3,4})(.*).pdf')

            i = 0
            dupCount = 0
            while i < len(aTags):
                # we begin with the caseLink field
                caseLink = aTags[i].get('href')
                caseLink = aTagsRegex.search(caseLink).group(1)
                caseLink = urljoin(url, caseLink)
                if verbose >= 2:
                    print str(i) + ": " + caseLink
                
                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    if verbose >= 1:
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
                if verbose >= 2:
                    print "caseNum: " + str(caseNum)

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
            dupCount = 0
            while i < len(aTags):
                # caseLink and caseNameShort
                caseLink = aTags[i].get('href')

                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    if verbose >= 1:
                        result += "Duplicate found at " + str(i) + "\n"
                    dupCount += 1
                    if dupCount == 3:
                        # third dup in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

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

                # next up is the caseDate
                splitDate = caseDate.split('/')
                caseDate = datetime.date(int("20" + splitDate[2]),int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate

                # Make a decision about the docType.
                if "recprec.htm" in str(url):
                    doc.documentType = "P"
                elif "recnon2day.htm" in str(url):
                    doc.documentType = "U"

                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
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
        dupCount = 0
        regexII = re.compile('\d{2}/\d{2}/\d{4}')
        regexIII = re.compile('\d{4}(.*)')
        while i < len(aTags):
            # caseLink field, and save it
            caseLink = aTags[i].get('href')
            caseLink = urljoin(url, caseLink)

            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

            if error:
                # things broke, punt this iteration
                i += 1
                continue

            if not created:
                # it's an oldie, punt!
                if verbose >= 1:
                    result += "Duplicate found at " + str(i) + "\n"
                dupCount += 1
                if dupCount == 3:
                    # third dup in a a row. BREAK!
                    break
                i += 1
                continue
            else:
                dupCount = 0

            # using caselink, we can get the caseNumber and documentType
            fileName = caseLink.split('/')[-1]
            caseNumber, documentType = fileName.split('.')[0:2]
            # the caseNumber needs a hyphen inserted after the second digit
            caseNumber = caseNumber[0:2] + "-" + caseNumber[2:]
            doc.documentType = documentType

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

            # let's check for duplicates before we proceed
            cite, created = hasDuplicate(caseNumber, caseNameShort)

            # last, save evrything (pdf, citation and document)
            doc.citation = cite
            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
            doc.save()

            i += 1
        return result
    
    elif (courtID == 5):
        """New fifth circuit scraper, which can get back versions all the way to 1992!"""
        url = "http://www.ca5.uscourts.gov/Opinions.aspx"
        ct = Court.objects.get(courtUUID='ca5')
        
        """
        # This code was used to get the backlog of cases. Uncomment this section 
        # to get the backlog a second time. It should, however, be complete.
        
        # Build an array of every the date every 30 days from 1992-01-01 to today
        hoy = datetime.date.today()
        unixTimeToday = int(time.mktime(hoy.timetuple()))
        dates = []
        i = 0
        while True:
            # 1992-01-01 + 30 days * i
	        newDate = 1202112000 + (2592000 * i)
            dates.append(datetime.datetime.fromtimestamp(newDate))
            if newDate > unixTimeToday:
                break
            else:
                i += 1
        """
        
        # make an array of two dates: today, and a week ago. That's our range.
        todayObject = datetime.date.today()
        unixTimeToday = int(time.mktime(todayObject.timetuple()))
        unixTimeAWeekAgo = unixTimeToday - 604800
        aWeekAgoObject = datetime.datetime.fromtimestamp(unixTimeAWeekAgo)
        dates = [aWeekAgoObject, todayObject]
        if verbose >= 2: print "dates: " + str(dates)
        
        # next, iterate over these until there are no more!
        j = 0
        while j < (len(dates)-1):
            startDate = time.strftime('%m/%d/%Y', dates[j].timetuple())
            endDate = time.strftime('%m/%d/%Y', dates[j+1].timetuple())
            
            if verbose >= 2:
                print "startDate: " + startDate
                print "endDate: " + endDate
            
            # these are a mess because the court has a security check.
            postValues = {
                '__EVENTTARGET'     : '',
                '__EVENTARGUMENT'   : '',
                '__VIEWSTATE'       : '/wEPDwULLTEwOTU2NTA2NDMPZBYCAgEPZBYKAgEPDxYIHgtDZWxsUGFkZGluZ2YeC0NlbGxTcGFjaW5nZh4JQmFja0NvbG9yCRcQJ/8eBF8hU0ICiIAYZGQCAw8PFggfAGYfAWYfAgmZzP//HwMCiIAYZGQCGQ9kFgYCAg8PFgQfAgqHAR8DAghkZAIEDw8WBB8CCocBHwMCCGRkAgYPDxYEHwIKhwEfAwIIZGQCGw9kFooBAgIPDxYEHwIKhwEfAwIIZGQCBA8PFgQfAgqHAR8DAghkZAIGDw8WBB8CCocBHwMCCGRkAggPDxYEHwIKhwEfAwIIZGQCCg8PFgQfAgqHAR8DAghkZAIMDw8WBB8CCocBHwMCCGRkAg4PDxYEHwIKhwEfAwIIZGQCEA8PFgQfAgqHAR8DAghkZAISDw8WBB8CCocBHwMCCGRkAhQPDxYEHwIKhwEfAwIIZGQCFg8PFgQfAgqHAR8DAghkZAIYDw8WBB8CCocBHwMCCGRkAhoPDxYEHwIKhwEfAwIIZGQCHA8PFgQfAgqHAR8DAghkZAIeDw8WBB8CCocBHwMCCGRkAiAPDxYEHwIKhwEfAwIIZGQCIg8PFgQfAgqHAR8DAghkZAIkDw8WBB8CCocBHwMCCGRkAiYPDxYEHwIKhwEfAwIIZGQCKA8PFgQfAgqHAR8DAghkZAIqDw8WBB8CCocBHwMCCGRkAiwPDxYEHwIKhwEfAwIIZGQCLg8PFgQfAgqHAR8DAghkZAIwDw8WBB8CCocBHwMCCGRkAjIPDxYEHwIKhwEfAwIIZGQCNA8PFgQfAgqHAR8DAghkZAI2Dw8WBB8CCocBHwMCCGRkAjgPDxYEHwIKhwEfAwIIZGQCOg8PFgQfAgqHAR8DAghkZAI8Dw8WBB8CCocBHwMCCGRkAj4PDxYEHwIKhwEfAwIIZGQCQA8PFgQfAgqHAR8DAghkZAJCDw8WBB8CCocBHwMCCGRkAkQPDxYEHwIKhwEfAwIIZGQCRg8PFgQfAgqHAR8DAghkZAJIDw8WBB8CCocBHwMCCGRkAkoPDxYEHwIKhwEfAwIIZGQCTA8PFgQfAgqHAR8DAghkZAJODw8WBB8CCocBHwMCCGRkAlAPDxYEHwIKhwEfAwIIZGQCUg8PFgQfAgqHAR8DAghkZAJUDw8WBB8CCocBHwMCCGRkAlYPDxYEHwIKhwEfAwIIZGQCWA8PFgQfAgqHAR8DAghkZAJaDw8WBB8CCocBHwMCCGRkAlwPDxYEHwIKhwEfAwIIZGQCXg8PFgQfAgqHAR8DAghkZAJgDw8WBB8CCocBHwMCCGRkAmIPDxYEHwIKhwEfAwIIZGQCZA8PFgQfAgqHAR8DAghkZAJmDw8WBB8CCocBHwMCCGRkAmgPDxYEHwIKhwEfAwIIZGQCag8PFgQfAgqHAR8DAghkZAJsDw8WBB8CCocBHwMCCGRkAm4PDxYEHwIKhwEfAwIIZGQCcA8PFgQfAgqHAR8DAghkZAJyDw8WBB8CCocBHwMCCGRkAnQPDxYEHwIKhwEfAwIIZGQCdg8PFgQfAgqHAR8DAghkZAJ4Dw8WBB8CCocBHwMCCGRkAnoPDxYEHwIKhwEfAwIIZGQCfA8PFgQfAgqHAR8DAghkZAJ+Dw8WBB8CCocBHwMCCGRkAoABDw8WBB8CCocBHwMCCGRkAoIBDw8WBB8CCocBHwMCCGRkAoQBDw8WBB8CCocBHwMCCGRkAoYBDw8WBB8CCocBHwMCCGRkAogBDw8WBB8CCocBHwMCCGRkAooBDw8WBB8CCocBHwMCCGRkAh0PEGRkFgECAmRkcx2JRvTiy039dck7+vdOCUS6J5s=', 
                'txtBeginDate'      : startDate,
                'txtEndDate'        : endDate,
                'txtDocketNumber'   : '',
                'txtTitle='         : '',
                'btnSearch'         : 'Search',
                '__EVENTVALIDATION' : '/wEWCALd2o3pAgLH8d2nDwKAzfnNDgLChrRGAr2b+P4BAvnknLMEAqWf8+4KAqC3sP0KVcw25xdB1YPfbcUwUCqEYjQqaqM=',
            }
            j += 1
            
            data = urllib.urlencode(postValues)
            req = urllib2.Request(url, data)
            response = urllib2.urlopen(req)
            html = response.read()
            
            soup = BeautifulSoup(html)
            #if verbose >= 2: print soup
            
            #all links ending in pdf, case insensitive
            aTagRegex = re.compile("pdf$", re.IGNORECASE)
            aTags = soup.findAll(attrs={"href": aTagRegex})
            
            unpubRegex = re.compile(r"pinions.*unpub")
            
            i = 0
            dupCount = 0
            while i < len(aTags):
                print str(aTags[i])
                # this page has PDFs that aren't cases, we must filter them out
                if 'pinion' not in str(aTags[i]):
                    # it's not an opinion, increment and punt
                    if verbose >= 2: print "Punting"
                    i += 1
                    continue

                # we begin with the caseLink field
                caseLink = aTags[i].get('href')
                caseLink = urljoin(url, caseLink)

                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    if verbose >= 1: 
                        result += "Duplicate found at " + str(i) + "\n"
                    dupCount += 1
                    #if dupCount == 3:
                        # third dup in a a row. BREAK!
                        #break
                    i += 1
                    continue
                else:
                    dupCount = 0

                # using caseLink, we can get the caseNumber and documentType
                caseNumber = aTags[i].contents[0]

                if unpubRegex.search(str(aTags[i])) == None:
                    # it's published, else it's unpublished
                    documentType = "P"
                else:
                    documentType = "U"
                if verbose >= 2: print documentType

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

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
                doc.save()

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
        dupCount = 0
        while i < len(aTags):
            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = urljoin(url, caseLink)

            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

            if error:
                # things broke, punt this iteration
                i += 1
                continue

            if not created:
                # it's an oldie, punt!
                if verbose >= 1:
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

            # last, save evrything (pdf, citation and document)
            doc.citation = cite
            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
            doc.save()

            i += 1
        return result

    elif (courtID == 7):
        """another court where we need to do a post. This will be a good
        starting place for getting the judge field, when we're ready for that"""

        url = "http://www.ca7.uscourts.gov/fdocs/docs.fwx"
        ct = Court.objects.get(courtUUID = 'ca7')

        # if these strings change, check that documentType still gets set correctly.
        dataStrings = ("yr=&num=&Submit=Today&dtype=Opinion&scrid=Select+a+Case",
            "yr=&num=&Submit=Today&dtype=Nonprecedential+Disposition&scrid=Select+a+Case")

        for dataString in dataStrings:
            req = urllib2.Request(url, dataString)
            response = urllib2.urlopen(req)
            html = response.read()

            soup = BeautifulSoup(html)

            aTagsRegex = re.compile('pdf$', re.IGNORECASE)
            aTags = soup.findAll(attrs={'href' : aTagsRegex})

            i = 0
            dupCount = 0
            while i < len(aTags):
                # we begin with the caseLink field
                caseLink = aTags[i].get("href")
                caseLink = urljoin(url, caseLink)

                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    if verbose >= 1:
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


                # next up: docStatus
                if "type=Opinion" in dataString:
                    doc.documentType = 'P'
                elif "type=Nonprecedential+Disposition" in dataString:
                    doc.documentType = 'U'

                # now that we have the caseNumber and caseNameShort, we can dup check
                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
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
        dupCount = 0
        while i < len(aTags):
            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = urljoin(url, caseLink)

            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

            if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

            if not created:
                # it's an oldie, punt!
                if verbose >= 1:
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

            # last, save evrything (pdf, citation and document)
            doc.citation = cite
            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
            doc.save()

            i += 1

        return result

    elif (courtID == 9):
        """This court, by virtue of having a javascript laden website, was very
        hard to parse properly. BeautifulSoup couldn't handle it at all, so lxml
        has to be used. lxml seems pretty useful, but it was a pain to learn."""

        urls = ("http://www.ca9.uscourts.gov/opinions/?o_mode=view&amp;o_sort_field=19&amp;o_sort_type=DESC&o_page_size=100", "http://www.ca9.uscourts.gov/memoranda/?o_mode=view&amp;o_sort_field=21&amp;o_sort_type=DESC&o_page_size=100",)

        ct = Court.objects.get(courtUUID = 'ca9')

        for url in urls:
            req = urllib2.urlopen(url).read()
            tree = fromstring(req)

            if url == urls[0]:
                caseLinks = tree.xpath('//table[3]/tbody/tr/td/a')
                caseNumbers = tree.xpath('//table[3]/tbody/tr/td[2]/label')
                caseDates = tree.xpath('//table[3]/tbody/tr/td[6]/label')
            elif url == urls[1]:
                caseLinks = tree.xpath('//table[3]/tbody/tr/td/a')
                caseNumbers = tree.xpath('//table[3]/tbody/tr/td[2]/label')
                caseDates = tree.xpath('//table[3]/tbody/tr/td[7]/label')

            i = 0
            dupCount = 0
            while i < len(caseLinks):
                # we begin with the caseLink field
                caseLink = caseLinks[i].get('href')
                caseLink = urljoin(url, caseLink)

                # special case
                if 'no memos filed' in caseLink.lower():
                    i += 1
                    continue

                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    if verbose >= 1:
                        result += "Duplicate found at " + str(i) + "\n"
                    dupCount += 1
                    if dupCount == 3:
                        # third dup in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                # next, we'll do the caseNumber
                caseNumber = caseNumbers[i].text

                # next up: document type (static for now)
                if 'memoranda' in url:
                    doc.documentType = "U"
                elif 'opinions' in url:
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

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
                doc.save()

                i += 1

        return result

    elif (courtID == 10):
        # a daily feed of all the items posted THAT day. Missing a day == bad.
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
        dupCount = 0
        while i < len(caseLinks):
            # we begin with the caseLink field
            caseLink = caseLinks[i].text
            caseLink = urljoin(url, caseLink)

            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

            if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

            if not created:
                # it's an oldie, punt!
                if verbose >= 1:
                    result += "Duplicate found at " + str(i) + "\n"
                dupCount += 1
                if dupCount == 3:
                    # third dup in a a row. BREAK!
                    break
                i += 1
                continue
            else:
                dupCount = 0

            # next: docType (this order of if statements IS correct)
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

            # last, save evrything (pdf, citation and document)
            doc.citation = cite
            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
            doc.save()

            i += 1

        return result

    elif (courtID == 11):
        """Trying out an RSS feed this time, since the feed looks good. This
        court lacks a feed for unpublished opinions, so they are fetched after
        the below RSS feed finishes."""
        # Missing a day == OK.
        url = "http://www.ca11.uscourts.gov/rss/pubopnsfeed.php"
        ct = Court.objects.get(courtUUID = 'ca11')

#        req = urllib2.urlopen(url)

#        # this code gets rid of errant ampersands - they throw big errors.
#        contents = req.read()
#        if '&' in contents:
#            punctuationRegex = re.compile(" & ")
#            contents = re.sub(punctuationRegex, " &amp; ", contents)
#            tree = etree.fromstring(contents)
#        else:
#            tree = etree.fromstring(contents)

#        caseLinks = tree.xpath('//item/link')
#        description = tree.xpath('//item/description')
#        caseNames = tree.xpath('//item/title')

#        # some regexes
#        caseNumRegex = re.compile('''
#            case            # the word case
#            .*?             # some junk, not greedy
#            (\d{2}-\d{5})   # two digits a hyphen then five more
#            ''', re.IGNORECASE | re.VERBOSE)

#        # this could be improved with time.strptimme.
#        caseDateRegex = re.compile('''
#            date                    # the word date
#            .*?                     # some junk, not greedy
#            (\d{2}-\d{2}-\d{4})     # two digits - two digits - four digits
#            ''', re.IGNORECASE | re.VERBOSE)

#        i = 0
#        dupCount = 0
#        while i < len(caseLinks):
#            # we begin with the caseLink field
#            caseLink = caseLinks[i].text
#            caseLink = urljoin(url, caseLink)

#            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

#            if error:
#                    # things broke, punt this iteration
#                    i += 1
#                    continue

#            if not created:
#                # it's an oldie, punt!
#                if verbose >= 1:
#                    result += "Duplicate found at " + str(i) + "\n"
#                dupCount += 1
#                if dupCount == 3:
#                    # third dup in a a row. BREAK!
#                    break
#                i += 1
#                continue
#            else:
#                dupCount = 0

#            # these are only published opinions, unpublished lack a feed (boo!)
#            doc.documentType = "P"

#            # next, we'll do the caseNumber
#            caseNumber = caseNumRegex.search(description[i].text).group(1)

#            # next up: caseDate
#            caseDate = caseDateRegex.search(description[i].text).group(1)
#            splitDate = caseDate.split('-')
#            caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
#                int(splitDate[1]))
#            doc.dateFiled = caseDate

#            #next up: caseNameShort
#            caseNameShort = caseNames[i].text

#            # now that we have the caseNumber and caseNameShort, we can dup check
#            cite, created = hasDuplicate(caseNumber, caseNameShort)

#            # if that goes well, we save to the DB
#            doc.citation = cite

#            # last, save evrything (pdf, citation and document)
#            doc.citation = cite
#            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
#            doc.save()

#            i += 1

        urls = (
            "http://www.ca11.uscourts.gov/unpub/searchdate.php",
            "http://www.ca11.uscourts.gov/opinions/searchdate.php",
        )
        
        for url in urls:
            if 'unpub' in url:
                i = 0
                years = []
                while i <= 1:
                    j = 5
                    while j <= 12:
                        if j < 10:
                            month = "0" + str(j)
                        else:
                            month = str(j)
                        years.append(str(2008+i) + "-" + month)
                        j += 1
                    i += 1
                if verbose >= 2: print "years: " + str(years)
            elif 'opinions' in url:
                i = 0
                years = []
                while i <= 16:
                    j = 1
                    while j <= 12:
                        if j < 10:
                            month = "0" + str(j)
                        else:
                            month = str(j)
                        years.append(str(1994+i) + "-" + month)
                        j += 1
                    i += 1
                if verbose >= 2: print "years: " + str(years)

            for year in years:
                postValues = {
                    'date'  : year,
                }
                
                data = urllib.urlencode(postValues)
                req = urllib2.Request(url, data)
                response = urllib2.urlopen(req)
                html = response.read()

                tree = fromstring(html)
                
                if 'unpub' in url:
                    caseNumbers = tree.xpath('//table[3]//table//table/tr[1]/td[2]')
                    caseLinks   = tree.xpath('//table[3]//table//table/tr[3]/td[2]/a')
                    caseDates   = tree.xpath('//table[3]//table//table/tr[4]/td[2]')
                    caseNames   = tree.xpath('//table[3]//table//table/tr[6]/td[2]')
                elif 'opinion' in url:
                    caseNumbers = tree.xpath('//table[3]//td[3]//table/tr[1]/td[2]')
                    caseLinks   = tree.xpath('//table[3]//td[3]//table/tr[3]/td[2]/a')
                    caseDates   = tree.xpath('//table[3]//td[3]//table/tr[4]/td[2]')
                    caseNames   = tree.xpath('//table[3]//td[3]//table/tr[6]/td[2]')
                
                '''
                # for debugging
                print "length: " + str(len(caseNames))
                for foo in caseNames:
                    print str(foo.text)
                
                return result'''
                
                i = 0
                dupCount = 0
                while i < len(caseNumbers):
                    caseLink = caseLinks[i].get('href')
                    caseLink = urljoin(url, caseLink)
                    
                    myFile, doc, created, error = makeDocFromURL(caseLink, ct)
                    
                    if error:
                        # things broke, punt this iteration
                        i += 1
                        continue
                    
                    if not created:
                        # it's an oldie, punt!
                        if verbose >= 1: 
                            result += "Duplicate found at " + str(i) + "\n"
			if verbose >= 2:
			    print "Duplicate found at " + str(i)
                        dupCount += 1
                        #if dupCount == 3:
                            # third dup in a a row. BREAK!
                            #break
                        i += 1
                        continue
                    else:
                        dupCount = 0
                    
                    if 'unpub' in url:
                        doc.documentType = "U"
                    elif 'opinion' in url:
                        doc.documentType = "P"
                    if verbose >= 2: print "documentType: " + str(doc.documentType)
                    
                    cleanDate = caseDates[i].text.strip()
                    doc.dateFiled = datetime.datetime(*time.strptime(cleanDate, "%m-%d-%Y")[0:5])
                    if verbose >= 2: print "dateFiled: " + str(doc.dateFiled)
                    
                    caseNameShort = caseNames[i].text
                    caseNumber = caseNumbers[i].text
                    
                    cite, created = hasDuplicate(caseNumber, caseNameShort)
                    if verbose >= 2: 
                        print "caseNameShort: " + cite.caseNameShort
                        print "caseNumber: " + cite.caseNumber + "\n"
                    
                    doc.citation = cite
                    doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
                    doc.save()
                    
                    i += 1
        return result

    elif (courtID == 12):
        # terrible site. Code assumes that we download the opinion on the day
        # it is released. If we miss a day, that could cause a problem.
        url = "http://www.cadc.uscourts.gov/bin/opinions/allopinions.asp"
        ct = Court.objects.get(courtUUID = 'cadc')

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)

        aTagsRegex = re.compile('pdf$', re.IGNORECASE)
        aTags = soup.findAll(attrs={'href' : aTagsRegex})

        caseNumRegex = re.compile("(\d{2}-\d{4})")

        i = 0
        dupCount = 0
        while i < len(aTags):
            # we begin with the caseLink field
            caseLink = aTags[i].get('href')
            caseLink = urljoin(url, caseLink)

            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

            if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

            if not created:
                # it's an oldie, punt!
                if verbose >= 1:
                    result += "Duplicate found at " + str(i) + "\n"
                dupCount += 1
                if dupCount == 3:
                    # third dup in a a row. BREAK!
                    break
                i += 1
                continue
            else:
                dupCount = 0

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

            # if that goes well, we save to the DB
            doc.citation = cite

            # last, save evrything (pdf, citation and document)
            doc.citation = cite
            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
            doc.save()

            i += 1

        return result

    elif (courtID == 13):
        # running log of all opinions
        url = "http://www.cafc.uscourts.gov/dailylog.html"
        ct = Court.objects.get(courtUUID = "cafc")

        html = urllib2.urlopen(url)
        soup = BeautifulSoup(html)

        aTagsRegex = re.compile('pdf$', re.IGNORECASE)
        trTags = soup.findAll('tr')

        # start on the second row, since the first is headers.
        i = 1
        dupCount = 0
        while i <= 50: #stop at 50, if no triple dups first.
            try:
                caseLink = trTags[i].td.nextSibling.nextSibling.nextSibling\
                    .nextSibling.nextSibling.nextSibling.a.get('href').strip('.')
                caseLink = urljoin(url, caseLink)
                if 'opinion' not in caseLink:
                    # we have a non-case PDF. punt
                    i += 1
                    continue
            except:
                # the above fails when things get funky, in that case, we punt
                i += 1
                continue

            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

            if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

            if not created:
                # it's an oldie, punt!
                if verbose >= 1:
                    result += "Duplicate found at " + str(i) + "\n"
                dupCount += 1
                if dupCount == 3:
                    # third dup in a a row. BREAK!
                    break
                i += 1
                continue
            else:
                dupCount = 0

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
            # normalize the result for our internal purposes...
            if documentType == 'N':
                documentType = 'U'
            doc.documentType = documentType

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)

            # last, save evrything (pdf, citation and document)
            doc.citation = cite
            doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
            doc.save()

            i += 1

        return result

    if (courtID == 14):
        # we do SCOTUS
        urls = ("http://www.supremecourt.gov/opinions/slipopinions.aspx",
                "http://www.supremecourt.gov/opinions/in-chambers.aspx",
                "http://www.supremecourt.gov/opinions/relatingtoorders.aspx",)

        ct = Court.objects.get(courtUUID = 'scotus')

        for url in urls:
            req = urllib2.urlopen(url).read()
            tree = fromstring(req)

            if 'slipopinion' in url:
                caseLinks = tree.xpath('//table/tr/td[4]/a')
                caseNumbers = tree.xpath('//table/tr/td[3]')
                caseDates = tree.xpath('//table/tr/td[2]')
            elif 'in-chambers' in url:
                caseLinks = tree.xpath('//table/tr/td[3]/a')
                caseNumbers = tree.xpath('//table/tr/td[2]')
                caseDates = tree.xpath('//table/tr/td[1]')
            elif 'relatingtoorders' in url:
                caseLinks = tree.xpath('//table/tr/td[3]/a')
                caseNumbers = tree.xpath('//table/tr/td[2]')
                caseDates = tree.xpath('//table/tr/td[1]')

            i = 0
            dupCount = 0
            while i < len(caseLinks):
                # we begin with the caseLink field
                caseLink = caseLinks[i].get('href')
                caseLink = urljoin(url, caseLink)

                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    if verbose >= 1:
                        result += "Duplicate found at " + str(i) + "\n"
                    dupCount += 1
                    if dupCount == 3:
                        # third dup in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                caseNumber = caseNumbers[i].text

                caseNameShort = caseLinks[i].text

                if 'slipopinion' in url:
                    doc.documentType = "P"
                elif 'in-chambers' in url:
                    doc.documentType = "I"
                elif 'relatingtoorders' in url:
                    doc.documentType = "R"

                if '/' in caseDates[i].text:
                    splitDate = caseDates[i].text.split('/')
                elif '-' in caseDates[i].text:
                    splitDate = caseDates[i].text.split('-')
                year = int("20" + splitDate[2])
                caseDate = datetime.date(year, int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate

                # now that we have the caseNumber and caseNameShort, we can dup check
                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
                doc.save()

                i += 1

        return result


def parseCourt(courtID, result, verbose):
    """Here, we do the following:
        1. For a given court, find all of its documents
        2. Determine if the document has been parsed already
        3. If it has, punt, if not, open the PDF and parse it.

    returns a string containing the result"""

    # get the court IDs from models.py
    courts = []
    for code in PACER_CODES:
        courts.append(code[0])

    # select all documents from this jurisdiction that lack plainText (this
    # achieves duplicate checking.
    selectedDocuments = Document.objects.filter(documentPlainText = "",
        court__courtUUID = courts[courtID-1])

    for doc in selectedDocuments:
        # for each of these documents, open it, parse it.
        if verbose >= 1:
            result += "Parsed: " + doc.citation.caseNameShort + "\n"

        relURL = str(doc.local_path)
        relURL = settings.MEDIA_ROOT + relURL
        doc.documentPlainText = getPDFContent(relURL)[0]
        doc.save()

    return result


def scrape_and_parse(courtID, verbose):
    """
    The master function. This will receive a court ID, determine the correct
    action to take, then hand it off to another function that will handle the
    nitty-gritty crud.

    If the courtID is 0, then we scrape all courts, one after the next.

    returns a list containing the result
    """

    # we show this string to stdout if things go smoothly
    if verbose >= 1:
        result = "It worked\n"

    # some data validation, for good measure - this should already be done via
    # our url regex
    try:
        courtID = int(courtID)
    except:
        result = "Error: court not found\n"
        raise django.core.exceptions.ObjectDoesNotExist

    # next, we attack the court requested.
    if (courtID == 0):
        # we do ALL of the courts (useful for testing)
        i = 1
        from alertSystem.models import PACER_CODES
        while i <= len(PACER_CODES):
            if verbose >= 1:
                result += "NOW SCRAPING COURT: " + str(i) + "\n"
            result = scrapeCourt(i, result, verbose) + "\n\n"
            if verbose >= 1:
                result += "NOW PARSING COURT: " + str(i) + "\n\n"
            result = parseCourt(i, result, verbose)
            i += 1
    else:
        result += scrapeCourt(courtID, result, verbose)
        result += parseCourt(courtID, result, verbose)
    return result


def main():
    usage = "usage: %prog (-s SCRAPEID | -p PARSEID) [-v | -V]"
    parser = OptionParser(usage)
    parser.add_option('-s', '--scrape', dest='scrapeID', metavar='SCRAPEID',
                      help="The court to scrape and parse")
    parser.add_option('-p', '--parse', dest='parseID', metavar='PARSEID',
                      help="The court to only parse")
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose', 
        default=False, help="Display status messages after execution")
    parser.add_option('-V', '--vverbose', action="store_true", dest='vverbose', 
        default=False, help="Display status messages after execution, and display verbose variable values during execution")
    (options, args) = parser.parse_args()
    if not options.scrapeID or options.parseID:
        parser.error("You must specify a court to scrape and/or parse")

    if options.verbose:
        verbose = 1
    elif options.vverbose:
        verbose = 2
    
    if options.parseID:
        # we are only parsing.
        courtID = options.parseID
        if verbose >= 1: result = "It worked\n"
        print parseCourt(courtID, result, verbose)
    elif options.scrapeID:
        # we scrape and parse. Currently no option to only scrape.
        courtID = options.scrapeID
        print scrape_and_parse(courtID, verbose)

    return 0


if __name__ == '__main__':
    main()
