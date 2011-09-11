#!/usr/bin/env python

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

import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import sys
# append these to the path to make the dev machines and the server happy (respectively)
sys.path.append("/var/www/court-listener")

from django import db
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.template.defaultfilters import slugify
from django.utils.encoding import smart_str, smart_unicode
from alert.alertSystem.models import Court, Citation, Document
from alert.lib.parse_dates import parse_dates
from alert.lib.encode_decode import num_to_ascii
from alert.lib.string_utils import clean_string, harmonize, titlecase, trunc
from alert.lib.scrape_tools import hasDuplicate
from dup_finder import check_dup

from lxml.html import fromstring, tostring
from urlparse import urljoin
import datetime
import re
import subprocess
import time
import urllib2

# Set to False to disable automatic browser usage. Else, set to the
# command you want to run, e.g. 'firefox'
BROWSER = False
SIMULATE = True


def load_fix_files():
    '''Loads the fix files into memory so they can be accessed efficiently.'''
    court_fix_file = open('../logs/f3_court_fix_file.txt', 'r')
    date_fix_file  = open('../logs/f3_date_fix_file.txt', 'r')
    case_name_short_fix_file = open('../logs/f3_short_case_name_fix_file.txt', 'r')
    court_fix_dict = {}
    date_fix_dict = {}
    case_name_short_dict = {}
    for line in court_fix_file:
        key, value = line.split('|')
        court_fix_dict[key] = value
    for line in date_fix_file:
        key, value = line.split('|')
        date_fix_dict[key] = value
    for line in case_name_short_fix_file:
        key, value = line.split('|')
        case_name_short_dict[key] = value

    court_fix_file.close()
    date_fix_file.close()
    case_name_short_fix_file.close()
    return court_fix_dict, date_fix_dict, case_name_short_dict


def check_fix_list(sha1, fix_dict):
    '''Given a sha1, return the correction for a case. Return false if no values.

    Corrections are strings that the parser can interpret as needed. Items are
    written to this file the first time the cases are imported, and this file
    can be used to import F2 into later systems.
    '''
    try:
        return fix_dict[sha1].strip()
    except KeyError:
        return False


