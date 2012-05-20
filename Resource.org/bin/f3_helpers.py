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

from juriscraper.lib.parse_dates import parse_dates
from alert.lib.string_utils import anonymize
from alert.search.models import Citation, Court, Document
from juriscraper.lib.string_utils import clean_string, harmonize, titlecase

import datetime
import re
import subprocess
import time
import urllib2

from lxml.html import fromstring, tostring
from urlparse import urljoin


BROWSER = 'firefox'

def add_case(case):
    '''Add the case to the database.
    
    '''
    simulate = False
    # Get the court
    court = Court.objects.get(courtUUID=case.court)

    # Make a citation
    cite = Citation(case_name=case.case_name,
                    docketNumber=case.docket_number,
                    westCite=case.west_cite)

    # Make the document object
    doc = Document(source='R',
                   documentSHA1=case.sha1_hash,
                   dateFiled=case.case_date,
                   court=court,
                   download_URL=case.download_url,
                   documentType=case.precedential_status)

    doc.documentHTML, blocked = anonymize(case.body)
    if blocked:
        doc.blocked = True
        doc.date_blocked = datetime.date.today()

    if not simulate:
        # Save everything together
        cite.save()
        doc.citation = cite
        doc.save()

def merge_cases_simple(case, target_id):
    '''Add `case` to the database, merging with target_id
     
     Merging is done along the following algorithm:
     - SHA1 is preserved from CL
     - The HTML from PRO gets added to CL's DB.
     - CL's title is preserved (it tends to be better)
     - The source field for the document is changed to CR (court and PRO)
     - The west citation is added to CL's DB from PRO
     - Block status is determined according to the indexing pipeline    
    '''
    simulate = False
    doc = Document.objects.get(documentUUID=target_id)
    print "Merging %s with" % case.case_name
    print "        %s" % doc.citation.case_name

    doc.source = 'CR'
    doc.citation.westCite = case.west_cite
    doc.documentHTML, blocked = anonymize(case.body)
    if blocked:
        doc.blocked = True
        doc.date_blocked = datetime.date.today()

    if not simulate:
        doc.citation.save()
        doc.save()

def merge_cases_complex(case, target_ids):
    '''Merge data from PRO with multiple cases that seem to be a match.
    
    The process here is a conservative one. We take *only* the information
    from PRO that is not already in CL in any form, and add only that.
    '''
    for target_id in target_ids:
        simulate = False
        doc = Document.objects.get(documentUUID=target_id)
        print "Merging %s with" % case.case_name
        print "        %s" % doc.citation.case_name

        doc.source = 'CR'
        doc.citation.westCite = case.west_cite

        if not simulate:
            doc.citation.save()
            doc.save()

def find_same_docket_numbers(case, candidates):
    '''Identify the candidates that have the same docket numbers as the case.
    
    '''
    new_docket_number = case.docket_number
    same_docket_numbers = []
    for candidate in candidates:
        if candidate['docketNumber'] == new_docket_number:
            same_docket_numbers.append(candidate)
    return same_docket_numbers

def filter_by_stats(candidates, stats):
    '''Looks at the candidates and their stats, and filters out obviously 
    different candidates.
    '''
    filtered_stats = stats[0:2]
    filtered_stats.append([])
    filtered_stats.append([])
    filtered_stats.append([])
    filtered_candidates = []
    for i in range(0, len(candidates)):
        if stats[2][i] < 0.125:
            # The case name is wildly different
            continue
        elif stats[3][i] > 400:
            # The documents have wildly different lengths
            continue
        elif stats[4][i] < 0.4:
            # The contents are wildly different
            continue
        else:
            # It's a reasonably close match.
            filtered_stats[2].append(stats[2][i])
            filtered_stats[3].append(stats[3][i])
            filtered_stats[4].append(stats[4][i])
            filtered_candidates.append(candidates[i])
    return filtered_candidates, filtered_stats

