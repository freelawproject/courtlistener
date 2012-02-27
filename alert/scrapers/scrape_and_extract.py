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

import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.search.models import Court
from alert.lib.string_utils import clean_string
from alert.lib.string_utils import titlecase
from alert.lib.scrape_tools import courtChanged
from alert.lib.scrape_tools import makeDocError
from alert.lib.scrape_tools import makeDocFromURL
from alert.lib.scrape_tools import readURL
from alert.lib.scrape_tools import save_all

from django.core.exceptions import ObjectDoesNotExist
from juriscraper.opinions.united_states.federal import *

import datetime
import re
import signal
import time
import traceback
import urllib
import urllib2

from BeautifulSoup import BeautifulSoup
from lxml.html import fromstring
from lxml import etree
from optparse import OptionParser
from StringIO import StringIO
from time import mktime
from urlparse import urljoin

# for use in catching the SIGINT (Ctrl+C)
die_now = False

def signal_handler(signal, frame):
    print 'Exiting safely...this will finish the current court, then exit...'
    global die_now
    die_now = True

def scrape_court(court, verbosity):
    try:
        site = court.Site().parse()
    except:
        #TODO: Print stack trace here.
        pass

    # "Transactionally" save the values to the DB



def scrapeCourt(courtID, DAEMONMODE, VERBOSITY):
    if VERBOSITY >= 1: print "NOW SCRAPING COURT: " + str(courtID)

    if (courtID == 'ca1'):
        # PDFs are available from the first circuit if you go to their RSS feed.
        # So go to their RSS feed we shall.

        urls = ("http://www.ca1.uscourts.gov/opinions/opinionrss.php",)
        ct = Court.objects.get(courtUUID=courtID)

        for url in urls:
            try: html = readURL(url, courtID)
            except:
                continue

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
            docketNumberRegex = re.compile("(\d{2}-.*?\W)(.*)$")

            # incredibly, this RSS feed is in cron order, so new stuff is at the
            # end. Mind blowing.
            i = len(caseLinks) - 1

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
                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # next: docketNumber
                docketNumber = docketNumberRegex.search(caseNamesAndNumbers[i].text)\
                    .group(1)

                # next: caseNameShort
                caseNameShort = docketNumberRegex.search(caseNamesAndNumbers[i].text)\
                    .group(2)

                # last, save everything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i -= 1
        return

    elif (courtID == 'ca2'):
        #  URL hacking FTW.

        # Note that for some reason, setting the IW_DATABASE to Both makes the
        # display fail. Oh well.
        urls = (
            "http://www.ca2.uscourts.gov/decisions?IW_DATABASE=OPN&IW_FIELD_TEXT=*&IW_SORT=-Date&IW_BATCHSIZE=100",
            "http://www.ca2.uscourts.gov/decisions?IW_DATABASE=SUM&IW_FIELD_TEXT=*&IW_SORT=-Date&IW_BATCHSIZE=100",
        )
        ct = Court.objects.get(courtUUID=courtID)

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            soup = BeautifulSoup(html)

            aTagsRegex = re.compile('(.*?.pdf).*?', re.IGNORECASE)
            docketNumRegex = re.compile('.*/(\d{1,2}-\d{1,4})(.*).pdf')
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
                        docketNumbers = docketNumRegex.search(caseLink).group(1)
                    except:
                        docketNumbers = ""
                    aTagsEncoded.append(docketNumbers)

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

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # using caseLink, we can get the docketNumber and documentType
                docketNumber = docketNumRegex.search(caseLink).group(1)

                # and the docType
                documentType = docketNumRegex.search(caseLink).group(2)
                if 'opn' in documentType:
                    # it's unpublished
                    doc.documentType = "Published"
                elif 'so' in documentType:
                    doc.documentType = "Unpublished"

                # next, the caseNameShort (there's probably a better way to do this).
                caseNameShort = aTags[i].parent.parent.nextSibling.nextSibling\
                    .nextSibling.nextSibling.contents[0]

                # next, we can do the caseDate
                caseDate = aTags[i].parent.parent.nextSibling.nextSibling\
                    .nextSibling.nextSibling.nextSibling.nextSibling.contents[0]\
                    .replace('&nbsp;', ' ').strip()

                # some caseDate cleanup
                splitDate = caseDate.split('-')
                caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate

                # last, save everything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'ca3'):
        #  This URL provides the latest 25 cases, so I need to pick out the new
        # ones and only get those. I can do this efficiently by trying to do each,
        # and then giving up once I hit one that I've done before. This will work
        # because they are in reverse chronological order.        

        # if these URLs change, the docType identification (below) will need
        # to be updated. It's lazy, but effective.
        urls = (
            "http://www.ca3.uscourts.gov/recentop/week/recprec.htm",
            "http://www.ca3.uscourts.gov/recentop/week/recnonprec.htm",
            )
        ct = Court.objects.get(courtUUID=courtID)

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

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # caseDate and docketNumber
                junk = aTags[i].previous.previous.previous
                try:
                    # this error seems to happen upon dups...not sure why yet
                    caseDate = regexII.search(junk).group(0)
                    docketNumber = regexIII.search(junk).group(0)
                except:
                    i += 1
                    continue

                # next up is the caseDate
                splitDate = caseDate.split('/')
                caseDate = datetime.date(int("20" + splitDate[2]), int(splitDate[0]),
                    int(splitDate[1])) # ack y2k1c bug!
                doc.dateFiled = caseDate

                # Make a decision about the docType.
                if "recprec.htm" in str(url):
                    doc.documentType = "Published"
                elif "recnonprec.htm" in str(url):
                    doc.documentType = "Unpublished"

                # last, save everything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'ca4'):
        # The fourth circuit is THE worst form of HTML I've ever seen. It's
        # going to break a lot, but I've done my best to clean it up, and make it
        # reliable.

        urls = ("http://pacer.ca4.uscourts.gov/opinions_today.htm",)
        ct = Court.objects.get(courtUUID=courtID)

        for url in urls:
            try: html = readURL(url, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            # sadly, beautifulsoup chokes on the lines of this file because
            # the HTML is so bad. To make it work, we must pull out the target
            # attributes. And so we do.
            regex = re.compile("target.*>", re.IGNORECASE)
            html = re.sub(regex, ">", html)

            soup = BeautifulSoup(html)

            # all links ending in pdf, case insensitive
            regex = re.compile("pdf$", re.IGNORECASE)
            aTags = soup.findAll(attrs={"href": regex})
            if VERBOSITY >= 3: print aTags

            i = 0
            dupCount = 0
            regexII = re.compile('\d{2}/\d{2}/\d{4}')
            # finds the case name in a string of the following format:
            # USA v Holder (per curium DATE)
            regexIII = re.compile('(.*)\(', re.MULTILINE)
            while i < len(aTags):
                # caseLink field, and save it
                caseLink = aTags[i].get('href')
                caseLink = urljoin(url, caseLink)

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # using caselink, we can get the docketNumber and documentType
                fileName = caseLink.split('/')[-1]
                docketNumber, documentType = fileName.split('.')[0:2]
                # the docketNumber needs a hyphen inserted after the second digit
                docketNumber = docketNumber[0:2] + "-" + docketNumber[2:]
                if VERBOSITY >= 2:
                    print "Case number: %s" % docketNumber

                if documentType == 'U':
                    doc.documentType = 'Unpublished'
                elif documentType == 'P':
                    doc.documentType = 'Published'
                else:
                    doc.documentType = ""
                if VERBOSITY >= 2:
                    print "Precedential status: %s" % doc.documentType

                # next, we do the caseDate and caseNameShort, so we can quit before
                # we get too far along.
                junk = aTags[i].contents[0].replace('&nbsp;', ' ').strip()
                if VERBOSITY >= 3:
                    print "junk: " + str(junk)
                try:
                    # this error seems to happen upon dups...not sure why yet
                    caseDate = clean_string(regexII.search(junk).group(0))
                    caseNameShort = regexIII.search(junk).group(1)
                except AttributeError:
                    print "****Unable to get casename or caseDate at ca4****"
                    i += 1
                    continue
                if VERBOSITY >= 2: print "Case name: %s" % caseNameShort

                # some caseDate cleanup
                splitDate = caseDate.split('/')
                caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate
                if VERBOSITY >= 2: print "Date filed: %s" % doc.dateFiled

                # last, save everything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'ca5'):
        # New fifth circuit scraper, which can get back versions all the way to
        # 1992!

        # This is exciting, but be warned, the search is not reliable on recent
        # dates. It has been known not to bring back results that are definitely
        # within the set. Watch closely.

        urls = ("http://www.ca5.uscourts.gov/Opinions.aspx",)
        ct = Court.objects.get(courtUUID=courtID)

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
            try:
                html = readURL(req, courtID)
            except:
                continue

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
                if VERBOSITY >= 2:
                    print "Case link: %s" % caseLink

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # using caseLink, we can get the docketNumber and documentType
                docketNumber = aTags[i].contents[0]

                # next, we do the caseDate
                caseDate = aTags[i].next.next.contents[0].contents[0]

                # some caseDate cleanup
                splitDate = caseDate.split('/')
                caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate

                # next, we do the caseNameShort
                caseNameShort = aTags[i].next.next.next.next.next.contents[0]\
                    .contents[0]

                # last, save everything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'ca6'):
        # Results are available without an HTML POST, but those results lack a
        # date field. Hence, we must do an HTML POST.

        # Missing a day == OK. Just need to monkey with the date POSTed.

        urls = ("http://www.ca6.uscourts.gov/cgi-bin/opinions.pl",)
        ct = Court.objects.get(courtUUID=courtID)

        for url in urls:
            today = datetime.date.today()
            formattedToday = str(today.month) + '/' + str(today.day) + '/' + \
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
            try: html = readURL(req, courtID)
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

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # using caseLink, we can get the docketNumber and documentType
                docketNumber = aTags[i].next.next.next.next.next.contents[0]

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
                caseDate = datetime.date(int(splitDate[0]), int(splitDate[1]),
                    int(splitDate[2]))
                doc.dateFiled = caseDate

                # next, the caseNameShort (there's probably a better way to do this.
                caseNameShort = aTags[i].next.next.next.next.next.next.next.next\
                    .next.next.next

                # last, save everything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'ca7'):
        # another court where we need to do a post. This will be a good
        # starting place for getting the judge field, when we're ready for that.

        # Missing a day == OK. Queries return cases for the past week.

        urls = ("http://www.ca7.uscourts.gov/fdocs/docs.fwx",)
        ct = Court.objects.get(courtUUID=courtID)

        for url in urls:
            # if these strings change, check that documentType still gets set correctly.
            dataStrings = ("yr=&num=&Submit=Past+Week&dtype=Opinion&scrid=Select+a+Case",
                "yr=&num=&Submit=Past+Week&dtype=Nonprecedential+Disposition&scrid=Select+a+Case",)

            for dataString in dataStrings:
                req = urllib2.Request(url, dataString)
                try: html = readURL(req, courtID)
                except: continue

                if DAEMONMODE:
                    # if it's DAEMONMODE, see if the court has changed
                    changed = courtChanged(url + dataString, html)
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

                    try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                    except makeDocError:
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

                    # using caseLink, we can get the docketNumber and documentType
                    docketNumber = aTags[i].previous.previous.previous.previous.previous\
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

                    # last, save everything (pdf, citation and document)
                    save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                    i += 1
        return

    elif (courtID == 'ca8'):
        # Has a search interface that can be hacked with POST data, but the
        # HTML returned from it is an utter wasteland consisting of nothing but
        # <br>, <b> and text. So we can't really use it.

        # Instead, we would turn to the RSS feed, but it's the same sad story.

        # So we go to the one page that has any semantic markup.

        # Missing a day == bad.

        urls = ("http://www.ca8.uscourts.gov/cgi-bin/new/today2.pl",)
        ct = Court.objects.get(courtUUID=courtID)

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

            docketNumRegex = re.compile('(\d{2})(\d{4})(u|p)', re.IGNORECASE)
            caseDateRegex = re.compile('(\d{2}/\d{2}/\d{4})(.*)(</b>)')

            i = 0
            dupCount = 0
            while i < len(aTags):
                # we begin with the caseLink field
                caseLink = aTags[i].get('href')
                caseLink = urljoin(url, caseLink)

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # using caseLink, we can get the docketNumber and documentType
                junk = aTags[i].contents[0]
                docketNumber = docketNumRegex.search(junk).group(1) + "-" + \
                    docketNumRegex.search(junk).group(2)

                documentType = docketNumRegex.search(junk).group(3).upper()
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
                caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate

                # last, save evrything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'ca9'):
        # This court, by virtue of having a javascript laden website, was very
        # hard to parse properly. BeautifulSoup couldn't handle it at all, so lxml
        # has to be used.

        # these URLs redirect now. So much for hacking them. A new approach can probably be done using POST data.
        # If these URLs are changed, code below must be changed for the doc type and dateFiled fields
        urls = (
            "http://www.ca9.uscourts.gov/opinions/?o_mode=view&amp;o_sort_field=19&amp;o_sort_type=DESC&o_page_size=100",
            "http://www.ca9.uscourts.gov/memoranda/?o_mode=view&amp;o_sort_field=21&amp;o_sort_type=DESC&o_page_size=100",
            )

        ct = Court.objects.get(courtUUID=courtID)

        for url in urls:
            if VERBOSITY >= 1: print "Scraping URL: " + url
            try: html = readURL(url, courtID)
            except: continue

            parser = etree.HTMLParser()
            tree = etree.parse(StringIO(html), parser)

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the links in the court have changed.
                # This is necessary because the 9th circuit puts random numbers
                # in their HTML. This gets rid of those, so SHA1 can be generated.
                caseLinks = tree.xpath('//table[3]/tbody/tr/td/a')
                listofLinks = []
                for i in caseLinks:
                    listofLinks.append(i.get('href'))
                changed = courtChanged(url, str(listofLinks))
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            # Get all the rows in the main table so that this is row centric.
            # This fixes off-by-one problems if cells are empty.
            rows = tree.xpath('//table[3]/tbody/tr')

            # for each row in the table, skipping the first, parse the cells
            dupCount = 0
            for row in rows[1:]:
                # Find all the table cells in this row.
                tableCells = row.findall('.//td')

                # Next: caseLink
                caseLink = tableCells[0].find('./a').get('href')
                caseLink = urljoin(url, caseLink)

                #next up: caseNameShort
                caseNameShort = titlecase(tableCells[0].find('./a').text)

                # special cases
                noMemos = 'no memos filed' in caseLink.lower()
                noOpinions = 'no opinions filed' in caseLink.lower()
                if noMemos or noOpinions:
                    continue

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
                    continue

                if not created:
                    # it's an oldie, punt!
                    dupCount += 1
                    if dupCount == 5:
                        # fifth dup in a a row. BREAK!
                        break
                    continue
                else:
                    dupCount = 0

                # Next: docketNumber
                docketNumber = tableCells[1].find('./label').text

                # Next: document type (static for now)
                if 'opinions' in url:
                    doc.documentType = "Published"
                elif 'memoranda' in url:
                    doc.documentType = "Unpublished"

                # Next: caseDate
                try:
                    if 'opinions' in url:
                        caseDate = tableCells[5].find('./label').text
                    elif 'memoranda' in url:
                        caseDate = tableCells[6].find('./label').text
                    splitDate = caseDate.split('/')
                    caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                        int(splitDate[1]))
                except AttributeError:
                    caseDate = None
                doc.dateFiled = caseDate

                # last, save evrything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

        return

    elif (courtID == 'ca10'):
        # a daily feed of all the items posted THAT day. Missing a day == bad.
        urls = ("http://www.ca10.uscourts.gov/opinions/new/daily_decisions.rss",)
        ct = Court.objects.get(courtUUID=courtID)

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
            docketNumberRegex = re.compile("(\d{2}-\d{4})(.*)$")

            i = 0
            dupCount = 0
            while i < len(caseLinks):
                # we begin with the caseLink field
                caseLink = caseLinks[i].text
                caseLink = urljoin(url, caseLink)

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # next: docketNumber
                docketNumber = docketNumberRegex.search(descriptions[i].text)\
                    .group(1)

                # next: caseNameShort
                caseNameShort = caseNames[i].text

                # last, save everything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'ca11'):
        # Prior to rev 313 (2010-04-27), this got published documents only,
        # using the court's RSS feed.

        # Currently, it uses lxml to parse the HTML on the published and
        # unpublished feeds. It can be set to do any date range desired, however
        # such modifications should likely go in back_scrape.py.

        # Missing a day == OK.
        urls = (
            "http://www.ca11.uscourts.gov/unpub/searchdate.php",
            "http://www.ca11.uscourts.gov/opinions/searchdate.php",
        )
        ct = Court.objects.get(courtUUID=courtID)

        for url in urls:
            date = time.strftime('%Y-%m', datetime.date.today().timetuple())

            postValues = {
                'date'  : date,
            }

            data = urllib.urlencode(postValues)
            req = urllib2.Request(url, data)
            try: html = readURL(req, courtID)
            except: continue

            if DAEMONMODE:
                # if it's DAEMONMODE, see if the court has changed
                changed = courtChanged(url, html)
                if not changed:
                    # if not, bail. If so, continue to the scraping.
                    return

            tree = fromstring(html)

            if 'unpub' in url:
                docketNumbers = tree.xpath('//table[3]//table//table/tr[1]/td[2]')
                caseLinks = tree.xpath('//table[3]//table//table/tr[3]/td[2]/a')
                caseDates = tree.xpath('//table[3]//table//table/tr[4]/td[2]')
                caseNames = tree.xpath('//table[3]//table//table/tr[6]/td[2]')
            elif 'opinion' in url:
                docketNumbers = tree.xpath('//table[3]//td[3]//table/tr[1]/td[2]')
                caseLinks = tree.xpath('//table[3]//td[3]//table/tr[3]/td[2]/a')
                caseDates = tree.xpath('//table[3]//td[3]//table/tr[4]/td[2]')
                caseNames = tree.xpath('//table[3]//td[3]//table/tr[6]/td[2]')

            '''
            # for debugging
            print "length: " + str(len(caseNames))
            for foo in caseNames:
                print str(foo.text)

            return'''

            i = 0
            dupCount = 0
            while i < len(docketNumbers):
                caseLink = caseLinks[i].get('href')
                caseLink = urljoin(url, caseLink)

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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
                docketNumber = docketNumbers[i].text

                # Save everything
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'cadc'):
        # A decent RSS feed, created 2011-02-01
        urls = ("http://www.cadc.uscourts.gov/internet/opinions.nsf/uscadcopinions.xml",)
        ct = Court.objects.get(courtUUID=courtID)

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
            docketNums = tree.xpath("//item/title")
            caseDates = tree.xpath("//item/pubDate")

            i = 0
            dupCount = 0
            while i < len(caseLinks):
                # we begin with the caseLink field
                caseLink = caseLinks[i].text
                caseLink = urljoin(url, caseLink)

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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
                doc.dateFiled = datetime.datetime.fromtimestamp(mktime(caseDateTime))

                # next: docketNumber
                docketNumber = docketNums[i].text.split('|')[0].strip()

                # next: caseNameShort
                caseNameShort = caseNames[i].text

                # last, save everything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    elif (courtID == 'cafc'):
        # for last seven days use:
        urls = ("http://www.cafc.uscourts.gov/index.php?searchword=&ordering=&date=7&type=&origin=&searchphrase=all&Itemid=12&option=com_reports",)
        ct = Court.objects.get(courtUUID=courtID)

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

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                # next: docketNumber
                docketNumber = trTags[i].td.nextSibling.nextSibling.contents[0]

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
                    .replace('[ERRATA]', '').replace('[CORRECTED]', '').replace('[ORDER 2]', '')\
                    .replace('[ORDER}', '').replace('[ERRATA 2]', '')
                caseNameShort = titlecase(caseNameShort)

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

                # last, save evrything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return

    if (courtID == 'scotus'):
        urls = ("http://www.supremecourt.gov/opinions/slipopinions.aspx",
                "http://www.supremecourt.gov/opinions/in-chambers.aspx",
                "http://www.supremecourt.gov/opinions/relatingtoorders.aspx",)
        ct = Court.objects.get(courtUUID=courtID)

        for url in urls:
            if VERBOSITY >= 1: print "Scraping URL: " + url
            try: html = readURL(url, courtID)
            except: continue
            tree = fromstring(html)

            if 'slipopinion' in url:
                caseLinks = tree.xpath('//table/tr/td[4]/a')
                docketNumbers = tree.xpath('//table/tr/td[3]')
                caseDates = tree.xpath('//table/tr/td[2]')
            elif 'in-chambers' in url:
                caseLinks = tree.xpath('//table/tr/td[3]/a')
                docketNumbers = tree.xpath('//table/tr/td[2]')
                caseDates = tree.xpath('//table/tr/td[1]')
            elif 'relatingtoorders' in url:
                caseLinks = tree.xpath('//table/tr/td[3]/a')
                docketNumbers = tree.xpath('//table/tr/td[2]')
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

                try: myFile, doc, created = makeDocFromURL(caseLink, ct)
                except makeDocError:
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

                docketNumber = docketNumbers[i].text

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

                # last, save evrything (pdf, citation and document)
                save_all(doc, ct, myFile, caseNameShort, docketNumber, VERBOSITY)

                i += 1
        return