def unpublished_cleaner(caseName):
    '''Cleans common Resource.org special cases off of case names, and
    sets the documentType for a document.

    Returns caseName, documentType
    '''
    caseName = caseName.lower()
    ca1regex = re.compile('(unpublished disposition )?notice: first circuit local rule 36.2\(b\)6 states unpublished opinions may be cited only in related cases.?')
    ca2regex = re.compile('(unpublished disposition )?notice: second circuit local rule 0.23 states unreported opinions shall not be cited or otherwise used in unrelated cases.?')
    ca2regex2 = re.compile('(unpublished disposition )?notice: this summary order may not be cited as precedential authority, but may be called to the attention of the court in a subsequent stage of this case, in a related case, or in any case for purposes of collateral estoppel or res judicata. see second circuit rule 0.23.?')
    ca3regex = re.compile('(unpublished disposition )?notice: third circuit rule 21\(i\) states citations to federal decisions which have not been formally reported should identify the court, docket number and date.?')
    ca4regex = re.compile('(unpublished disposition )?notice: fourth circuit (local rule 36\(c\)|i.o.p. 36.6) states that citation of unpublished dispositions is disfavored except for establishing res judicata, estoppel, or the law of the case and requires service of copies of cited unpublished dispositions of the fourth circuit.?')
    ca5regex = re.compile('(unpublished disposition )?notice: fifth circuit local rule 47.5.3 states that unpublished opinions should normally be cited only when they establish the law of the case, are relied upon as a basis for res judicata or collateral estoppel, or involve related facts. if an unpublished opinion is cited, a copy shall be attached to each copy of the brief.?')
    ca6regex = re.compile('(unpublished disposition )?notice: sixth circuit rule 24\(c\) states that citation of unpublished dispositions is disfavored except for establishing res judicata, estoppel, or the law of the case and requires service of copies of cited unpublished dispositions of the sixth circuit.?')
    ca7regex = re.compile('(unpublished disposition )?notice: seventh circuit rule 53\(b\)\(2\) states unpublished orders shall not be cited or used as precedent except to support a claim of res judicata, collateral estoppel or law of the case in any federal court within the circuit.?')
    ca8regex = re.compile('(unpublished disposition )?notice: eighth circuit rule 28a\(k\) governs citation of unpublished opinions and provides that (no party may cite an opinion not intended for publication unless the cases are related by identity between the parties or the causes of action|they are not precedent and generally should not be cited unless relevant to establishing the doctrines of res judicata, collateral estoppel, the law of the case, or if the opinion has persuasive value on a material issue and no published opinion would serve as well).?')
    ca9regex = re.compile('(unpublished disposition )?notice: ninth circuit rule 36-3 provides that dispositions other than opinions or orders designated for publication are not precedential and should not be cited except when relevant under the doctrines of law of the case, res judicata, or collateral estoppel.?')
    ca10regex = re.compile('(unpublished disposition )?notice: tenth circuit rule 36.3 states that unpublished opinions and orders and judgments have no precedential value and shall not be cited except for purposes of establishing the doctrines of the law of the case, res judicata, or collateral estoppel.?')
    cadcregex = re.compile('(unpublished disposition )?notice: d.c. circuit local rule 11\(c\) states that unpublished orders, judgments, and explanatory memoranda may not be cited as precedents, but counsel may refer to unpublished dispositions when the binding or preclusive effect of the disposition, rather than its quality as precedent, is relevant.?')
    cafcregex = re.compile('(unpublished disposition )?notice: federal circuit local rule 47.(6|8)\(b\) states that opinions and orders which are designated as not citable as precedent shall not be employed or cited as precedent. this does not preclude assertion of issues of claim preclusion, issue preclusion, judicial estoppel, law of the case or the like based on a decision of the court rendered in a nonprecedential opinion or order.?')
    # Clean off special cases
    if 'first circuit' in caseName:
        caseName = re.sub(ca1regex, '', caseName)
        documentType = 'Unpublished'
    elif 'second circuit' in caseName:
        caseName = re.sub(ca2regex, '', caseName)
        caseName = re.sub(ca2regex2, '', caseName)
        documentType = 'Unpublished'
    elif 'third circuit' in caseName:
        caseName = re.sub(ca3regex, '', caseName)
        documentType = 'Unpublished'
    elif 'fourth circuit' in caseName:
        caseName = re.sub(ca4regex, '', caseName)
        documentType = 'Unpublished'
    elif 'fifth circuit' in caseName:
        caseName = re.sub(ca5regex, '', caseName)
        documentType = 'Unpublished'
    elif 'sixth circuit' in caseName:
        caseName = re.sub(ca6regex, '', caseName)
        documentType = 'Unpublished'
    elif 'seventh circuit' in caseName:
        caseName = re.sub(ca7regex, '', caseName)
        documentType = 'Unpublished'
    elif 'eighth circuit' in caseName:
        caseName = re.sub(ca8regex, '', caseName)
        documentType = 'Unpublished'
    elif 'ninth circuit' in caseName:
        caseName = re.sub(ca9regex, '', caseName)
        documentType = 'Unpublished'
    elif 'tenth circuit' in caseName:
        caseName = re.sub(ca10regex, '', caseName)
        documentType = 'Unpublished'
    elif 'd.c. circuit' in caseName:
        caseName = re.sub(cadcregex, '', caseName)
        documentType = 'Unpublished'
    elif 'federal circuit' in caseName:
        caseName = re.sub(cafcregex, '', caseName)
        documentType = 'Unpublished'
    else:
        documentType = 'Published'

    return caseName, documentType


def write_dups(source, dups, DEBUG=False):
    '''Writes duplicates to a file so they are logged.

    This function recieves a queryset and then writes out the values to a log.
    '''
    log = open('../logs/dup_log.txt', 'a')
    if dups[0] != None:
        log.write(source)
        print "Logging match: " + source,
        for dup in dups:
            # write out each doc
            log.write('|' + str(dup.pk) + " - " + num_to_ascii(dup.pk))
            if DEBUG:
                print '|' + str(dup.pk) + ' - ' + num_to_ascii(dup.pk),
    else:
        log.write("%s" % source)
        if DEBUG:
            print "No dups found for %s" % source,
    print ""
    log.write('\n')
    log.close()


