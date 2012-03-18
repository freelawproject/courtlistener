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

import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'
import sys
sys.path.append("/var/www/court-listener")

from alert.lib.parse_dates import parse_dates
from alert.lib.string_utils import clean_string, harmonize, titlecase
import datetime
from lxml.html import fromstring, tostring
import re
import subprocess
import time
import urllib2
from urlparse import urljoin


BROWSER = 'firefox-trunk'

class Case(object):
    '''Represents a case within Resource.org'''
    def __init__(self, base_url, url_element, case_date, sha1_hash):
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
        self.status = 'R'

    def __str__(self):
        out = []
        for attr, val in self.__dict__.iteritems():
            if any(['body' in attr,
                    'dict' in attr,
                    'file' in attr]):
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
                try:
                    dates = parse_dates(self.body_text, False)
                except OverflowError:
                    # Happens when we try to make a date from a very large number
                    dates = []
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
        case_url = urljoin(self.url, self.case_urls[key])
        return Case(case_url)

    def __iter__(self):
        for i in range(0, self.__len__()):
            yield Case(self.url,
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

    def __len__(self):
        # Caches the len attr for better performance.
        return len(self.volume_urls)

    def __getitem__(self, key):
        # Uses the key to create a volume object
        volume_url = urljoin(self.url, self.volume_urls[key], "index.html")
        return Volume(volume_url)

    def __iter__(self):
        for volume_url in self.volume_urls:
            volume_url = urljoin(self.url, volume_url + "/index.html")
            yield Volume(volume_url)
