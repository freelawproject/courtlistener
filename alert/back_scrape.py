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

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alertSystem.models import *
from alertSystem.string_utils import *
from scrape_and_parse import getDocContent
from scrape_and_parse import hasDuplicate
from scrape_and_parse import makeDocFromURL
from scrape_and_parse import makeDocError
from scrape_and_parse import parseCourt
from scrape_and_parse import printAndLogNewDoc
from scrape_and_parse import readURL
from django.core.files.base import ContentFile
from django.core.files import File
from django.core.exceptions import ObjectDoesNotExist

import calendar
import datetime
import hashlib
import httplib
import re
import StringIO
import subprocess
import time
import urllib
import urllib2

from BeautifulSoup import BeautifulSoup
from lxml.html import fromstring
from lxml.html import tostring
from lxml import etree
from optparse import OptionParser
from urlparse import urljoin


"""This is where scrapers live that can be trained on historical data with some
tweaking.

These are generally much more hacked than those scrapers in scrape_and_parse.py,
but they should work with some editing or updating."""


def back_scrape_court(courtID, VERBOSITY):
    if (courtID == 1):
        '''
        This scrapes ca1 using an HTTP POST. The data comes back in a nice
        tabular format, so that's easy, but it's paginated 200 per page, so we
        have to iterate over the pages until we get all the results.

        The process is thus to start at 1993/01/01, and do one month increments.

        The court has docs back to 1992, but the first ones lack decent case
        names, so we'll have to get them from resource.org.
        '''
        url = 'http://www.ca1.uscourts.gov/cgi-bin/opinions.pl'
        ct = Court.objects.get(courtUUID = 'ca1')

        # Build an array of every the date every 30 days from 1993-01-01 to today
        hoy = datetime.date.today()
        unixTimeToday = int(time.mktime(hoy.timetuple()))
        dates = []
        i = 0
        while True:
            # This is the start date + 30 days for each value of i.
            # it's expressed in Unixtime, and can be arbitrarily set by running
            # date --date="2010-04-19" +%s in the terminal.

	    # This is the date that was used in the original start date.
            # newDate = 725875200 + (2592000 * i)

	    # This date was used to get things moving after crawler crashes.
	    newDate = 738831600 + (2592000 * i)
            dates.append(datetime.datetime.fromtimestamp(newDate))
            if newDate > unixTimeToday:
                break
            else:
                i += 1

        # next, iterate over these until there are no more!
        i = 0
        while i < (len(dates)-1):
            startDate = time.strftime('%m/%d/%Y', dates[i].timetuple())
            endDate = time.strftime('%m/%d/%Y', dates[i+1].timetuple())
            i += 1

            print "\n\n****Now scraping " + startDate + " to " + endDate + "****"

            postValues = {
                    'OPINNUM'  : '',
                    'CASENUM'  : '',
                    'TITLE'    : '',
                    'FROMDATE' : startDate,
                    'TODATE'   : endDate,
                    'puid'     : '',
                }

            data = urllib.urlencode(postValues)
            req = urllib2.Request(url, data)
            try: html = readURL(req, courtID)
            except: continue

            parser = etree.HTMLParser()
            import StringIO
            tree = etree.parse(StringIO.StringIO(html), parser)

            rows = tree.xpath('//table[2]/tr')

            # Iterate over each row, and pull out the goods, skipping the header row.
            for row in rows[1:]:
                '''
                The next large couple of blocks try to get the file as a PDF.
                Failing that, they try as a WPD. If that fails, they extract
                the text from the webpage.

                After all this mess, we end up with a doc.
                '''

                # Start with the case number
                rowCells = row.findall('.//td')
                caseNumber = rowCells[1].find('./a').text

                # Special cases
                if caseNumber.strip() == '92-2198.01A':
                    continue

                # Case link, if there is a PDF
                caseLink = 'http://www.ca1.uscourts.gov/pdf.opinions/' + caseNumber + '.pdf'
                #print caseLink

                try:
                    # Best case scenario: There's a PDF.
                    myFile, doc, created = makeDocFromURL(caseLink, ct)
                    mimetype = '.pdf'
                except makeDocError as e:
                    if 'DownloadingError' in e.value:
                        # The PDF didn't exist; try the WPD
                        caseLink = 'http://www.ca1.uscourts.gov/wp.opinions/' + caseNumber
                        mimetype = '.wpd'
                        try:
                            myFile, doc, created = makeDocFromURL(caseLink, ct)
                        except makeDocError:
                            # The WPD didn't exist either, grab the text and
                            # clean it up.
                            mimetype = None
                            caseLink = rowCells[1].find('./a').get('href')
                            caseLink = urljoin(url, caseLink)
                            #print "Quick view's case link is: " + caseLink

                            try: quickHtml = readURL(caseLink, courtID)
                            except: continue

                            # This helps out the parser in corner cases.
                            quickHtml = unicode(quickHtml)

                            # Get the useful part of the webpage.
                            quickTree = etree.parse(StringIO.StringIO(quickHtml), parser)

                            documentPlainText = quickTree.find('//pre')

                            # Clean up the text
                            try:
                                documentPlainText = tostring(documentPlainText).replace('<pre>', '').replace('</pre>','')\
                                    .replace('<br>', '\n').replace('_', ' ')
                            except TypeError:
                                continue
                            documentPlainText = anonymize(documentPlainText)
                            documentPlainText = removeDuplicateLines(documentPlainText)
                            documentPlainText = removeLeftMargin(documentPlainText)

                            sha1Hash = hashlib.sha1(documentPlainText).hexdigest()

                            # using that, we check for a dup
                            doc, created = Document.objects.get_or_create(documentSHA1 = sha1Hash,
                                court = ct)

                            if created:
                                # we only do this if it's new
                                doc.documentSHA1 = sha1Hash
                                doc.download_URL = caseLink
                                doc.court = ct
                                doc.source = "C"

                            doc.documentPlainText = documentPlainText

                        except:
                            print "Unanticipated error. Aborting"
                            return 1

                if not created:
                    continue

                # The real case number (the one above is't quite right)
                caseNumber = rowCells[2].find('./a').text

                # Next: Case name.
                caseNameShort = clean_string(rowCells[3].text)
                if caseNameShort == 'v.':
                    caseNameShort = 'Unknown case name'

                # Next: Doctype
                doc.documentType = "Published"
                try:
                    if 'not for publication' in documentPlainText.lower():
                        doc.documentType = "Unpublished"
                except NameError:
                    pass

                # documentPlainText doesn't exist.
                if 'u' in caseNumber.lower():
                    doc.documentType = "Unpublished"
                elif 'e' in caseNumber.lower():
                    doc.documentType = "Errata"
                elif 'p' in caseNumber.lower():
                    doc.documentType = "Published"

                # Next: caseDate
                try:
                    caseDate = rowCells[0].text.strip()
                    splitDate = caseDate.split('/')
                    caseDate = datetime.date(int(splitDate[0]), int(splitDate[1]),
                        int(splitDate[2]))
                except AttributeError:
                    caseDate = None
                doc.dateFiled = caseDate

                # now that we have the caseNumber and caseNameShort, we can dup check
                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (file, citation and document)
                doc.citation = cite
                if mimetype:
                    doc.local_path.save(trunc(clean_string(caseNameShort), 80) + mimetype, myFile)
                printAndLogNewDoc(VERBOSITY, ct, cite)
                doc.save()

        return


    if (courtID == 5):
        """Court is accessible via a HTTP Post, but requires some random fields
        in order to work. The method here, as of 2010/04/27, is to create an
        array of each date every thirty days from the beginning if the court's
        corpus until today, and then to iterate over that array, making an HTTP
        POST for each month."""

        # Build an array of every the date every 30 days from 1992-01-01 to today
        hoy = datetime.date.today()
        unixTimeToday = int(time.mktime(hoy.timetuple()))
        dates = []
        i = 0
        while True:
            # This is the start date + 30 days for each value of i.
            # it's expressed in Unixtime, and can be arbitrarily set by running
            # date --date="2010-04-19" +%s in the terminal.
            newDate = 1202112000 + (2592000 * i)
            dates.append(datetime.datetime.fromtimestamp(newDate))
            if newDate > unixTimeToday:
                break
            else:
                i += 1

        url = "http://www.ca5.uscourts.gov/Opinions.aspx"
        ct = Court.objects.get(courtUUID='ca5')

        if verbosity >= 2: print "dates: " + str(dates)

        # next, iterate over these until there are no more!
        j = 0
        while j < (len(dates)-1):
            startDate = time.strftime('%m/%d/%Y', dates[j].timetuple())
            endDate = time.strftime('%m/%d/%Y', dates[j+1].timetuple())

            if verbosity >= 2:
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
            #if verbosity >= 2: print soup

            #all links ending in pdf, case insensitive
            aTagRegex = re.compile("pdf$", re.IGNORECASE)
            aTags = soup.findAll(attrs={"href": aTagRegex})

            unpubRegex = re.compile(r"pinions.*unpub")

            i = 0
            dupCount = 0
            numP = 0
            numQ = 0
            while i < len(aTags):
                print str(aTags[i])
                # this page has PDFs that aren't cases, we must filter them out
                if 'pinion' not in str(aTags[i]):
                    # it's not an opinion, increment and punt
                    if verbosity >= 2: print "Punting"
                    i += 1
                    continue

                # we begin with the caseLink field
                caseLink = aTags[i].get('href')
                caseLink = urljoin(url, caseLink)

                # next, we do the docStatus field, b/c we need to include it in
                # the dup check.
                if unpubRegex.search(str(aTags[i])) == None:
                    # it's published, else it's unpublished
                    documentType = "Published"
                    numP += 1
                else:
                    documentType = "Unpublished"
                    numQ += 1
                if verbosity >= 2: print documentType
                doc.documentType = documentType


                myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                if error:
                    # things broke, punt this iteration
                    i += 1
                    continue

                if not created:
                    # it's an oldie, punt!
                    if verbosity >= 1:
                        result += "Duplicate found at " + str(i) + "\n"
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
                doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
                doc.save()

                i += 1

        return result

    if courtID == 10:
        '''Functional as of 2010/08/11. This court has a search form, which
        returns ten results at a time. The results are in pretty shabby form,
        hence we request then ONE AT A TIME!

        To re-use this, find the index number on the court website of the
        starting and ending points you want by doing a search for a date
        range, then monitoring the POST values submitted when the next button
        on the results page is pressed.
        '''

        url = "http://www.ca10.uscourts.gov/searchbydateresults.php"
        ct = Court.objects.get(courtUUID = 'ca10')
        not_binding = re.compile('not(\s+)binding(\s+)precedent', re.IGNORECASE)

        i = 0
        dupCount = 0
        while i <= 20000:
            if verbosity >= 2: print "i: " + str(i)
            postValues = {
                'start_index' : i,
                'end_index'   : i
            }

            data = urllib.urlencode(postValues)
            req = urllib2.Request(url, data)
            try: html = urllib2.urlopen(req).read()
            except:
                result += "****ERROR CONNECTING TO COURT: " + str(courtID) + "****\n"
                continue

            tree = fromstring(html)

            # we begin with the caseLink field
            caseLinkElements = tree.xpath('/html/body/table//tr[4]/td/table//td[2]/table/tr[2]/td[2]/a')
            caseLink = caseLinkElements[0].get('href')
            caseLink = urljoin(url, caseLink)
            if verbosity >= 2: print "caseLink: " + caseLink

            myFile, doc, created, error = makeDocFromURL(caseLink, ct)

            # Check for dups or errors
            if error:
                # things broke, punt this iteration
                if verbosity >= 2:
                    print "Error in makeDocFromURL function at: " + str(i)
                i += 1
                continue

            if not created:
                # it's an oldie, punt!
                if verbosity >= 2: print "Duplicate found at " + str(i)
                dupCount += 1
                if dupCount == 10:
                    # third dup in a a row. BREAK!
                    break
                i += 1
                continue
            else:
                dupCount = 0

            # split the URL on /, and get the file name, then split on ., and
            # get the caseNumber
            caseNumber = caseLink.split('/')[5]
            caseNumber = caseNumber.split('.')[0]
            if verbosity >= 2: print "caseNumber: " + caseNumber

            # caseNameShort is up next
            caseNameShort = tostring(caseLinkElements[0]).split('&#160;')[3]
            if verbosity >= 2: print "caseNameShort: " + caseNameShort

            # now that we have the caseNumber and caseNameShort, we can dup check
            cite, created = hasDuplicate(caseNumber, caseNameShort)

            # the first element with the class headline is the caseDate
            caseDate = tree.find_class('headline')[0].text
            splitDate = caseDate.split('/')
            year = int(splitDate[2])
            if year > 80 and year <= 99:
                year = int("19" + splitDate[2])
            elif year >= 2000:
                pass
            elif year < 80 and year >= 0:
                year = int("20" + splitDate[2])
            caseDate = datetime.date(year, int(splitDate[0]), int(splitDate[1]))
            doc.dateFiled = caseDate
            if verbosity >= 2: print "caseDate: " + str(caseDate)

            # save the pdf to disk, link the citation
            doc.citation = cite
            doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)

            # we do the PDF parsing here, because we need to determine if it's
            # a published or unpublished doc.
            if verbosity >= 2: print "Parsing: " + caseNameShort

            path = str(doc.local_path)
            path = settings.MEDIA_ROOT + path

            # do the pdftotext work
            process = subprocess.Popen(
                ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"], shell=False,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            content, err = process.communicate()
            if err: result += "Error parsing file: " + doc.citation.caseNameShort

            # add the anonymized plain text to the DB!
            doc.documentPlainText = anonymize(smart_str(content))

            # determine if it's published or not by checking for the words
            # "not binding precedent" in the first 5000 characters.
            if not_binding.search(doc.documentPlainText[:5000]):
                doc.documentType = "Unpublished"
            else:
                doc.documentType = "Published"
            if verbosity >= 2: print "documentType: " + doc.documentType + "\n"

            doc.save()

            i += 1
        return result


    if courtID == 11:
        """Functional as of 2010/04/27. This court has a URL for its precedential
        and non-precedential cases, so we shall iterate over those. For each URL,
        we build an array of dates that we want to query.

        Dates take the form: 2010-01-01 (all cases for January 1, 2010), 2010-01
        (all cases for January, 2010), 2010 (all dates for 2010 - too slow).
        Months must be prepended with 0, if they are less than ten, so "2010-1"
        will not work. Thus, there is some wonky code.

        For each date in our set, perform an HTTP POST, and crawl the results.
        """

        url = "http://www.ca11.uscourts.gov/rss/pubopnsfeed.php"
        ct = Court.objects.get(courtUUID = 'ca11')

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
                if verbosity >= 2: print "years: " + str(years)
            elif 'opinions' in url:
                i = 0
                years = []
                while i <= 0:
                    j = 3
                    while j <= 12:
                        if j < 10:
                            month = "0" + str(j)
                        else:
                            month = str(j)
                        years.append(str(2010+i) + "-" + month)
                        j += 1
                    i += 1
                if verbosity >= 2: print "years: " + str(years)

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
                        if verbosity >= 1:
                            result += "Duplicate found at " + str(i) + "\n"
                        if verbosity >= 2:
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
                        doc.documentType = "Unpublished"
                    elif 'opinion' in url:
                        doc.documentType = "Published"
                    if verbosity >= 2: print "documentType: " + str(doc.documentType)

                    cleanDate = caseDates[i].text.strip()
                    doc.dateFiled = datetime.datetime(*time.strptime(cleanDate, "%m-%d-%Y")[0:5])
                    if verbosity >= 2: print "dateFiled: " + str(doc.dateFiled)

                    caseNameShort = caseNames[i].text
                    caseNumber = caseNumbers[i].text

                    cite, created = hasDuplicate(caseNumber, caseNameShort)
                    if verbosity >= 2:
                        print "caseNameShort: " + cite.caseNameShort
                        print "caseNumber: " + cite.caseNumber + "\n"

                    doc.citation = cite
                    doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
                    doc.save()

                    i += 1
        return result

    if courtID == 12:
        '''
        cadc - a nice HTML page, with good data. Scraped using lxml, no major
        tricks.
        '''
        VERBOSITY = verbosity
        ct = Court.objects.get(courtUUID = 'cadc')

        months = [ '01', '02', '03', '04', '05', '06', '07', '08', '09', '10',
            '11', '12']
        years = [ '1997', '1998', '1999', '2000', '2001', '2002', '2003', '2004',
            '2005', '2006', '2007', '2008', '2009', '2010']

        for year in years:
            for month in months:
                print "\n\n*****Date is now: " + year + "/" + month + "*****"
                url = "http://www.cadc.uscourts.gov/internet/opinions.nsf/OpinionsByRDate?OpenView&count=100&SKey=" + year + month


                try: html = readURL(url, courtID)
                except: continue

                parser = etree.HTMLParser()
                import StringIO
                tree = etree.parse(StringIO.StringIO(html), parser)

                divs = tree.xpath('//div[@class="row-entry"]')

                dupCount = 0
                for div in divs:
                    # Loop through the divs. If the div has an HTML anchor in column
                    # one, then it's a case number + name in the div. Else, it's a date
                    caseLinkAnchor = div.find('./span[@class="column-one"]/a')
                    if caseLinkAnchor == None:
                        caseLinkAnchor = div.find('./span[@class="column-one texticon"]/a')
                    caseNameDiv = div.find('./span[@class="column-two"]')
                    caseDate = div.find('./span[@class="column-two myDemphasize"]')

                    if caseLinkAnchor != None:
                        # It's a caseLink, caseName row, grab them.
                        caseLink = caseLinkAnchor.get('href')
                        caseLink = urljoin(url, caseLink)
                        #print "Link: " + caseLink

                        caseNumber = caseLinkAnchor.text
                        #print "Case number: " + caseNumber

                        caseNameShort = caseNameDiv.text
                        #print "CaseName: " + caseNameShort
                    else:
                        # No caselink here, find the casedate instead, then do the
                        # rest of the processing. This is ugly code, but it works
                        # b/c the date always comes after the casename and link.
                        caseDate = caseDate.text
                        #print "Date: " + caseDate

                        myFile, doc, created, error = makeDocFromURL(caseLink, ct)

                        if error:
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

                        doc.documentType = "Published"

                        splitDate = caseDate.split('/')
                        caseDate = datetime.date(int(splitDate[2]), int(splitDate[0]),
                            int(splitDate[1]))
                        doc.dateFiled = caseDate

                        # now that we have the caseNumber and caseNameShort, we can dup check
                        cite, created = hasDuplicate(caseNumber, caseNameShort)

                        # last, save evrything (pdf, citation and document)
                        doc.citation = cite
                        mimetype = '.' + caseLink.split('.')[-1]
                        doc.local_path.save(trunc(clean_string(caseNameShort), 80) + mimetype, myFile)
                        printAndLogNewDoc(VERBOSITY, ct, cite)
                        doc.save()

        return

    if courtID == 14:
        """SCOTUS. This code is the same as in the scraper as of today (2010-05-05).
        There is a two year overlap between the resource.org stuff and the stuff
        obtained this way. That two years could be obtained, but for now, I've
        simply closed the gap."""

         # we do SCOTUS
        urls = ("http://www.supremecourt.gov/opinions/slipopinions.aspx?Term=05",
                "http://www.supremecourt.gov/opinions/slipopinions.aspx?Term=06",
                "http://www.supremecourt.gov/opinions/slipopinions.aspx?Term=07",
                "http://www.supremecourt.gov/opinions/slipopinions.aspx?Term=08",
                "http://www.supremecourt.gov/opinions/in-chambers.aspx?Term=05",
                "http://www.supremecourt.gov/opinions/in-chambers.aspx?Term=06",
                "http://www.supremecourt.gov/opinions/in-chambers.aspx?Term=07",
                "http://www.supremecourt.gov/opinions/in-chambers.aspx?Term=08",
                "http://www.supremecourt.gov/opinions/relatingtoorders.aspx?Term=05",
                "http://www.supremecourt.gov/opinions/relatingtoorders.aspx?Term=06",
                "http://www.supremecourt.gov/opinions/relatingtoorders.aspx?Term=07",
                "http://www.supremecourt.gov/opinions/relatingtoorders.aspx?Term=08",)
        ct = Court.objects.get(courtUUID = 'scotus')

        for url in urls:
            if verbosity >= 2: print "Now scraping: " + url
            html = urllib2.urlopen(url).read()
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

            i = 0
            dupCount = 0
            while i < len(caseLinks):
                if 'slipopinion' in url and "Term=05" in url and i == 76:
                    # dups could begin here.
                    break
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
                    if verbosity >= 1:
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
                    doc.documentType = "Published"
                elif 'in-chambers' in url:
                    doc.documentType = "In-chambers"
                elif 'relatingtoorders' in url:
                    doc.documentType = "Relating-to"

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

                if verbosity >= 2:
                    print "Link: " + caseLink
                    print "Doc Status: " + doc.documentType
                    print "Case Name: " + caseNameShort
                    print "Case number: " + caseNumber
                    print "Date filed: " + str(caseDate)
                    print " "

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(caseNameShort, 80) + ".pdf", myFile)
                doc.save()

                i += 1
        return result

    if courtID == '14v545':
        """This scraper uses the internet archives copy of the supreme court site
        to pull in all the documents from volume 545 of United States Reports.
        Amazingly, resource.org simply lacks this volume."""
        httplib.HTTPConnection.debuglevel = 1
        urls = ('http://web.archive.org/web/20051222044311/www.supremecourtus.gov/opinions/04slipopinion.html',)
        ct = Court.objects.get(courtUUID = 'scotus')

        for url in urls:
            if verbosity >= 2: print "Now scraping: " + url
            data = urllib2.urlopen(url).read()

            # this decompresses the data, since IA is annoying about sending compressed data no matter what.
            import StringIO
            data = StringIO.StringIO(data)
            import gzip
            gzipper = gzip.GzipFile(fileobj=data)
            html = gzipper.read()
            tree = fromstring(html)

            # xpath goodness
            caseLinks   = tree.xpath('/html//table[2]//tr/td[4]/a')
            caseNumbers = tree.xpath('/html//table[2]//tr/td[3]')
            caseDates   = tree.xpath('/html//table[2]//tr/td[2]')


            # for debugging
            """print "length: " + str(len(caseLinks))
            print str(caseLinks)
            print str(caseNumbers)
            print str(caseDates)
            i = 2
            while i <= (28):
                print str(caseDates[i].text) + "  |  " + str(caseNumbers[i].text)   + "  |  " + str(urljoin(url, caseLinks[i].get('href'))) + "  |  " + str(caseLinks[i].text)
                i = i + 1
                #print str(foo.text)
                #print foo.get('href')
                #print tostring(foo)

            """

            i = 2
            while i <= 28: #cut this off at the end of v545
                # we begin with the caseLink field
                caseLink = caseLinks[i].get('href')
                caseLink = urljoin(url, caseLink)

                # set some easy ones
                caseNumber = caseNumbers[i].text
                caseNameShort = caseLinks[i].text

                # get the PDF
                try:
                    request = urllib2.Request("http://web.archive.org/web/20051222044311/" + caseLink)
                    request.add_header('User-agent', 'Mozilla/5.0(Windows; U; Windows NT 5.2; rv:1.9.2) Gecko/20100101 Firefox/3.6')
                    h = urllib2.HTTPHandler(debuglevel=1)
                    opener = urllib2.build_opener(h)
                    webFile = opener.open(request).read()
                    stringThing = StringIO.StringIO()
                    stringThing.write(webFile)
                    myFile = ContentFile(stringThing.getvalue())
                    """
                    webFile = urllib2.urlopen(caseLink)
                    stringThing = StringIO.StringIO()
                    stringThing.write(webFile.read())
                    myFile = ContentFile(stringThing.getvalue())
                    webFile.close()"""

                except:
                    print "ERROR DOWNLOADING FILE!: " + str(caseNameShort) + "\n\n"
                    i += 1
                    continue

                # make the SHA1
                data = myFile.read()
                sha1Hash = hashlib.sha1(data).hexdigest()

                # using that, we check for a dup
                doc, created = Document.objects.get_or_create(documentSHA1 = sha1Hash,
                    court = ct)

                if created:
                    # we only do this if it's new
                    doc.documentSHA1 = sha1Hash
                    doc.download_URL = caseLink
                    doc.court = ct
                    doc.source = "A"
                    doc.documentType = "Published"

                if not created:
                    # it's an oldie, punt!
                    if verbosity >= 1:
                        result += "Duplicate found at " + str(i) + "\n"
                    i += 1
                    continue

                if '/' in caseDates[i].text:
                    splitDate = caseDates[i].text.split('/')
                year = int("20" + splitDate[2])
                caseDate = datetime.date(year, int(splitDate[0]),
                    int(splitDate[1]))
                doc.dateFiled = caseDate

                # now that we have the caseNumber and caseNameShort, we can dup check
                cite, created = hasDuplicate(caseNumber, caseNameShort)

                # last, save evrything (pdf, citation and document)
                doc.citation = cite
                doc.local_path.save(trunc(clean_string(caseNameShort), 80) + ".pdf", myFile)
                doc.save()

                i += 1

        return result