def need_dup_check_in_date_and_court(dateFiled, court):
    '''Checks whether a case needs duplicate checking.

    Performs a simple check for whether we have scraped any documents for the
    date and court specified, using known dates of when scraping started at a
    court.

    The following MySQL is from the server, and indicates the earliest scraped
    documents in each court:

        mysql> select court_id, min(dateFiled)
               from Document
               where source = 'C'
               group by court_id;
        +----------+----------------+
        | court_id | min(dateFiled) |
        +----------+----------------+
        | ca1      | 1993-01-05     |
        | ca10     | 1995-09-01     |
        | ca11     | 1994-12-09     |
        | ca2      | 2003-04-08     |
        | ca3      | 2009-07-02     |
        | ca4      | 2010-03-12     |
        | ca5      | 1992-05-14     |
        | ca6      | 2010-03-15     |
        | ca7      | 2010-03-12     |
        | ca8      | 2010-03-12     |
        | ca9      | 2010-03-10     |
        | cadc     | 1997-09-12     |
        | cafc     | 2004-11-30     |
        | scotus   | 2005-10-07     |
        +----------+----------------+
        14 rows in set (51.65 sec)

    We'll ues these values to filter out cases that can't possibly have a dup.

    Returns True if a duplicate check should be run. Else: False.
    '''

    earliest_dates = {
        'ca1': datetime.datetime(1993, 1, 5),
        'ca2': datetime.datetime(2003, 4, 8),
        'ca3': datetime.datetime(2009, 7, 2),
        'ca4': datetime.datetime(2010, 3, 12),
        'ca5': datetime.datetime(1992, 5, 14),
        'ca6': datetime.datetime(2010, 3, 15),
        'ca7': datetime.datetime(2010, 3, 12),
        'ca8': datetime.datetime(2010, 3, 12),
        'ca9': datetime.datetime(2010, 3, 10),
        'ca10': datetime.datetime(1995, 9, 1),
        'ca11': datetime.datetime(1994, 12, 9),
        'cadc': datetime.datetime(1997, 9, 12),
        'cafc': datetime.datetime(2004, 11, 30),
        'scotus': datetime.datetime(1600, 1, 1),
        }
    try:
        if dateFiled <= earliest_dates[court.pk]:
            # Doc was filed before court was scraped. No need for check.
            return False
        else:
            # Doc was filed after court was scraped. Need dup check. Alas.
            return True
    except KeyError:
        # The court was never scraped - thus we get an exception. No need for
        # check.
        return False