def need_dup_check_for_date_and_court(case):
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

    We'll use these values to filter out cases that can't possibly have a dup.

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
        if case.case_date <= earliest_dates[case.court]:
            # Doc was filed before court was scraped. No need for check.
            return False
        else:
            # Doc was filed after court was scraped. Need dup check. Alas.
            return True
    except KeyError:
        # The court was never scraped - thus we get an exception. No need for
        # check.
        return False


class Case(object):
    '''Represents a case within Resource.org'''
    def __init__(self, base_url, url_element, case_date, sha1_hash):
        print "Making a case object"
        super(Case, self).__init__()
        # Non-core data attributes
        self.url_element = url_element
        self.tree = fromstring(urllib2.urlopen(urljoin(base_url, url_element.get('href'))).read())
        self.court_fix_dict = self._load_fix_file('../logs/f3_court_fix_file.txt')
        self.date_fix_dict = self._load_fix_file('../logs/f3_date_fix_file.txt')
        self.case_name_dict = self._load_fix_file('../logs/f3_short_case_name_fix_file.txt')
        self.court_fix_file = open('../logs/f3_court_fix_file.txt', 'a')
        self.date_fix_file = open('../logs/f3_date_fix_file.txt', 'a')
        self.case_name_fix_file = open('../logs/f3_short_case_name_fix_file.txt', 'a')
        self.saved_court = ''

        # Core data attributes
        self.url = self._get_url(base_url)
        self.sha1_hash = sha1_hash
        self.download_url = self._get_download_url()
        self.body, self.body_text = self._get_case_body()
        self.court = self._get_court()
        self.case_date = self._get_case_date(case_date)
        self.west_cite = self._get_west_cite()
        self.docket_number = self._get_docket_number()
        self.case_name, self.precedential_status = self._get_case_name_and_status()

    def __str__(self):
        # TODO: Has issue with unicode...hard to track down, and a corner case,
        # thus prioritizing other issues. Can be reproduced in vol. 23 of F3.
        out = []
        for attr, val in self.__dict__.iteritems():
            if any(['body' in attr,
                    'dict' in attr,
                    'file' in attr,
                    'tree' == attr,
                    'url_element' == attr]):
                continue
            out.append('%s: %s' % (attr, val))
        return '\n'.join(out) + '\n'

    def _load_fix_file(self, location):
        '''Loads a fix file into memory so it can be accessed efficiently.'''
        fix_file = open(location, 'r')
        fix_dict = {}
        for line in fix_file:
            key, value = line.split('|')
            fix_dict[key] = value

        fix_file.close()
        return fix_dict

    def _check_fix_list(self, sha1, fix_dict):
        '''Given a sha1, return the correction for a case. Return false if no values.
    
        Corrections are strings that the parser can interpret as needed. Items are
        written to this file the first time the cases are imported, and this file
        can be used to import F3 into later systems.
        '''
        try:
            return fix_dict[sha1].strip()
        except KeyError:
            return False

    def _get_url(self, base_url):
        return urljoin(base_url, self.url_element.get('href'))

    def _get_download_url(self):
        return "http://bulk.resource.org/courts.gov/c/F3/%s/%s" % \
                                            tuple(self.url.rsplit('/', 2)[-2:])

    def _get_case_body(self):
        body_contents = self.tree.xpath('//body/*[not(@id="footer")]')

        body = ""
        body_text = ""
        for element in body_contents:
            body += tostring(element)
            try:
                body_text += tostring(element, method='text')
            except UnicodeEncodeError:
                # Happens with odd characters.
                pass

        return body, body_text

    def _get_court(self):
        try:
            courtPs = self.tree.xpath('//p[@class = "court"]')
            # Often the court ends up in the parties field.
            partiesPs = self.tree.xpath("//p[@class= 'parties']")
            court = ""
            for courtP in courtPs:
                court += tostring(courtP).lower()
            for party in partiesPs:
                court += tostring(party).lower()
        except IndexError:
            court = self._check_fix_list(self.sha1_hash, self.court_fix_dict)
            if not court:
                print self.url
                if BROWSER:
                    subprocess.Popen([BROWSER, self.url], shell=False).communicate()
                court = raw_input("Please input court name (e.g. \"First Circuit of Appeals\"): ").lower()
                self.court_fix_file.write("%s|%s\n" % (self.sha1_hash, court))
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
        elif ('claims' in court) or ('uscfc' == court):
            court = 'uscfc'
        else:
            # No luck extracting the court name. Try the fix file.
            court = self._check_fix_list(self.sha1_hash, self.court_fix_dict)
            if not court:
                # Not yet in the fix file. Check if it's a crazy ca5 case
                court = ''
                ca5courtPs = self.tree.xpath('//p[@class = "center"]')
                for ca5courtP in ca5courtPs:
                    court += tostring(ca5courtP).lower()
                if 'fifth circuit' in court:
                    court = 'ca5'
                else:
                    court = False

                if not court:
                    # Still no luck. Ask for input, then append it to
                    # the fix file.
                    print self.url
                    if BROWSER:
                        subprocess.Popen([BROWSER, self.url], shell=False).communicate()
                    court = raw_input("Unknown court. Input the court code to "
                                      "proceed [%s]: " % self.saved_court)
                    court = court or saved_court
                court_fix_file.write("%s|%s\n" % (self.sha1_hash, court))

        self.saved_court = court
        return court

    def _get_case_date(self, case_date):
        raw_date = case_date.find('a')
        try:
            if raw_date != None:
                date_text = raw_date.text
                try:
                    case_date = datetime.datetime(*time.strptime(date_text, "%B, %Y")[0:5])
                except ValueError, TypeError:
                    case_date = datetime.datetime(*time.strptime(date_text, "%B %d, %Y")[0:5])
            else:
                # No value was found. Throw an exception.
                raise ValueError
        except:
            # No date provided.
            try:
                # Try to get it from the saved list
                case_date = datetime.datetime(*time.strptime(self._check_fix_list(self.sha1_hash, self.date_fix_dict), "%B %d, %Y")[0:5])
            except:
                case_date = False
            if not case_date:
                # Parse out the dates with debug set to false.
                dates = parse_dates(self.body_text, False)
                try:
                    first_date_found = dates[0]
                except IndexError:
                    # No dates found.
                    first_date_found = False
                if first_date_found == saved_case_date:
                    # High likelihood of date being correct. Use it.
                    case_date = saved_case_date
                else:
                    print "Cannot find date at: %s" % self.url
                    if BROWSER:
                        subprocess.Popen([BROWSER, self.url], shell=False).communicate()
                    print "Unknown date. Possible options are:"
                    try:
                        print "  1) %s" % saved_case_date.strftime("%B %d, %Y")
                    except AttributeError:
                        # Happens on first iteration when saved_case_date has no strftime attribute.
                        try:
                            saved_case_date = dates[0]
                            print "  1) %s" % saved_case_date.strftime("%B %d, %Y")
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
                        case_date = saved_case_date
                    elif choice in ['2', '3', '4', '5']:
                        # The user chose an option between 2 and 5. Use it.
                        case_date = dates[int(choice) - 2]
                    else:
                        # The user typed a new date. Use it.
                        case_date = datetime.datetime(*time.strptime(choice, "%B %d, %Y")[0:5])
                self.date_fix_file.write("%s|%s\n" % (sha1_hash, case_date.strftime("%B %d, %Y")))

        # Used during the next iteration as the default value
        self.saved_case_date = case_date
        return case_date

    def _get_west_cite(self):
        return self.url_element.text

    def _get_docket_number(self):
        return self.url.split('.')[-2]

    def _get_case_name_and_status(self):
        case_name = self.url_element.get('title').lower()
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
        if 'first circuit' in case_name:
            case_name = re.sub(ca1regex, '', case_name)
            status = 'Unpublished'
        elif 'second circuit' in case_name:
            case_name = re.sub(ca2regex, '', case_name)
            case_name = re.sub(ca2regex2, '', case_name)
            status = 'Unpublished'
        elif 'third circuit' in case_name:
            case_name = re.sub(ca3regex, '', case_name)
            status = 'Unpublished'
        elif 'fourth circuit' in case_name:
            case_name = re.sub(ca4regex, '', case_name)
            status = 'Unpublished'
        elif 'fifth circuit' in case_name:
            case_name = re.sub(ca5regex, '', case_name)
            status = 'Unpublished'
        elif 'sixth circuit' in case_name:
            case_name = re.sub(ca6regex, '', case_name)
            status = 'Unpublished'
        elif 'seventh circuit' in case_name:
            case_name = re.sub(ca7regex, '', case_name)
            status = 'Unpublished'
        elif 'eighth circuit' in case_name:
            case_name = re.sub(ca8regex, '', case_name)
            status = 'Unpublished'
        elif 'ninth circuit' in case_name:
            case_name = re.sub(ca9regex, '', case_name)
            status = 'Unpublished'
        elif 'tenth circuit' in case_name:
            case_name = re.sub(ca10regex, '', case_name)
            status = 'Unpublished'
        elif 'd.c. circuit' in case_name:
            case_name = re.sub(cadcregex, '', case_name)
            status = 'Unpublished'
        elif 'federal circuit' in case_name:
            case_name = re.sub(cafcregex, '', case_name)
            status = 'Unpublished'
        else:
            status = 'Published'

        case_name = titlecase(harmonize(clean_string(case_name)))

        if case_name == '' or case_name == 'unpublished disposition':
            # No luck getting the case name
            saved_case_name = self._check_fix_list(self.sha1_hash, self.case_name_dict)
            if saved_case_name:
                case_name = saved_case_name
            else:
                print self.url
                if BROWSER:
                    subprocess.Popen([BROWSER, self.url], shell=False).communicate()
                case_name = raw_input("Short case name: ")
                self.case_name_fix_file.write("%s|%s\n" % (self.sha1_hash, case_name))

        return case_name, status