def main():
    """
    The master function. This will receive arguments from the user, determine
    the actions to take, then hand it off to other functions that will handle the
    nitty-gritty crud.

    If the courtID is 0, then we scrape/parse all courts, one after the next.

    returns a list containing the result
    """

    usage = "usage: %prog -c COURTID (-s | -p) [-v {1,2}]"
    parser = OptionParser(usage)
    parser.add_option('-s', '--scrape', action="store_true", dest='scrape',
        default=False, help="Whether to scrape")
    parser.add_option('-p', '--parse', action="store_true", dest='parse',
        default=False, help="Whether to parse")
    parser.add_option('-c', '--court', dest='courtID', metavar="COURTID",
        help="The court to scrape, parse or both")
    parser.add_option('-v', '--verbosity', dest='verbosity', metavar="VERBOSITY",
        help="Display status messages after execution. Higher values are more verbosity.")
    (options, args) = parser.parse_args()
    if not options.courtID or (not options.scrape and not options.parse):
        parser.error("You must specify a court and whether to scrape and/or parse it")

    try:
        courtID = int(options.courtID)
    except:
        print "Error: court not found"
        raise django.core.exceptions.ObjectDoesNotExist


    if options.verbosity:
        verbosity = options.verbosity
    else:
        verbosity = '0'

    if courtID == 0:
        # we use a while loop to do all courts.
        courtID = 1
        from alertSystem.models import PACER_CODES
        while courtID <= len(PACER_CODES):
            if options.scrape: back_scrape_court(courtID, verbosity)
            if options.parse:  parseCourt(courtID, verbosity)
            courtID += 1
    else:
        # we're only doing one court
        if options.scrape: back_scrape_court(courtID, verbosity)
        if options.parse:  parseCourt(courtID, verbosity)

    return 0


if __name__ == '__main__':
    main()