def scrape_and_parse():
    '''Traverses the dumps from resource.org, and puts them in the DB.

    Probably lots of ways to go about this, but I think the easiest will be the following:
     - look at the index page of all volumes, and follow all the links it has.
     - for each volume, look at its index page, and follow the link to all cases
     - for each case, collect information wisely.
     - put it all in the DB
    '''

    # begin by loading up the fix files into memory
    court_fix_dict, date_fix_dict, case_name_short_dict = load_fix_files()

    results = []
    DEBUG = 4
    court_fix_file = open('../logs/f3_court_fix_file.txt', 'a')
    date_fix_file = open('../logs/f3_date_fix_file.txt', 'a')
    case_name_short_fix_file = open('../logs/f3_short_case_name_fix_file.txt', 'a')
    vol_file = open('../logs/vol_file.txt', 'r+')
    case_file = open('../logs/case_file.txt', 'r+')

    url = "file:///var/www/court-listener/Resource.org/data/F3/index.html"
    openedURL = urllib2.urlopen(url)
    content = openedURL.read()
    openedURL.close()
    tree = fromstring(content)

    volumeLinks = tree.xpath('//table/tbody/tr/td[1]/a')

    try:
        i = int(vol_file.readline())
    except ValueError:
        # the volume file is emtpy or otherwise failing.
        i = 0
    vol_file.close()

    if DEBUG >= 1:
        print "Number of remaining volumes is: %d" % (len(volumeLinks)-i)

    # used later, needs a default value.
    saved_caseDate = None
    saved_court = None
    while i < len(volumeLinks):
        # we iterate over every case in the volume
        volumeURL = volumeLinks[i].text + "/index.html"
        volumeURL = urljoin(url, volumeURL)
        if DEBUG >= 1:
            print "Current volumeURL is: %s" % volumeURL

        openedVolumeURL = urllib2.urlopen(volumeURL)
        content = openedVolumeURL.read()
        volumeTree = fromstring(content)
        openedVolumeURL.close()
        caseLinks  = volumeTree.xpath('//table/tbody/tr/td[1]/a')
        caseDates  = volumeTree.xpath('//table/tbody/tr/td[2]')
        sha1Hashes = volumeTree.xpath('//table/tbody/tr/td[3]/a')

        # The following loads a serialized placeholder from disk.
        try:
            j = int(case_file.readline())
        except ValueError:
            j = 0
        case_file.close()
        while j < len(caseLinks):
            # iterate over each case, throwing it in the DB
            if DEBUG >= 1:
                print ''

            ############
            ### SHA1 ###
            ############
            sha1Hash = sha1Hashes[j].text
            if DEBUG >= 4:
                print "SHA1 is: %s" % sha1Hash


            ################
            ### caseLink ###
            ################
            caseLink = caseLinks[j].get('href')
            absCaseLink = urljoin(volumeURL, caseLink)


            ####################
            ### download_URL ###
            ####################
            download_URL = "http://bulk.resource.org/courts.gov/c/F3/" \
                + str(i+1) + "/" + caseLink


            ############
            ### HTML ###
            ############
            html = urllib2.urlopen(absCaseLink).read()
            htmlTree = fromstring(html)
            bodyContents = htmlTree.xpath('//body/*[not(@id="footer")]')

            body = ""
            bodyText = ""
            for element in bodyContents:
                body += tostring(element)
                try:
                    bodyText += tostring(element, method='text')
                except UnicodeEncodeError:
                    # Happens with odd characters. Simply pass this iteration.
                    pass
            if DEBUG >= 5:
                print body
                print bodyText


            ##############
            ### Court ####
            ##############
            try:
                courtPs = htmlTree.xpath('//p[@class = "court"]')
                # Often the court ends up in the parties field.
                partiesPs = htmlTree.xpath("//p[@class= 'parties']")
                court = ""
                for courtP in courtPs:
                    court += tostring(courtP).lower()
                for party in partiesPs:
                    court += tostring(party).lower()
            except IndexError:
                court = check_fix_list(sha1Hash, court_fix_dict)
                if not court:
                    print absCaseLink
                    if BROWSER:
                        subprocess.Popen([BROWSER, absCaseLink], shell=False).communicate()
                    court = raw_input("Please input court name (e.g. \"First Circuit of Appeals\"): ").lower()
                    court_fix_file.write("%s|%s\n" % (sha1Hash, court))
            if ('first' in court) or ('ca1' == court):
                court = 'ca1'
            elif ('second' in court) or ('ca2' == court):
                court = 'ca2'
            elif ('third' in court) or ('ca3' == court):
                court = 'ca3'
            elif ('fourth' in court) or ('ca4' == court):
                court = 'ca4'
            elif ('fifth' in court) or ('ca5' == court):
                court = 'ca5'
            elif ('sixth' in court) or ('ca6' == court):
                court = 'ca6'
            elif ('seventh' in court) or ('ca7' == court):
                court = 'ca7'
            elif ('eighth' in court) or ('ca8' == court):
                court = 'ca8'
            elif ('ninth' in court) or ('ca9' == court):
                court = 'ca9'
            elif ("tenth" in court) or ('ca10' == court):
                court = 'ca10'
            elif ("eleventh" in court) or ('ca11' == court):
                court = 'ca11'
            elif ('columbia' in court) or ('cadc' == court):
                court = 'cadc'
            elif ('federal' in court) or ('cafc' == court):
                court = 'cafc'
            elif ('patent' in court) or ('ccpa' == court):
                court = 'ccpa'
            elif (('emergency' in court) and ('temporary' not in court)) or ('eca' == court):
                court = 'eca'
            elif ('claims' in court) or ('cfc' == court):
                court = 'cfc'
            else:
                # No luck extracting the court name. Try the fix file.
                court = check_fix_list(sha1Hash, court_fix_dict)
                if not court:
                    # Not yet in the fix file. Check if it's a crazy ca5 case
                    court = ''
                    ca5courtPs = htmlTree.xpath('//p[@class = "center"]')
                    for ca5courtP in ca5courtPs:
                        court += tostring(ca5courtP).lower()
                    if 'fifth circuit' in court:
                        court = 'ca5'
                    else:
                        court = False

                    if not court:
                        # Still no luck. Ask for input, then append it to
                        # the fix file.
                        print absCaseLink
                        if BROWSER:
                            subprocess.Popen([BROWSER, absCaseLink], shell=False).communicate()
                        court = raw_input("Unknown court. Input the court code to proceed successfully [%s]: " % saved_court)
                        court = court or saved_court
                    court_fix_file.write("%s|%s\n" % (sha1Hash, court))

            saved_court = court
            court = Court.objects.get(courtUUID = court)
            if DEBUG >= 4:
                print "Court is: %s" % court


            ##################
            ### dateFiled ####
            ##################
            # http://pleac.sourceforge.net/pleac_python/datesandtimes.html
            rawDate = caseDates[j].find('a')
            try:
                if rawDate != None:
                    date_text = rawDate.text
                    try:
                        caseDate = datetime.datetime(*time.strptime(date_text, "%B, %Y")[0:5])
                    except ValueError, TypeError:
                        caseDate = datetime.datetime(*time.strptime(date_text, "%B %d, %Y")[0:5])
                else:
                    # No value was found. Throw an exception.
                    raise ValueError
            except:
                # No date provided.
                try:
                    # Try to get it from the saved list
                    caseDate = datetime.datetime(*time.strptime(check_fix_list(sha1Hash, date_fix_dict), "%B %d, %Y")[0:5])
                except:
                    caseDate = False
                if not caseDate:
                    # Parse out the dates with debug set to false.
                    try:
                        dates = parse_dates(bodyText, False)
                    except OverflowError:
                        # Happens when we try to make a date from a very large number
                        dates = []
                    try:
                        first_date_found = dates[0]
                    except IndexError:
                        # No dates found.
                        first_date_found = False
                    if first_date_found == saved_caseDate:
                        # High likelihood of date being correct. Use it.
                        caseDate = saved_caseDate
                    else:
                        print absCaseLink
                        if BROWSER:
                            subprocess.Popen([BROWSER, absCaseLink], shell=False).communicate()
                        print "Unknown date. Possible options are:"
                        try:
                            print "  1) %s" % saved_caseDate.strftime("%B %d, %Y")
                        except AttributeError:
                            # Happens on first iteration when saved_caseDate has no strftime attribute.
                            try:
                                saved_caseDate = dates[0]
                                print "  1) %s" % saved_caseDate.strftime("%B %d, %Y")
                            except IndexError:
                                # Happens when dates has no values.
                                print "  No options available."
                        for k, date in enumerate(dates[0:4]):
                            if date.year >= 1900:
                                # strftime can't handle dates before 1900.
                                print "  %s) %s" % (k + 2, date.strftime("%B %d, %Y"))
                        choice = raw_input("Enter the date or an option to proceed [1]: ")
                        choice = choice or 1
                        if str(choice) == '1':
                            # The user chose the default. Use the saved value from the last case
                            caseDate = saved_caseDate
                        elif choice in ['2','3','4','5']:
                            # The user chose an option between 2 and 5. Use it.
                            caseDate = dates[int(choice) - 2]
                        else:
                            # The user typed a new date. Use it.
                            caseDate = datetime.datetime(*time.strptime(choice, "%B %d, %Y")[0:5])
                    date_fix_file.write("%s|%s\n" % (sha1Hash, caseDate.strftime("%B %d, %Y")))

            # Used during the next iteration as the default value
            saved_caseDate = caseDate

            if DEBUG >= 3:
                print "caseDate is: %s" % (caseDate)


            ############################################
            ### westCite, docketNumber and CaseName ####
            ############################################
            # Full casename is gotten later.
            westCite = caseLinks[j].text
            docketNumber = absCaseLink.split('.')[-2]
            caseName = caseLinks[j].get('title')

            # data cleanup.
            caseName, documentType = unpublished_cleaner(caseName)
            caseName = titlecase(harmonize(clean_string(caseName)))

            if caseName == '' or caseName == 'unpublished disposition':
                # No luck getting the case name
                savedCaseNameShort = check_fix_list(sha1Hash, case_name_short_dict)
                if not savedCaseNameShort:
                    print absCaseLink
                    if BROWSER:
                        subprocess.Popen([BROWSER, absCaseLink], shell=False).communicate()
                    caseName = raw_input("Short casename: ")
                    case_name_short_fix_file.write("%s|%s\n" % (sha1Hash, caseName))
                else:
                    # We got both the values from the save files. Use 'em.
                    caseName = savedCaseNameShort

            if DEBUG >= 4:
                print "documentType: " + documentType
                print "westCite: " + westCite
                print "docketNumber: " + docketNumber
                print "caseName: " + caseName


            ##########################
            ### Duplicate checking ###
            ##########################
            if need_dup_check_in_date_and_court(caseDate, court):
                print "Running complex dup check."
                # There exist scraped cases in this court and date.
                # Strip HTML.
                entities = re.compile(r'&(([a-z]{1,5})|(#\d{1,4}));')
                content = entities.sub('', body)
                br = re.compile(r'<br/?>')
                content = br.sub(' ', content)
                p = re.compile(r'<.*?>')
                content = p.sub('', content)
                dups = check_dup(court.pk, caseDate, caseName, content, docketNumber, sha1Hash, DEBUG=True)
                if len(dups) == 0:
                    # No dups found. Move on.
                    pass
                elif len(dups) == 1:
                    # Duplicate found.
                    write_dups(sha1Hash, dups, DEBUG=True)
                elif len(dups) > 1:
                    # Multiple dups found. Seek human review.
                    write_dups(sha1Hash, dups, DEBUG=True)
            else:
                print "No complex check needed."

            if not SIMULATE:
                cite, new = hasDuplicate(caseName, westCite, docketNumber)


            #################################
            ### Document saving routines ####
            #################################
            if not SIMULATE:
                try:
                    doc, created = Document.objects.get_or_create(
                        documentSHA1 = sha1Hash, court = court)
                except MultipleObjectsReturned:
                    # this shouldn't happen now that we're using SHA1 as the dup
                    # check, but the old data is problematic, so we must catch this.
                    created = False

                if created:
                    # we only do this if it's new
                    doc.documentHTML = body
                    doc.documentSHA1 = sha1Hash
                    doc.download_URL = download_URL
                    doc.dateFiled = caseDate
                    doc.source = "R"

                    doc.documentType = documentType
                    doc.citation = cite
                    doc.save()

                if not created:
                    # This happens if we have a match on the sha1, which really
                    # shouldn't happen, since F3 sha's come from the text, and ours
                    # come from the binary.
                    print "Duplicate found at volume " + str(i+1) + \
                        " and row " + str(j+1) + "!!!!"
                    print "Found document %s in the database with doc id of %d!" % (doc, doc.documentUUID)
                    exit(1)

            # save our location within the volume.
            j += 1
            case_file = open('../logs/case_file.txt', 'w')
            case_file.write(str(j))
            case_file.close()

        # save the last volume completed.
        i += 1
        vol_file = open('../logs/vol_file.txt', 'w')
        vol_file.write(str(i))
        vol_file.close()

        # Clear query cache, as it presents a memory leak
        db.reset_queries()

    return 0

def main():
    print scrape_and_parse()
    print "Completed all volumes successfully. Exiting."
    exit(0)


if __name__ == '__main__':
    main()