def main():
    global die_now

    # this line is used for handling SIGINT, so things can die safely.
    signal.signal(signal.SIGQUIT, signal_handler)

    usage = 'usage: %prog -c COURTID [-d] [-r RATE] [-v {1,2}]'
    parser = OptionParser(usage)
    parser.add_option('-d', '--daemon', action="store_true", dest='daemonmode',
                      default=False, help=('Use this flag to turn on daemon '
                                           'mode, in which all courts will be '
                                           'sraped in turn, non-stop.'))
    parser.add_option('-r', '--rate', dest='rate', metavar='RATE',
                      help=('The length of time in minutes it takes to crawl all '
                            'known courts. Particularly useful if it is desired '
                            'to quickly scrape over all courts. Default is 30 '
                            'minutes.'))
    parser.add_option('-c', '--courts', dest='court_id', metavar="COURTID",
                      help=('The court(s) to scrape and extract. This should be in '
                            'the form of a python module or package import '
                            'from the Juriscraper library, e.g. '
                            '"opinions.united_states.federal.ca1" or '
                            'simply "opinions" to do everything.'))
    parser.add_option('-v', '--verbosity', dest='verbosity', metavar="VERBOSITY",
                      help=('Display status messages during execution. Higher '
                            'values print more verbosity.'))
    (options, args) = parser.parse_args()

    daemon_mode = options.daemonmode
    court_id = options.court_id

    if not court_id:
        parser.error('You must specify a court as a package or module.')
    else:
        try:
            import court_id
        except ImportError:
            parser.error('Unable to import court module or package.')

    try:
        verbosity = int(options.verbosity)
    except ValueError, AttributeError:
        verbosity = 0

    try:
        rate = int(options.rate)
    except ValueError, AttributeError:
        rate = 30
    num_courts = len(court_id.__all__)
    wait = (rate * 60) / num_courts
    i = 0
    while i >= num_courts:
        scrape_court(court_id.__all__[i], verbosity)
        # this catches SIGINT, so the code can be killed safely.
        if die_now == True:
            sys.exit(0)

        time.sleep(wait)
        if i == num_courts and daemon_mode:
            i = 0
        else:
            i += 1
    return 0

if __name__ == '__main__':
    main()
