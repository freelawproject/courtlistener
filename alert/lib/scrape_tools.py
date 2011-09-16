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
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.

import sys
sys.path.append('/var/www/court-listener/alert')

from alert import settings
from django.core.management import setup_environ
setup_environ(settings)

from alertSystem.models import *
from lib.string_utils import *

from django.core.files.base import ContentFile

import hashlib
import logging.handlers
import StringIO
import subprocess
import time
import traceback
import urllib2


LOG_FILENAME = '/var/log/scraper/daemon_log.out'

# Set up a specific logger with our desired output level
logger = logging.getLogger('Logger')
logger.setLevel(logging.DEBUG)

# Add the log message handler to the logger
handler = logging.handlers.RotatingFileHandler(
              LOG_FILENAME, maxBytes = 5120000, backupCount = 1)

logger.addHandler(handler)


class makeDocError(Exception):
    '''
    This is a simple class for errors stemming from the makeDocFromURL function.
    It doesn't do much except to make the code a little cleaner and more precise.
    '''
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


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
        print "****ERROR CONNECTING TO COURT: " + str(courtID) + "****"
        print 'Generic Exception: ' + traceback.format_exc()
    return html


def printAndLogNewDoc(VERBOSITY, ct, cite):
    '''
    Simply prints the log message and then logs it.
    '''
    caseName = smart_unicode(str(cite), errors = 'ignore')
    if (cite.westCite != '') and (cite.westCite != None):
        caseNum = cite.westCite
    elif (cite.lexisCite != '') and (cite.lexisCite != None):
        caseNum = cite.lexisCite
    elif (cite.docketNumber != '') and (cite.docketNumber != None):
        caseNum = cite.docketNumber

    if VERBOSITY >= 1:
        print time.strftime("%a, %d %b %Y %H:%M", time.localtime()) + \
            ": Added " + ct.shortName + ": " + caseName + \
            ", " + str(caseNum)
    logger.debug(time.strftime("%a, %d %b %Y %H:%M", time.localtime()) +
        ": Added " + ct.shortName + ": " + caseName + \
        ", " + str(caseNum))


def makeDocFromURL(LinkToDoc, ct):
    '''
    Receives a URL and a court as arguments, then downloads the Doc
    that's in it, and makes it into a StringIO. Generates a sha1 hash of the
    file, and tries to add it to the db. If it's a duplicate, it gets the one in
    the DB. If it's a new sha1, it creates a new document.

    returns a StringIO of the PDF, a Document object, and a boolean indicating
    whether the Document was created
    '''

    # Percent encode URLs if necessary.
    LinkToDoc = urllib2.quote(LinkToDoc, safe = "%/:=&?~#+!$,;'@()*[]")

    # get the Doc
    try:
        webFile = urllib2.urlopen(LinkToDoc)
        stringThing = StringIO.StringIO()
        stringThing.write(webFile.read())
        myFile = ContentFile(stringThing.getvalue())
        webFile.close()
    except:
        err = 'DownloadingError: ' + str(LinkToDoc)
        print traceback.format_exc()
        raise makeDocError(err)

    # make the SHA1
    data = myFile.read()

    # test for empty files (thank you CA1)
    if len(data) == 0:
        err = "EmptyFileError: " + str(LinkToDoc)
        print traceback.format_exc()
        raise makeDocError(err)

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

    return myFile, doc, created


def courtChanged(url, contents):
    '''
    Takes HTML contents from a court download, generates a SHA1, and then
    compares that hash to a value in the DB, if there is one. If there is a value
    and it is the same, it returns False. Else, it returns True.
    '''
    sha1Hash = hashlib.sha1(contents).hexdigest()
    url2Hash, created = urlToHash.objects.get_or_create(url = url)

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


