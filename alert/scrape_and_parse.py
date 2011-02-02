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
from alertSystem.string_utils import *

from django.utils.encoding import smart_str
from django.core.exceptions import MultipleObjectsReturned
from django.core.files import File
from django.core.files.base import ContentFile

import datetime, calendar, hashlib, re, signal, StringIO, subprocess, sys, time, urllib, urllib2
from BeautifulSoup import BeautifulSoup
from lxml.html import fromstring, tostring
from lxml import etree
from optparse import OptionParser
from urlparse import urljoin
from datetime import datetime
from time import mktime

import logging
import logging.handlers

DAEMONMODE = False
VERBOSITY = 0
LOG_FILENAME = '/var/log/scraper/daemon_log.out'

# Set up a specific logger with our desired output level
logger = logging.getLogger('Logger')
logger.setLevel(logging.DEBUG)

# Add the log message handler to the logger
handler = logging.handlers.RotatingFileHandler(
              LOG_FILENAME, maxBytes=512000, backupCount=1)

logger.addHandler(handler)

# for use in catching the SIGINT (Ctrl+C)
dieNow = False

def signal_handler(signal, frame):
    print 'Exiting safely...this will finish the current court, then exit...'
    dieNow = True


def readURL(url, courtID):
    try: html = urllib2.urlopen(url).read()
    except urllib2.HTTPError, e:
        print "****ERROR CONNECTING TO COURT: " + str(courtID) + "****"
        print 'HTTPError = ' + str(e.code)
    except urllib2.URLError, e:
        print "****ERROR CONNECTING TO COURT: " + str(courtID) + "****"
        print 'URLError = ' + str(e.reason)
    except httplib.HTTPException, e:
        print "****ERROR CONNECTING TO COURT: " + str(courtID) + "****"
        print 'HTTPException'
    except Exception:
        import traceback
        print "****ERROR CONNECTING TO COURT: " + str(courtID) + "****"
        print 'Generic Exception: ' + traceback.format_exc()
    return html


def makeDocFromURL(LinkToDoc, ct):
    '''Receives a URL and a court as arguments, then downloads the PDF
    that's in it, and makes it into a StringIO. Generates a sha1 hash of the
    file, and tries to add it to the db. If it's a duplicate, it gets the one in
    the DB. If it's a new sha1, it creates a new document.

    returns a StringIO of the PDF, a Document object, and a boolean indicating
    whether the Document was created
    '''

    # get the Doc
    try:
        webFile = urllib2.urlopen(LinkToDoc)
        stringThing = StringIO.StringIO()
        stringThing.write(webFile.read())
        myFile = ContentFile(stringThing.getvalue())
        webFile.close()
    except:
        print "ERROR DOWNLOADING FILE!: " + str(LinkToDoc)
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
        doc.download_URL = LinkToDoc
        doc.court = ct
        doc.source = "C"

    error = False

    return myFile, doc, created, error


def courtChanged(url, contents):
    """Takes HTML contents from a court download, generates a SHA1, and then
    compares that hash to a value in the DB, if there is one. If there is a value
    and it is the same, it returns false. Else, it returns true."""
    sha1Hash = hashlib.sha1(contents).hexdigest()
    url2Hash, created = urlToHash.objects.get_or_create(url=url)

    if not created and url2Hash.SHA1 == sha1Hash:
        # it wasn't created, and it has the same SHA --> not changed.
        return False
    else:
        # Whether or not it was created, it's a change, and so we update the SHA
        # and save the changes.
        url2Hash.SHA1 = sha1Hash
        url2Hash.save()

        # Log the change time and URL
        try:
            logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + ": URL: " + url)
        except UnicodeDecodeError:
            pass

        return True


def hasDuplicate(caseNum, caseName):
    """takes a caseName and a caseNum, and checks if the object exists in the
    DB. If it doesn't, then it puts it in. If it does, it returns it.
    """

    # data cleanup
    caseName = harmonize(clean_string(caseName))
    caseNum  = clean_string(caseNum)

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


