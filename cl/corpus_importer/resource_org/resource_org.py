from juriscraper.lib.string_utils import titlecase, clean_string
from juriscraper.lib.string_utils import harmonize
import urllib2
import datetime
from lxml.html import fromstring
from urlparse import urljoin
import re
import requests
import time


class Case(object):
    """Represents a case within Resource.org"""

    def __init__(self, base_url, url_element, case_date, sha1_hash):
        print "Making a case object"
        super(Case, self).__init__()
        # Non-core data attributes
        self.url_element = url_element
        self.tree = fromstring(
            urllib2.urlopen(urljoin(base_url, url_element.get('href'))).read())
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
        for attr, val in self.__dict__.items():
            if any(['body' in attr,
                    'dict' in attr,
                    'file' in attr,
                    'tree' == attr,
                    'url_element' == attr]):
                continue
            out.append('%s: %s' % (attr, val))
        return '\n'.join(out) + '\n'

    def _load_fix_file(self, location):
        """Loads a fix file into memory so it can be accessed efficiently."""
        fix_file = open(location, 'r')
        fix_dict = {}
        for line in fix_file:
            key, value = line.split('|')
            fix_dict[key] = value

        fix_file.close()
        return fix_dict

    def _check_fix_list(self, sha1, fix_dict):
        """Given a sha1, return the correction for a case. Return false if no values.

        Corrections are strings that the parser can interpret as needed. Items are
        written to this file the first time the cases are imported, and this file
        can be used to import F3 into later systems.
        """
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


    def _get_case_date(self, case_date):
        raw_date = case_date.find('a')
        try:
            if raw_date is not None:
                date_text = raw_date.text
                try:
                    case_date = datetime.datetime(
                        *time.strptime(date_text, "%B, %Y")[0:5])
                except ValueError, TypeError:
                    case_date = datetime.datetime(
                        *time.strptime(date_text, "%B %d, %Y")[0:5])
            else:
                # No value was found. Throw an exception.
                raise ValueError
        except:
            # No date provided.
            try:
                # Try to get it from the saved list
                case_date = datetime.datetime(*time.strptime(
                    self._check_fix_list(self.sha1_hash, self.date_fix_dict),
                    "%B %d, %Y")[0:5])
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
                        subprocess.Popen([BROWSER, self.url],
                                         shell=False).communicate()
                    print "Unknown date. Possible options are:"
                    try:
                        print "  1) %s" % saved_case_date.strftime("%B %d, %Y")
                    except AttributeError:
                        # Happens on first iteration when saved_case_date has no strftime attribute.
                        try:
                            saved_case_date = dates[0]
                            print "  1) %s" % saved_case_date.strftime(
                                "%B %d, %Y")
                        except IndexError:
                            # Happens when dates has no values.
                            print "  No options available."
                    for k, date in enumerate(dates[0:4]):
                        if date.year >= 1900:
                            # strftime can't handle dates before 1900.
                            print "  %s) %s" % (
                                k + 2, date.strftime("%B %d, %Y"))
                    choice = raw_input(
                        "Enter the date or an option to proceed [1]: ")
                    choice = choice or 1
                    if str(choice) == '1':
                        # The user chose the default. Use the saved value from the last case
                        case_date = saved_case_date
                    elif choice in ['2', '3', '4', '5']:
                        # The user chose an option between 2 and 5. Use it.
                        case_date = dates[int(choice) - 2]
                    else:
                        # The user typed a new date. Use it.
                        case_date = datetime.datetime(
                            *time.strptime(choice, "%B %d, %Y")[0:5])
                self.date_fix_file.write(
                    "%s|%s\n" % (sha1_hash, case_date.strftime("%B %d, %Y")))

        # Used during the next iteration as the default value
        self.saved_case_date = case_date
        return case_date

    def _get_west_cite(self):
        return self.url_element.text

    def _get_docket_number(self):
        return self.url.split('.')[-2]


class Volume(object):
    """Represents a volume within Resource.org"""

    def __init__(self, url):
        super(Volume, self).__init__()
        self.url = url
        self.tree = fromstring(urllib2.urlopen(self.url).read())
        self.case_urls = self.tree.xpath('//table/tbody/tr/td[1]/a')
        self.case_dates = self.tree.xpath('//table/tbody/tr/td[2]')
        self.sha1_hashes = self.tree.xpath('//table/tbody/tr/td[3]/a/text()')
        print "Created volume with %s case urls" % len(self.case_urls)

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
    """Contains a collection of Volumes"""

    def __init__(self, url):
        super(Corpus, self).__init__()
        self.url = url
        self.tree = fromstring(
            requests.get(urljoin(url, "index.html")).content)
        self.volume_urls = self.tree.xpath('//table/tbody/tr/td[1]/a/@href')
        print "Created corpus with %s volume URLs" % len(self.volume_urls)

    def __len__(self):
        return len(self.volume_urls)

    def __getitem__(self, key):
        try:
            int(key)
            if key > 456:
                # Volume 457 is missing. Add 1 to all subsequent volumes.
                key += 1
            if key > 465:
                # Volume 466 is missing. Add 1 to all subsequent volumes.
                key += 1
            return Volume(urljoin(self.url, "%s/index.html" % key))
        except ValueError:
            for vol in self.volume_urls[key]:
                return Volume(urljoin(self.url, '%s/index.html' % vol))

    def __iter__(self):
        for volume_url in self.volume_urls:
            volume_url = urljoin(self.url, volume_url + "/index.html")
            return Volume(volume_url)