def hasDuplicate(caseName, westCite = None, docketNumber = None):
    '''Determines if the case name and number are already in the DB.

    Takes either a caseName, a westCite or a docketNumber or both, and checks
    if the citation already exists in the database. If it exists, the citation
    is returned. If not, then a citation is created and returned.

    In no case will an existing citation get updated with additional information
    that it previously lacked. For example, if docketNumber and westCitation
    are provided, and there is a citation with one but not the other, that
    citation will not be updated. Instead a new citation will be created, since
    West citations are not unique, and neither are docket numbers.
    '''

    # data cleanup
    caseName = titlecase(harmonize(clean_string(caseName)))
    if westCite:
        westCite = clean_string(westCite)
    if docketNumber:
        docketNumber = clean_string(docketNumber)

    caseNameShort = trunc(caseName, 100)

    if westCite and docketNumber:
        # We have both the west citation and the docket number
        cite, created = Citation.objects.get_or_create(
            caseNameShort = str(caseNameShort), westCite = str(westCite),
            docketNumber = str(docketNumber))
    elif westCite and not docketNumber:
        # Only the west citation was provided.
        cite, created = Citation.objects.get_or_create(
            caseNameShort = str(caseNameShort), westCite = str(westCite))
    elif docketNumber and not westCite:
        # Only the docketNumber was provided.
        cite, created = Citation.objects.get_or_create(
            caseNameShort = str(caseNameShort), docketNumber = str(docketNumber))

    cite.caseNameFull = caseName

    cite.save()

    return cite, created


def getDocContent(docs):
    '''
    Get the contents of a list of files, and add them to the DB, sniffing
    their mimetype.
    '''
    for doc in docs:
        path = str(doc.local_path)
        path = settings.MEDIA_ROOT + path

        mimetype = path.split('.')[-1]
        if mimetype == 'pdf':
            # do the pdftotext work for PDFs
            process = subprocess.Popen(["pdftotext", "-layout", "-enc", "UTF-8",
                path, "-"], shell = False, stdout = subprocess.PIPE,
                stderr = subprocess.STDOUT)
            content, err = process.communicate()
            if content == '':
                # probably an image PDF.
                content = "Unable to parse document content."
            doc.documentPlainText = anonymize(content)
            if err:
                print "****Error extracting PDF text from: " + doc.citation.caseNameShort + "****"
                continue
        elif mimetype == 'txt':
            # read the contents of text files.
            try:
                content = open(path).read()
                doc.documentPlainText = anonymize(content)
            except:
                print "****Error extracting plain text from: " + doc.citation.caseNameShort + "****"
                continue
        elif mimetype == 'wpd':
            # It's a Word Perfect file. Use the wpd2html converter, clean up
            # the HTML and save the content to the HTML field.
            print "Parsing: " + path
            process = subprocess.Popen(['wpd2html', path, '-'], shell = False,
                stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
            content, err = process.communicate()

            parser = etree.HTMLParser()
            import StringIO
            tree = etree.parse(StringIO.StringIO(content), parser)
            body = tree.xpath('//body')
            content = tostring(body[0]).replace('<body>', '').replace('</body>', '')

            fontsizeReg = re.compile('font-size: .*;')
            content = re.sub(fontsizeReg, '', content)

            colorReg = re.compile('color: .*;')
            content = re.sub(colorReg, '', content)

            if 'not for publication' in content.lower():
                doc.documentType = "Unpublished"
            doc.documentHTML = anonymize(content)

            if err:
                print "****Error extracting WPD text from: " + doc.citation.caseNameShort + "****"
                continue
        elif mimetype == 'doc':
            # read the contents of MS Doc files
            print "Parsing: " + path
            process = subprocess.Popen(['antiword', path, '-i', '1'], shell = False,
                stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
            content, err = process.communicate()
            doc.documentPlainText = anonymize(content)
            if err:
                print "****Error extracting DOC text from: " + doc.citation.caseNameShort + "****"
                continue
        else:
            print "*****Unknown mimetype: " + mimetype + ". Unable to parse: " + doc.citation.caseNameShort + "****"
            continue

        try:
            doc.save()
        except Exception, e:
            print "****Error saving text to the db for: " + doc.citation.caseNameShort + "****"


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
    docs = Document.objects.filter(documentPlainText = "", documentHTML = "",
        court__courtUUID = courts[courtID - 1], source = "C").order_by('documentUUID')

    numDocs = docs.count()

    # this is a crude way to start threads, but I'm lazy, and two is a good
    # starting point. This essentially starts two threads, each with half of the
    # unparsed PDFs. If the -c 0 flag is used, it's likely for the next court
    # to begin scraping before both of these have finished. This should be OK,
    # but seems noteworthy.
    if numDocs > 0:
        t1 = Thread(target = getDocContent, args = (docs[0:numDocs / 2],))
        t2 = Thread(target = getDocContent, args = (docs[numDocs / 2:numDocs],))
        t1.start()
        t2.start()
    elif numDocs == 0:
        if VERBOSITY >= 1: print "Nothing to parse for this court."