def getDocContent(docs):
    """Get the contents of a list of files, and add them to the DB, sniffing
    their mimetype."""
    for doc in docs:
        path = str(doc.local_path)
        path = settings.MEDIA_ROOT + path

        mimetype = path.split('.')[-1]
        if mimetype == 'pdf':
            # do the pdftotext work for PDFs
            process = subprocess.Popen(
                ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"], shell=False,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            content, err = process.communicate()
            if err: print "****Error extracting text from: " + doc.citation.caseNameShort + "****"
        elif mimetype == 'txt':
            # read the contents of text files.
            try:
                content = open(path).read()
            except:
                print "****Error extracting plain text from: " + doc.citation.caseNameShort + "****"
                continue
        else:
            print "*****Unknown mimetype. Unable to parse: " + doc.citation.caseNameShort + "****"
            continue

        # add the anonymized plain text to the DB. Don't run clean_string on this
        # because that removes the white space and newlines (see r538)!
        doc.documentPlainText = anonymize(content)
        try:
            doc.save()
        except Exception, e:
            print "****Error saving text to the db for: " + doc.citation.caseNameShort + "****"


def scrapeCourt(courtID, DAEMONMODE, VERBOSITY):
    if VERBOSITY >= 1: print "NOW SCRAPING COURT: " + str(courtID)

    if (courtID == 1):
        """
        PDFs are available from the first circuit if you go to their RSS feed.
        So go to their RSS feed we shall.
        """
        urls = ("http://www.ca1.uscourts.gov/opinions/opinionrss.php",)
        ct = Court.objects.get(courtUUID='ca1')

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            # this code gets rid of errant ampersands - they throw big errors
            # when parsing. We replace them later.
            if '&' in html:
                punctuationRegex = re.compile(" & ")
                html = re.sub(punctuationRegex, " &amp; ", html)
                tree = etree.fromstring(html)
            else:
                tree = etree.fromstring(html)

            caseLinks = tree.xpath("//item/link")
            descriptions = tree.xpath("//item/description")
            docTypes = tree.xpath("//item/category")
            caseNamesAndNumbers = tree.xpath("//item/title")

            caseDateRegex = re.compile("(\d{2}/\d{2}/\d{4})",
                re.VERBOSE | re.DOTALL)
            caseNumberRegex = re.compile("(\d{2}-.*?\W)(.*)$")

            # incredibly, this RSS feed is in cron order, so new stuff is at the
            # end. Mind blowing.
            i = len(caseLinks)-1

            dupCount = 0
            while i > 0:
                # First: docType, since we don't support them all...
                docType = docTypes[i].text.strip()
                if "unpublished" in docType.lower():
                    documentType = "Unpublished"
                elif "published" in docType.lower():
                    documentType = "Published"
                elif "errata" in docType.lower():
                    documentType = "Errata"
                else:
                    # something weird we don't know about, punt
                    i -= 1
                    continue

                # next, we begin with the caseLink field
                caseLink = caseLinks[i].text
                caseLink = urljoin(url, caseLink)

                # then we download the PDF, make the hash and document
                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i -= 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    dupCount += 1
                    if dupCount == 8:
                        # eighth dup in a a row. BREAK!
                        # this is 8 here b/c this court has tech problems.
                        break
                    i -= 1
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
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i -= 1
        return

    elif (courtID == 2):
        """
        URL hacking FTW.
        """
        urls = (
            "http://www.ca2.uscourts.gov/decisions?IW_DATABASE=OPN&IW_FIELD_TEXT=OPN&IW_SORT=-Date&IW_BATCHSIZE=100",
            "http://www.ca2.uscourts.gov/decisions?IW_DATABASE=SUM&IW_FIELD_TEXT=SUM&IW_SORT=-Date&IW_BATCHSIZE=100",
        )
        ct = Court.objects.get(courtUUID='ca2')

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            soup = BeautifulSoup(html)

            aTagsRegex = re.compile('(.*?.pdf).*?', re.IGNORECASE)
            caseNumRegex = re.compile('.*/(\d{1,2}-\d{1,4})(.*).pdf')
            aTags = soup.findAll(attrs={'href' : aTagsRegex})

            if DAEMONMODE:
                # this mess is necessary because the court puts random
                # (literally) numbers throughout their links. No idea why,
                # but the solution is to figure out the caselinks here, and to hand
                # those to the sha1 generator.
                aTagsEncoded = []
                for i in aTags:
                    caseLink = i.get('href')
                    caseLink = aTagsRegex.search(caseLink).group(1)
                    try:
                        caseNumbers = caseNumRegex.search(caseLink).group(1)
                    except:
                        caseNumbers = ""
                    aTagsEncoded.append(caseNumbers)

                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, str(aTagsEncoded))
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            i = 0
            dupCount = 0
            while i < len(aTags):
                # we begin with the caseLink field
                caseLink = aTags[i].get('href')
                caseLink = aTagsRegex.search(caseLink).group(1)
                caseLink = urljoin(url, caseLink)

                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
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
                    doc.documentType = "Published"
                elif 'so' in documentType:
                    doc.documentType = "Unpublished"

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
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 3):
        """
        This URL provides the latest 25 cases, so I need to pick out the new
        ones and only get those. I can do this efficiently by trying to do each,
        and then giving up once I hit one that I've done before. This will work
        because they are in reverse chronological order.
        """

        # if these URLs change, the docType identification (below) will need
        # to be updated. It's lazy, but effective.
        urls = (
            "http://www.ca3.uscourts.gov/recentop/week/recprec.htm",
            #"http://www.ca3.uscourts.gov/recentop/week/recnon2day.htm",
            )
        ct = Court.objects.get(courtUUID='ca3')

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

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
            while i < len(aTags) :
                # caseLink and caseNameShort
                caseLink = aTags[i].get('href')

                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
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
                    i += 1
                    continue

                # next up is the caseDate
                splitDate = caseDate.split('/')
                caseDate = datetime.date(int("20" + splitDate[2]),int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate

                # Make a decision about the docType.
                if "recprec.htm" in str(url):
                    doc.documentType = "Published"
                elif "recnon2day.htm" in str(url):
                    doc.documentType = "Unpublished"

                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 4):
        """The fourth circuit is THE worst form of HTML I've ever seen. It's
        going to break a lot, but I've done my best to clean it up, and make it
        reliable."""
        urls = ("http://pacer.ca4.uscourts.gov/opinions_today.htm",)
        ct = Court.objects.get(courtUUID='ca4')

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

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
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
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

                if documentType == 'U':
                    doc.documentType = 'Unpublished'
                elif documentType == 'P':
                    doc.documentType = 'Published'
                else:
                    doc.documentType = ""

                # next, we do the caseDate and caseNameShort, so we can quit before
                # we get too far along.
                junk = aTags[i].contents[0].replace('&nbsp;', ' ').strip()
                try:
                    # this error seems to happen upon dups...not sure why yet
                    caseDate = clean_string(regexII.search(junk).group(0))
                    caseNameShort = regexIII.search(junk).group(1)
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
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 5):
        """New fifth circuit scraper, which can get back versions all the way to
        1992!

        This is exciting, but be warned, the search is not reliable on recent
        dates. It has been known not to bring back results that are definitely
        within the set. Watch closely.
        """
        urls = ("http://www.ca5.uscourts.gov/Opinions.aspx",)
        ct = Court.objects.get(courtUUID = 'ca5')

        for url in urls:
            # Use just one date, it seems to work better this way.
            todayObject = datetime.date.today()
            startDate = time.strftime('%m/%d/%Y', todayObject.timetuple())

            # these are a mess because the court has a security check.
            postValues = {
                '__EVENTTARGET'     : '',
                '__EVENTARGUMENT'   : '',
                '__VIEWSTATE'       : '/wEPDwULLTEwOTU2NTA2NDMPZBYCAgEPZBYKAgEPDxYIHgtDZWxsUGFkZGluZ2YeC0NlbGxTcGFjaW5nZh4JQmFja0NvbG9yCRcQJ/8eBF8hU0ICiIAYZGQCAw8PFggfAGYfAWYfAgmZzP//HwMCiIAYZGQCGQ9kFgYCAg8PFgQfAgqHAR8DAghkZAIEDw8WBB8CCocBHwMCCGRkAgYPDxYEHwIKhwEfAwIIZGQCGw9kFooBAgIPDxYEHwIKhwEfAwIIZGQCBA8PFgQfAgqHAR8DAghkZAIGDw8WBB8CCocBHwMCCGRkAggPDxYEHwIKhwEfAwIIZGQCCg8PFgQfAgqHAR8DAghkZAIMDw8WBB8CCocBHwMCCGRkAg4PDxYEHwIKhwEfAwIIZGQCEA8PFgQfAgqHAR8DAghkZAISDw8WBB8CCocBHwMCCGRkAhQPDxYEHwIKhwEfAwIIZGQCFg8PFgQfAgqHAR8DAghkZAIYDw8WBB8CCocBHwMCCGRkAhoPDxYEHwIKhwEfAwIIZGQCHA8PFgQfAgqHAR8DAghkZAIeDw8WBB8CCocBHwMCCGRkAiAPDxYEHwIKhwEfAwIIZGQCIg8PFgQfAgqHAR8DAghkZAIkDw8WBB8CCocBHwMCCGRkAiYPDxYEHwIKhwEfAwIIZGQCKA8PFgQfAgqHAR8DAghkZAIqDw8WBB8CCocBHwMCCGRkAiwPDxYEHwIKhwEfAwIIZGQCLg8PFgQfAgqHAR8DAghkZAIwDw8WBB8CCocBHwMCCGRkAjIPDxYEHwIKhwEfAwIIZGQCNA8PFgQfAgqHAR8DAghkZAI2Dw8WBB8CCocBHwMCCGRkAjgPDxYEHwIKhwEfAwIIZGQCOg8PFgQfAgqHAR8DAghkZAI8Dw8WBB8CCocBHwMCCGRkAj4PDxYEHwIKhwEfAwIIZGQCQA8PFgQfAgqHAR8DAghkZAJCDw8WBB8CCocBHwMCCGRkAkQPDxYEHwIKhwEfAwIIZGQCRg8PFgQfAgqHAR8DAghkZAJIDw8WBB8CCocBHwMCCGRkAkoPDxYEHwIKhwEfAwIIZGQCTA8PFgQfAgqHAR8DAghkZAJODw8WBB8CCocBHwMCCGRkAlAPDxYEHwIKhwEfAwIIZGQCUg8PFgQfAgqHAR8DAghkZAJUDw8WBB8CCocBHwMCCGRkAlYPDxYEHwIKhwEfAwIIZGQCWA8PFgQfAgqHAR8DAghkZAJaDw8WBB8CCocBHwMCCGRkAlwPDxYEHwIKhwEfAwIIZGQCXg8PFgQfAgqHAR8DAghkZAJgDw8WBB8CCocBHwMCCGRkAmIPDxYEHwIKhwEfAwIIZGQCZA8PFgQfAgqHAR8DAghkZAJmDw8WBB8CCocBHwMCCGRkAmgPDxYEHwIKhwEfAwIIZGQCag8PFgQfAgqHAR8DAghkZAJsDw8WBB8CCocBHwMCCGRkAm4PDxYEHwIKhwEfAwIIZGQCcA8PFgQfAgqHAR8DAghkZAJyDw8WBB8CCocBHwMCCGRkAnQPDxYEHwIKhwEfAwIIZGQCdg8PFgQfAgqHAR8DAghkZAJ4Dw8WBB8CCocBHwMCCGRkAnoPDxYEHwIKhwEfAwIIZGQCfA8PFgQfAgqHAR8DAghkZAJ+Dw8WBB8CCocBHwMCCGRkAoABDw8WBB8CCocBHwMCCGRkAoIBDw8WBB8CCocBHwMCCGRkAoQBDw8WBB8CCocBHwMCCGRkAoYBDw8WBB8CCocBHwMCCGRkAogBDw8WBB8CCocBHwMCCGRkAooBDw8WBB8CCocBHwMCCGRkAh0PEGRkFgECAmRkcx2JRvTiy039dck7+vdOCUS6J5s=',
                'txtBeginDate'      : startDate,
                'txtEndDate'        : '',
                'txtDocketNumber'   : '',
                'txtTitle='         : '',
                'btnSearch'         : 'Search',
                '__EVENTVALIDATION' : '/wEWCALd2o3pAgLH8d2nDwKAzfnNDgLChrRGAr2b+P4BAvnknLMEAqWf8+4KAqC3sP0KVcw25xdB1YPfbcUwUCqEYjQqaqM=',
            }

            data = urllib.urlencode(postValues)
            req = urllib2.Request(url, data)
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            soup = BeautifulSoup(html)

            #all links ending in pdf, case insensitive
            aTagRegex = re.compile("pdf$", re.IGNORECASE)
            aTags = soup.findAll(attrs={"href": aTagRegex})

            unpubRegex = re.compile(r"pinions.*unpub")

            i = 0
            dupCount = 0
            numP = 0
            numQ = 0
            while i < len(aTags):
                # this page has PDFs that aren't cases, we must filter them out
                if 'pinion' not in str(aTags[i]):
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

                # next, we do the docStatus field, b/c we need to include it in
                # the dup check. This is because we need to abort after we have
                # three non-precedential and three precedential from this court.
                if unpubRegex.search(str(aTags[i])) == None:
                    # it's published, else it's unpublished
                    documentType = "Published"
                    numP += 1
                else:
                    documentType = "Unpublished"
                    numQ += 1
                doc.documentType = documentType

                if not created:
                    # it's an oldie, punt!
                    dupCount += 1
                    if dupCount >= 3 and numP >= 3 and numQ >= 3:
                        # third dup in a a row for both U and P.
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                # using caseLink, we can get the caseNumber and documentType
                caseNumber = aTags[i].contents[0]

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
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 6):
        """Results are available without an HTML POST, but those results lack a
        date field. Hence, we must do an HTML POST.

        Missing a day == OK. Just need to monkey with the date POSTed.
        """
        urls = ("http://www.ca6.uscourts.gov/cgi-bin/opinions.pl",)
        ct = Court.objects.get(courtUUID = 'ca6')

        for url in urls:
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
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

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
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                # using caseLink, we can get the caseNumber and documentType
                caseNumber = aTags[i].next.next.next.next.next.contents[0]

                # using the filename, we can determine the documentType...
                fileName = aTags[i].contents[0]
                if 'n' in fileName:
                    # it's unpublished
                    doc.documentType = "Unpublished"
                elif 'p' in fileName:
                    doc.documentType = "Published"

                # next, we can do the caseDate
                caseDate = aTags[i].next.next.next.next.next.next.next.next\
                    .contents[0]
                caseDate = clean_string(caseDate)

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
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 7):
        """another court where we need to do a post. This will be a good
        starting place for getting the judge field, when we're ready for that.

        Missing a day == OK. Queries return cases for the past week.
        """
        urls = ("http://www.ca7.uscourts.gov/fdocs/docs.fwx",)
        ct = Court.objects.get(courtUUID = 'ca7')

        for url in urls:
            # if these strings change, check that documentType still gets set correctly.
            dataStrings = ("yr=&num=&Submit=Past+Week&dtype=Opinion&scrid=Select+a+Case",
                "yr=&num=&Submit=Past+Week&dtype=Nonprecedential+Disposition&scrid=Select+a+Case",)

            for dataString in dataStrings:
                req = urllib2.Request(url, dataString)
                try: html = readURL(url, courtID)
                except: continue

                if DAEMONMODE:
                    # if it's DAEMONMODE, see if the court has changed
                    changed = courtChanged(url+dataString, html)
                    if not changed:
                        # if not, bail. If so, continue to the scraping.
                        return

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
                        dupCount += 1
                        if dupCount == 5:
                            # fifth dup in a a row. BREAK!
                            break
                        i += 1
                        continue
                    else:
                        dupCount = 0

                    # using caseLink, we can get the caseNumber and documentType
                    caseNumber = aTags[i].previous.previous.previous.previous.previous\
                        .previous.previous.previous.previous.previous

                    # next up: caseDate
                    caseDate = aTags[i].previous.previous.previous.contents[0]
                    caseDate = clean_string(caseDate)
                    splitDate = caseDate.split('/')
                    caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                        int(splitDate[1]))
                    doc.dateFiled = caseDate

                    # next up: caseNameShort
                    caseNameShort = aTags[i].previous.previous.previous.previous\
                        .previous.previous.previous

                    # next up: docStatus
                    if "type=Opinion" in dataString:
                        doc.documentType = "Published"
                    elif "type=Nonprecedential+Disposition" in dataString:
                        doc.documentType = "Unpublished"

                    # now that we have the caseNumber and caseNameShort, we can dup check
                    cite, created = hasDuplicate(caseNumber, caseNameShort)

                    # last, save evrything (pdf, citation and document)
                    doc.citation = cite
                    doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                    if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                    try:
                        logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                            ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                    except UnicodeDecodeError:
                        pass
                    doc.save()

                    i += 1
        return

    elif (courtID == 8):
        urls = ("http://www.ca8.uscourts.gov/cgi-bin/new/today2.pl",)
        ct = Court.objects.get(courtUUID = 'ca8')

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

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
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
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
                if documentType == 'U':
                    doc.documentType = 'Unpublished'
                elif documentType == 'P':
                    doc.documentType = 'Published'

                # caseDate is next on the block
                junk = str(aTags[i].next.next.next)
                caseDate = caseDateRegex.search(junk).group(1)
                caseDate = clean_string(caseDate)
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
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 9):
        """This court, by virtue of having a javascript laden website, was very
        hard to parse properly. BeautifulSoup couldn't handle it at all, so lxml
        has to be used."""

        # these URLs redirect now. So much for hacking them. A new approach can probably be done using POST data.
        urls = (
            "http://www.ca9.uscourts.gov/opinions/?o_mode=view&amp;o_sort_field=19&amp;o_sort_type=DESC&o_page_size=100",
            "http://www.ca9.uscourts.gov/memoranda/?o_mode=view&amp;o_sort_field=21&amp;o_sort_type=DESC&o_page_size=100",)

        ct = Court.objects.get(courtUUID = 'ca9')

        for url in urls:
            if VERBOSITY >= 1: print "Scraping URL: " + url
            try: html = readURL(url, courtID)
            except: continue

            tree = fromstring(html)

            if url == urls[0]:
                caseLinks = tree.xpath('//table[3]/tbody/tr/td/a')
                caseNumbers = tree.xpath('//table[3]/tbody/tr/td[2]/label')
                caseDates = tree.xpath('//table[3]/tbody/tr/td[6]/label')
            elif url == urls[1]:
                caseLinks = tree.xpath('//table[3]/tbody/tr/td/a')
                caseNumbers = tree.xpath('//table[3]/tbody/tr/td[2]/label')
                caseDates = tree.xpath('//table[3]/tbody/tr/td[7]/label')

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                # this is necessary because the 9th circuit puts random numbers
                # in their HTML. This gets rid of those, so SHA1 can be generated.
                listofLinks = []
                for i in caseLinks:
                    listofLinks.append(i.get('href'))
                changed = courtChanged(url, str(listofLinks))
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

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
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                # next, we'll do the caseNumber
                caseNumber = caseNumbers[i].text

                # next up: document type (static for now)
                if 'memoranda' in url:
                    doc.documentType = "Unpublished"
                elif 'opinions' in url:
                    doc.documentType = "Published"

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
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 10):
        # a daily feed of all the items posted THAT day. Missing a day == bad.
        urls = ("http://www.ca10.uscourts.gov/opinions/new/daily_decisions.rss",)
        ct = Court.objects.get(courtUUID = 'ca10')

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            # this code gets rid of errant ampersands - they throw big errors
            # when parsing. We replace them later.
            if '&' in html:
                punctuationRegex = re.compile(" & ")
                html = re.sub(punctuationRegex, " &amp; ", html)
                tree = etree.fromstring(html)
            else:
                tree = etree.fromstring(html)

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
                    dupCount += 1

                    '''this section is commented out because ca10 doesn't publish
                    their cases in any order resembling sanity. Thus, this bit
                    of code is moot. Ugh.
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
                        break'''
                    i += 1
                    continue
                else:
                    dupCount = 0

                # next: docType (this order of if statements IS correct)
                docType = docTypes[i].text.strip()
                if "unpublished" in docType.lower():
                    doc.documentType = "Unpublished"
                elif "published" in docType.lower():
                    doc.documentType = "Published"
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
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 11):
        """Prior to rev 313 (2010-04-27), this got published documents only,
        using the court's RSS feed.

        Currently, it uses lxml to parse the HTML on the published and
        unpublished feeds. It can be set to do any date range desired, however
        such modifications should likely go in back_scrape.py."""

        # Missing a day == OK.
        urls = (
            "http://www.ca11.uscourts.gov/unpub/searchdate.php",
            "http://www.ca11.uscourts.gov/opinions/searchdate.php",
        )
        ct = Court.objects.get(courtUUID = 'ca11')

        for url in urls:
            date = time.strftime('%Y-%m', datetime.date.today().timetuple())

            postValues = {
                'date'  : date,
            }

            data = urllib.urlencode(postValues)
            req = urllib2.Request(url, data)
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

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

            return'''

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
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                if 'unpub' in url:
                    doc.documentType = "Unpublished"
                elif 'opinion' in url:
                    doc.documentType = "Published"

                cleanDate = clean_string(caseDates[i].text)
                doc.dateFiled = datetime.datetime(*time.strptime(cleanDate, "%m-%d-%Y")[0:5])

                caseNameShort = caseNames[i].text
                caseNumber = caseNumbers[i].text

                cite, created = hasDuplicate(caseNumber, caseNameShort)

                doc.citation = cite
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 12):
        # A decent RSS feed, created 2011-02-01
        urls = ("http://www.cadc.uscourts.gov/internet/opinions.nsf/uscadcopinions.xml",)
        ct = Court.objects.get(courtUUID = 'cadc')

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            # this code gets rid of errant ampersands - they throw big errors
            # when parsing. We replace them later.
            if '&' in html:
                punctuationRegex = re.compile(" & ")
                html = re.sub(punctuationRegex, " &amp; ", html)
                tree = etree.fromstring(html)
            else:
                tree = etree.fromstring(html)

            caseLinks = tree.xpath("//item/link")
            caseNames = tree.xpath("//item/description")
            caseNums = tree.xpath("//item/title")
            caseDates = tree.xpath("//item/pubDate")

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
                    dupCount += 1

                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                # next: docType (this order of if statements IS correct)
                doc.documentType = "Published"

                # next: caseDate
                caseDateTime = time.strptime(caseDates[i].text[0:-6], "%a, %d %b %Y %H:%M:%S")
                doc.dateFiled = datetime.fromtimestamp(mktime(caseDateTime))

                # next: caseNumber
                caseNumber = caseNums[i].text.split('|')[0].strip()

                # next: caseNameShort
                caseNameShort = caseNames[i].text

                # check for dups, make the object if necessary, otherwise, get it
                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    elif (courtID == 13):
        # today's cases; missing a day not good.
        urls = ("http://www.cafc.uscourts.gov/index.php?option=com_reports&view=report&layout=search&Itemid=12",)
        # for last seven days use:
        #urls = ("http://www.cafc.uscourts.gov/index.php?searchword=&ordering=&date=7&type=&origin=&searchphrase=all&Itemid=12&option=com_reports",)
        ct = Court.objects.get(courtUUID = "cafc")

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            soup = BeautifulSoup(html)

            aTagsRegex = re.compile('pdf$', re.IGNORECASE)
            trTags = soup.findAll('tr')

            # start on the seventh row, since the prior trTags are junk.
            i = 6
            dupCount = 0
            while i <= 50: #stop at 50, if not three dupes first.
                try:
                    caseLink = trTags[i].td.nextSibling.nextSibling.nextSibling\
                        .nextSibling.nextSibling.nextSibling.a.get('href')
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
                    dupCount += 1
                    if dupCount == 5:
                        # fifth duplicate in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                # next: caseNumber
                caseNumber = trTags[i].td.nextSibling.nextSibling.contents[0]

                # next: dateFiled
                dateFiled = trTags[i].td.contents[0].strip()
                splitDate = dateFiled.split("-")
                dateFiled = datetime.date(int(splitDate[0]), int(splitDate[1]),
                    int(splitDate[2]))
                doc.dateFiled = dateFiled

                # next: caseNameShort
                caseNameShort = trTags[i].td.nextSibling.nextSibling.nextSibling\
                    .nextSibling.nextSibling.nextSibling.a.contents[0]\
                    .replace('[MOTION]', '').replace('[ORDER]', '').replace('(RULE 36)', '')\
                    .replace('[ERRATA]', '').replace('[CORRECTED]','')
                caseNameShort = titlecase(caseNameShort.lower())

                # next: documentType
                documentType = trTags[i].td.nextSibling.nextSibling.nextSibling\
                    .nextSibling.nextSibling.nextSibling.nextSibling.nextSibling\
                    .contents[0].strip()
                # normalize the result for our internal purposes...
                if documentType == "Nonprecedential":
                    documentType = "Unpublished"
                elif documentType == "Precedential":
                    documentType = "Published"
                doc.documentType = documentType

                # now that we have the caseNumber and caseNameShort, we can dup check
                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return

    if (courtID == 14):
        # we do SCOTUS
        urls = ("http://www.supremecourt.gov/opinions/slipopinions.aspx",
                "http://www.supremecourt.gov/opinions/in-chambers.aspx",
                "http://www.supremecourt.gov/opinions/relatingtoorders.aspx",)
        ct = Court.objects.get(courtUUID = 'scotus')

        for url in urls:
            if VERBOSITY >= 1: print "Scraping URL: " + url
            try: html = readURL(url, courtID)
            except: continue
            tree = fromstring(html)

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

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                # this is necessary because the SCOTUS puts random numbers
                # in their HTML. This gets rid of those, so SHA1 can be generated.
                listofLinks = []
                for i in caseLinks:
                    listofLinks.append(i.get('href'))
                changed = courtChanged(url, str(listofLinks))
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

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
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
                        break
                    i += 1
                    continue
                else:
                    dupCount = 0

                caseNumber = caseNumbers[i].text

                caseNameShort = caseLinks[i].text

                if 'slipopinion' in url:
                    doc.documentType = "Published"
                elif 'in-chambers' in url:
                    doc.documentType = "In-chambers"
                elif 'relatingtoorders' in url:
                    doc.documentType = "Relating-to"

                try:
                    if '/' in caseDates[i].text:
                        splitDate = caseDates[i].text.split('/')
                    elif '-' in caseDates[i].text:
                        splitDate = caseDates[i].text.split('-')
                    year = int("20" + splitDate[2])
                    caseDate = datetime.date(year, int(splitDate[0]),
                        int(splitDate[1]))
                    doc.dateFiled = caseDate
                except:
                    print "Error obtaining date field for " + caseLink

                # now that we have the caseNumber and caseNameShort, we can dup check
                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                if VERBOSITY >= 1: print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
                    ": Added " + ct.courtShortName + ": " + cite.caseNameShort
                try:
                    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
                        ": Added " + ct.courtShortName + ": " + cite.caseNameShort)
                except UnicodeDecodeError:
                    pass
                doc.save()

                i += 1
        return


def parseCourt(courtID, VERBOSITY):
    '''
    Here, we do the following:
     1. For a given court, find all of its documents
     2. Determine if the document has been parsed already
     3. If it has, punt, if not, open the PDF and parse it.

    returns a string containing the result
    '''
    if VERBOSITY >= 1: print "NOW PARSING COURT: " + str(courtID)

    from threading import Thread

    # get the court IDs from models.py
    courts = []
    for code in PACER_CODES:
        courts.append(code[0])

    # select all documents from this jurisdiction that lack plainText and were
    # downloaded from the court.
    docs = Document.objects.filter(documentPlainText = "",
        court__courtUUID = courts[courtID-1], source="C").order_by('documentUUID')

    numDocs = docs.count()

    # this is a crude way to start threads, but I'm lazy, and two is a good
    # starting point. This essentially starts two threads, each with half of the
    # unparsed PDFs. If the -c 0 flag is used, it's likely for the next court
    # to begin scraping before both of these have finished. This should be OK,
    # but seems noteworthy.
    if numDocs > 0:
        t1 = Thread(target=getDocContent, args=(docs[0:numDocs/2],))
        t2 = Thread(target=getDocContent, args=(docs[numDocs/2:numDocs],))
        t1.start()
        t2.start()
    elif numDocs == 0:
        if VERBOSITY >= 1: print "Nothing to parse for this court."


def main():
    """
    The master function. This will receive arguments from the user, determine
    the actions to take, then hand it off to other functions that will handle the
    nitty-gritty crud.

    If the courtID is 0, then we scrape/parse all courts, one after the next.

    returns a list containing the result
    """

    # this line is used for handling SIGINT, so things can die safely.
    signal.signal(signal.SIGINT, signal_handler)

    usage = "usage: %prog -d | (-c COURTID (-s | -p) [-v {1,2}])"
    parser = OptionParser(usage)
    parser.add_option('-s', '--scrape', action="store_true", dest='scrape',
        default=False, help="Whether to scrape")
    parser.add_option('-p', '--parse', action="store_true", dest='parse',
        default=False, help="Whether to parse")
    parser.add_option('-d', '--daemon', action="store_true", dest='daemonmode',
        default=False, help="Use this flag to turn on daemon mode at a rate of 20 minutes between each scrape")
    parser.add_option('-c', '--court', dest='courtID', metavar="COURTID",
        help="The court to scrape, parse or both")
    parser.add_option('-v', '--verbosity', dest='verbosity', metavar="VERBOSITY",
        help="Display status messages after execution. Higher values print more verbosity.")
    (options, args) = parser.parse_args()
    if options.daemonmode == False and (not options.courtID or (not options.scrape and not options.parse)):
        parser.error("You must specify either daemon mode or a court and whether to scrape and/or parse it.")

    if options.verbosity == '1' or options.verbosity == '2':
        VERBOSITY = options.verbosity

    DAEMONMODE = options.daemonmode

    if not DAEMONMODE:
        # some data validation, for good measure
        try:
            courtID = int(options.courtID)
        except:
            print "Error: court not found"
            raise django.core.exceptions.ObjectDoesNotExist

        if courtID == 0:
            # we use a while loop to do all courts.
            courtID = 1
            from alertSystem.models import PACER_CODES
            while courtID <= len(PACER_CODES):
                if options.scrape: scrapeCourt(courtID, DAEMONMODE, VERBOSITY)
                if options.parse:  parseCourt(courtID, VERBOSITY)
                # this catches SIGINT, so the code can be killed safely.
                if dieNow == True:
                    sys.exit(0)
                courtID += 1
        else:
            # we're only doing one court
            if options.scrape: scrapeCourt(courtID, DAEMONMODE, VERBOSITY)
            if options.parse:  parseCourt(courtID, VERBOSITY)
            # this catches SIGINT, so the code can be killed safely.
            if dieNow == True:
                sys.exit(0)

    elif DAEMONMODE:
        # daemon mode is ON. Iterate over all the courts, with a pause between
        # them that is long enough such that all of them are hit over the course
        # of thirty minutes. When checking a court, see if its HTML has changed.
        # If so, run the scrapers. If not, check the next one.
        VERBOSITY = 0

        from alertSystem.models import PACER_CODES
        wait = (30*60)/len(PACER_CODES)
        courtID = 1
        while courtID <= len(PACER_CODES):
            scrapeCourt(courtID, DAEMONMODE, VERBOSITY)
            parseCourt(courtID, VERBOSITY)
            # this catches SIGINT, so the code can be killed safely.
            if dieNow == True:
                sys.exit(0)

            time.sleep(wait)
            if courtID == len(PACER_CODES):
                # reset courtID
                courtID = 1
            else:
                # increment it
                courtID += 1

    return 0


if __name__ == '__main__':
    main()