class Volume(object):
    '''Represents a volume within Resource.org'''
    def __init__(self, url):
        super(Volume, self).__init__()
        self.url = url
        self.tree = fromstring(urllib2.urlopen(self.url).read())
        self.case_urls = self.tree.xpath('//table/tbody/tr/td[1]/a')
        self.case_dates = self.tree.xpath('//table/tbody/tr/td[2]')
        self.sha1_hashes = self.tree.xpath('//table/tbody/tr/td[3]/a/text()')

    def __len__(self):
        return len(self.case_urls)

    def __getitem__(self, key):
        try:
            # Check if key is an int. If so, we do the simple thing.
            int(key)
            return Case(self.url,
                       self.case_urls[key],
                       self.case_dates[key],
                       self.sha1_hashes[key])
        except ValueError:
            # If a for-reals key is provided, we zip up the items we want, and 
            # return them.
            for t in zip(self.case_urls[key],
                         self.case_dates[key],
                         self.sha1_hashes[key]):
                return Case(self.url, *t)

    def __iter__(self):
        print "Entering __iter__function."
        for i in range(i, self.__len__()):
            return Case(self.url,
                       self.case_urls[i],
                       self.case_dates[i],
                       self.sha1_hashes[i])


class Corpus(object):
    '''Contains a collection of Volumes'''
    def __init__(self, url):
        super(Corpus, self).__init__()
        self.url = url
        self.tree = fromstring(urllib2.urlopen(urljoin(url, "index.html")).read())
        self.volume_urls = self.tree.xpath('//table/tbody/tr/td[1]/a/@href')
        print self.volume_urls[60]

    def __len__(self):
        return len(self.volume_urls)

    def __getitem__(self, key):
        try:
            int(key)
            if key > 456:
                # Magic number. Volume 457 is missing.
                key += 1
            return Volume(urljoin(self.url, "%s/index.html" % key))
        except ValueError:
            for vol in self.volume_urls[key]:
                return Volume(urljoin(self.url, '%s/index.html' % vol))

    def __iter__(self):
        for volume_url in self.volume_urls:
            volume_url = urljoin(self.url, volume_url + "/index.html")
            return Volume(volume_url)
