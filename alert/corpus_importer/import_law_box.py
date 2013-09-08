from juriscraper.lib.string_utils import clean_string, harmonize, titlecase
from juriscraper.lib import parse_dates
import os
import pickle
import re
import subprocess
import traceback
from lxml import html
from alert.citations.constants import EDITIONS, REPORTERS
from alert.citations.find_citations import get_citations
from datetime import date, timedelta
from alert.lib.import_lib import map_citations_to_models

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import argparse
import datetime
import fnmatch
import hashlib
from lxml.html.clean import Cleaner
from lxml.html import tostring

from alert.search.models import Document, Citation, Court


DEBUG = 3

try:
    with open('lawbox_fix_file.pkl', 'rb') as fix_file:
        fixes = pickle.load(fix_file)
except (IOError, EOFError):
    fixes = {}

all_courts = Court.objects.all()

def add_fix(case_path, fix_dict):
    """Adds a fix to the fix dictionary. This dictionary looks like:

    fixes = {
        'path/to/some/case.html': {'docket_number': None, 'date_filed': date(1982, 6, 9)},
    }
    """
    if case_path in fixes:
        fixes[case_path].update(fix_dict)
    else:
        fixes[case_path] = fix_dict


def get_citations_from_tree(complete_html_tree):
    path = '//center[descendant::text()[not(starts-with(normalize-space(.), "No.") or starts-with(normalize-space(.), "Case No.") or starts-with(normalize-space(.), "Record No."))]]'
    citations = []
    for e in complete_html_tree.xpath(path):
        text = tostring(e, method='text', encoding='unicode')
        citations.extend(get_citations(text, html=False, do_defendant=False))
    if not citations:
        path = '//title/text()'
        text = complete_html_tree.xpath(path)[0]
        citations = get_citations(text, html=False, do_post_citation=False, do_defendant=False)
        if not citations:
            raise
    if DEBUG >= 3:
        cite_strs = [str(cite.__dict__) for cite in citations]
        print "  Citations found: %s" % ',\n                   '.join(cite_strs)

    return citations


def get_case_name(complete_html_tree):
    path = '//head/title/text()'
    # Text looks like: 'In re 221A Holding Corp., Inc, 1 BR 506 - Dist. Court, ED Pennsylvania 1979'
    s = complete_html_tree.xpath(path)[0].rsplit('-', 1)[0].rsplit(',', 1)[0]
    # returns 'In re 221A Holding Corp., Inc.'
    s = harmonize(clean_string(titlecase(s)))
    if DEBUG >= 3:
        print "  Case name: %s" % s
    return s


def get_date_filed(clean_html_tree, citations, case_path=None, court=None):
    path = '//center[descendant::text()[not(starts-with(normalize-space(.), "No.") or starts-with(normalize-space(.), "Case No.") or starts-with(normalize-space(.), "Record No."))]]'

    reporter_keys = [citation.reporter for citation in citations]
    range_dates = []
    for reporter_key in reporter_keys:
        for reporter in REPORTERS.get(EDITIONS.get(reporter_key)):
            try:
                range_dates.extend(reporter['editions'][reporter_key])
            except KeyError:
                # Fails when a reporter_key points to more than one reporter, one of which doesn't have the edition
                # queried. For example, Wash. 2d isn't in REPORTERS['Wash.']['editions'][0].
                pass
    if range_dates:
        start, end = min(range_dates) - timedelta(weeks=20 * 52), max(range_dates) + timedelta(weeks=20 * 52)
        if end > date.today():
            end = date.today()

    dates = []
    for e in clean_html_tree.xpath(path):
        text = tostring(e, method='text', encoding='unicode')
        # Items like "February 4, 1991, at 9:05 A.M." stump the lexer in the date parser. Consequently, we purge
        # the word at, and anything after it.
        text = re.sub(' at .*', '', text)
        try:
            if range_dates:
                found = parse_dates.parse_dates(text, sane_start=start, sane_end=end)
            else:
                found = parse_dates.parse_dates(text, sane_end=date.today())
            if found:
                dates.extend(found)
        except UnicodeEncodeError:
            # If it has unicode is crashes dateutil's parser, but is unlikely to be the date.
            pass

    # Additional approaches to getting the date(s)
    if not dates and court == 'SCOTUS':
        pass


    if not dates:
        # Try to grab the year from the citations, if it's the same in all of them.
        years = set([citation.year for citation in citations if citation.year])
        if len(years) == 1:
            dates.append(date(list(years)[0], 1, 1))

    if not dates:
        try:
            dates = fixes[case_path]['dates']
        except KeyError:
            if DEBUG >= 4:
                subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
                input_date = raw_input('  No date found. What should be here (YYYY-MM-DD)? ')
                add_fix(case_path, {'dates': [datetime.datetime.strptime(input_date, '%Y-%m-%d').date()]})
                dates = [input_date]
            elif DEBUG == 2:
                # Write the failed case out to file.
                dates.append(date.today())
                with open('missing_dates.txt', 'a') as out:
                    out.write('%s\n' % case_path)

        '''
        # Special cases...sigh.
        for e in clean_html_tree.xpath(path):
            text = tostring(e, method='text', encoding='unicode')
            if 'December, 1924' in text:
                dates.append(date(1924, 12, 1))
            elif '38 Cal.App.2d 215 (1040)' in text:
                dates.append(date(1940, 3, 29))
            elif 'September 28, 1336' in text:
                dates.append(date(1936, 9, 28))
            elif 'June 21, 1944.8' in text:
                dates.append(date(1944, 6, 21))
            elif 'Nov. 16, 1567' in text:
                dates.append(date(1967, 11, 16))
            if dates:
                break
        '''

    if DEBUG >= 3:
        print "  Using date: %s of dates found: %s" % (max(dates), dates)
    return max(dates)


def get_precedential_status(html_tree):
    return None


def get_docket_number(html, case_path=None, court=None):
    try:
        path = '//center/text()'
        text_elements = html.xpath(path)
    except AttributeError:
        # Not an HTML element, instead it's a string
        text_elements = [html]
    docket_no_formats = ['Bankruptcy', 'C.A.', 'Case', 'Civ', 'Civil', 'Civil Action', 'Crim', 'Criminal Action',
                         'Docket', 'Misc', 'Record']
    regexes = [
        re.compile('((%s)( Nos?\.)?)|(Nos?(\.| )?)' % "|".join(map(re.escape, docket_no_formats)), re.IGNORECASE),
        re.compile('\d{2}-\d{2,5}'),          # WY-03-071, 01-21574
        re.compile('[A-Z]{2}-[A-Z]{2}'),      # CA-CR 5158
        re.compile('[A-Z]\d{2} \d{4}[A-Z]'),  # C86 1392M
        re.compile('\d{2} [A-Z] \d{4}'),      # 88 C 4330
        re.compile('[A-Z]-\d{2,4}'),          # M-47B (VLB), S-5408
        re.compile('[A-Z]\d{3,}',),
        re.compile('[A-Z]{4,}'),              # SCBD #4983
        re.compile('\d{5,}'),                 # 95816
        re.compile('\d{2},\d{3}'),            # 86,782
        re.compile('([A-Z]\.){4}'),           # S.C.B.D. 3020
        re.compile('\d{2}-[a-z]{2}-\d{4}'),
    ]

    docket_number = None
    outer_break = False
    for t in text_elements:
        if outer_break:
            # Allows breaking the outer loop from the inner loop
            break
        t = clean_string(t).strip('.')
        for regex in regexes:
            if re.search(regex, t):
                docket_number = t
                outer_break = True
                break

    if docket_number:
        if docket_number.startswith('No.'):
            docket_number = docket_number[4:]
        elif docket_number.startswith('Nos.'):
            docket_number = docket_number[5:]
        elif docket_number.startswith('Docket No.'):
            docket_number = docket_number[11:]
        if re.search('^\(.*\)$', docket_number):
            # Starts and ends with parens. Nuke 'em.
            docket_number = docket_number[1:-1]

    if docket_number and re.search('submitted|reversed', docket_number, re.I):
        # False positive. Happens when there's no docket number and the date is incorrectly interpretted.
        docket_number = None

    if not docket_number:
        try:
            docket_number = fixes[case_path]['docket_number']
        except KeyError:
            docket_number = None
            '''
            if 'northeastern' not in case_path and \
                    'federal_reporter/2d' not in case_path and \
                    court not in ['or', 'orctapp', 'cal'] and \
                    ('unsorted' not in case_path and court not in ['ind']) and \
                    ('pacific_reporter/2d' not in case_path and court not in ['calctapp']):
                # Lots of missing docket numbers here.
                if DEBUG >= 2:
                    subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
                input_doc_number = raw_input('  No docket number found. What should be here? ')
                add_fix(case_path, {'docket_number': input_doc_number})
            '''
    if DEBUG >= 2:
        print '  Docket Number: %s' % docket_number
    return docket_number


def get_court_object(html, case_path=None):
    """
       Parse out the court string, somehow, and then map it back to our internal ids
    """
    path = '//center/p/b/text()'
    text_elements = html.xpath(path)

    def string_to_key(str):
        """Given a string, tries to map it to a court key."""
        # State
        if 'Supreme Court of Alaska' in str:
            return 'alaska'
        elif 'Court of Appeals of Alaska' in str:
            return 'alaskactapp'
        elif 'Supreme Court of Arizona' in str:
            return 'ariz'
        elif re.search('Court of Appeals,? of Arizona', str):
            return 'arizctapp'
        elif 'Supreme Court of California' in str:
            return 'cal'
        elif 'California Court of Appeals' in str or \
                'Court of Appeals of California' in str:
            return 'calctapp'
        elif 'Supreme Court of Colorado' in str:
            return 'colo'
        elif 'Colorado Court of Appeals' in str or \
                'Court of Appeals of Colorado' in str:
            return 'coloctapp'
        elif 'Supreme Court of Hawai' in str:
            return 'haw'
        elif re.search('Intermediate Court of Appeals .*Hawai', str, re.I) or \
                        'Court of Appeals of Hawai' in str:
            return 'hawapp'
        elif re.search('Supreme Court of (the state of )?Idaho', str, re.I):
            return 'idaho'
        elif 'Court of Appeals of Idaho' in str or \
                'Idaho Court of Appeals' in str:
            return 'idahoctapp'
        elif 'Supreme Court of Illinois' in str:
            return 'ill'
        elif 'Appellate Court of Illinois' in str or \
                'Illinois Appellate Court' in str:
            return 'illappct'
        elif 'Supreme Court of Indiana' in str:
            return 'ind'
        elif re.search('Court of Appeals ((of)|(in)) Indiana', str) or \
                re.search('Appe((llate)|(als)) Court of Indiana', str) or \
                'Indiana Court of Appeals' in str:
            return 'indctapp'
        elif 'Supreme Court of Kansas' in str:
            return 'kan'
        elif 'Court of Appeals of Kansas' in str:
            return 'kanctapp'
        elif re.search('Supreme (Judicial )?Court of Massachusetts', str):
            return 'mass'
        elif 'Appeals Court of Massachusetts' in str:
            return 'massappct'
        elif re.search('Supreme Court of Montana', str, re.I):
            return 'mont'
        elif 'Supreme Court of Nevada' in str:
            return 'nev'
        elif 'Supreme Court of New Mexico' in str:
            return 'nm'
        elif 'Court of Appeals of New Mexico' in str or \
                'New Mexico Court of Appeals' in str:
            return 'nmctapp'
        elif re.search('Court of Appeals of (the State of )?New York', str):
            return 'ny'
        elif 'Supreme Court of Ohio' in str:
            return 'ohio'
        elif re.search('Supreme Court (of )?Oklahoma', str):
            return 'okla'
        elif re.search('Court of Criminal Appeals (of )?Oklahoma', str, re.I) or \
                re.search('Criminal Courts of Appeals of Oklahoma', str):
            return 'oklacrimapp'
        elif re.search('Court of Civils? Appeals of Oklahoma', str) or \
                re.search('Court of Appeals?,? (civil )?(of )?(State )?(of )?Oklahoma', str, re.I):
            # Researched this with the court. When they refer to simply the "Court of Appeals" they mean the the civil
            # court.
            return 'oklacivapp'
        elif re.search('Supreme Court (((for)|(of)) the State )?of (the )?Oregon', str, re.I) or \
                re.search('Oregon Supreme Court', str, re.I):
            return 'or'
        elif re.search('Court of Appeals of (the )?(state of )?Oregon', str, re.I) or \
                'oregon court of appeals' in str.lower():
            return 'orctapp'
        elif re.search('Supreme Court of (the )?(state of )?Utah', str, re.I):
            return 'utah'
        elif re.search('Court of Appeals (of )?Utah', str) or \
                'Utah Court of Appeals' in str:
            return 'utahctapp'
        elif 'Supreme Court of Washington' in str:
            return 'wash'
        elif 'Court of Appeals of Washington' in str:
            return 'washctapp'
        elif re.search('Supreme Court (of )?Wyoming', str):
            return 'wyo'

        # State Special
        elif 'Tax Court of Arizona' in str:
            return 'ariztaxct'
        elif 'Tax Court of Indiana' in str or \
                        'Indiana Tax Court' in str:
            return 'indtc'
        elif 'Oklahoma Judicial Ethics Advisory Panel' in str:
            return 'oklajeap'
        elif 'Court on the Judiciary of Oklahoma' in str:
            return 'oklacoj'

        # Federal appeals
        elif re.search('Court,? of Appeal', str) or \
                'Circuit of Appeals' in str:
            if 'First Circuit' in str or \
                    'First District' in str:
                return 'ca1'
            elif 'Second Circuit' in str or \
                    'Second District' in str:
                return 'ca2'
            elif 'Third Circuit' in str:
                return 'ca3'
            elif 'Fourth Circuit' in str:
                return 'ca4'
            elif 'Fifth Circuit' in str:
                return 'ca5'
            elif 'Sixth Circuit' in str:
                return 'ca6'
            elif 'Seventh Circuit' in str:
                return 'ca7'
            elif 'Eighth' in str:  # Aka, apparently, "Eighth Court"
                return 'ca8'
            elif 'Ninth Circuit' in str:
                return 'ca9'
            elif 'Tenth Circuit' in str:
                return 'ca10'
            elif 'Eleventh Circuit' in str:
                return 'ca11'
            elif 'District of Columbia' in str:
                return 'cadc'
            elif 'Federal Circuit' in str:
                return 'cafc'
            elif 'Emergency' in str:
                return 'eca'
            elif 'Court of Appeals of Columbia' in str:
                return 'cadc'
        elif 'Judicial Council of the Ninth Circuit' in str:
            return 'ca9'


        # Federal district
        elif re.search('Distr?in?ct\.? Court', str, re.I):
            fd_pairs = (
                ('D(\.|(istrict))?,? (of )?Colu(m|(in))bia', 'dcd'),
            )
            if re.search('D(\.|(istrict))?,? (of )?Colu(m|(in))bia', str):
                return 'dcd'
            elif re.search('M\. ?D\. Alabama', str):
                return 'almd'
            elif re.search('N\. ?D\. Alabama', str):
                return 'alnd'
            elif re.search('S\. ?D\. Alabama', str):
                return 'alsd'
            elif 'Alaska' in str:
                return 'akd'
            elif re.search('D\.? ?Arizona', str):
                return 'azd'
            elif re.search('E\. ?D(\.|:)? Arkansas', str):
                return 'ared'
            elif re.search('W\. ?D\. Arkansas', str):
                return 'arwd'
            elif re.search('C\. ?D\. ?(of )?Cal(ifornia)?', str):
                return 'cacd'
            elif re.search('N\. ?D\. ?(of )?Cal(ifornia)?', str):
                return 'cand'
            elif re.search('S\. ?D\. ?(of )?Cal(ifornia)?', str):
                return 'casd'
            # No longer exists. Existed 1866-07-27 to 1886-08-05
            elif 'D. California' in str:  # Must go last for Cal.
                return 'californiad'
            elif re.search('D\. ?Colo(rado)?', str):
                return 'cod'
            elif 'D. Conn' in str:
                return 'ctd'
            elif re.search('D\. ?Delaware', str):
                return 'ded'
            elif re.search('M\. ?D\. ?Florida', str):
                return 'flmd'
            elif re.search('N\. ?D\. ?Florida', str):
                return 'flnd'
            elif re.search('S\. ?D\. ?Florida', str):
                return 'flsd'
            elif re.search('M\. ?D\. ?Georgia', str):
                return 'gamd'
            elif re.search('N\. ?D\. ?(of )?Georgia', str):
                return 'gand'
            elif re.search('S\. ?D\. ?Georgia', str):
                return 'gasd'
            elif 'Hawai' in str:
                return 'hid'
            elif 'D. Idaho' in str:
                return 'idd'
            elif re.search('C\.? ?D\.? (of )?Ill(inois)?', str):
                return 'ilcd'
            elif re.search('N\. ?D\.?,? ?(of )?Ill(inois)?', str):
                return 'ilnd'
            elif re.search('S\. ?D\. ?Illinois', str):
                return 'ilsd'
            # Abolished. 1905-03-03 to 1978-10-02
            elif re.search('E\. ?D\. ?Illinois', str):
                return 'illinoised'
            # Abolished. 1819-03-03 to 1855-02-13
            elif 'D. Illinois' in str:  # Must go last
                return 'illinoisd'
            elif re.search('N\.? ?D\.? ?(of )?Indiana', str):
                return 'innd'
            elif re.search('S\.? ?D\.? ?(of )?Indiana', str):
                return 'insd'
            # Abolished. 1817-03-03 to 1928-04-21
            elif 'D. Indiana' in str:  # Must go last
                return 'indianad'
            elif re.search('N\. ?D\. ?(of )?Iowa', str):
                return 'iand'
            elif re.search('S\.? ?D\.? ?Iowa', str):
                return 'iasd'
            elif 'Kansas' in str:
                return 'ksd'
            elif re.search('E\. ?D\. ?Kentucky', str):
                return 'kyed'
            elif re.search('W\. ?D\. Kentucky', str):
                return 'kywd'
            elif re.search('E\. ?D\. Louisiana', str) or \
                    'Eastern District, Louisiana' in str:
                return 'laed'
            elif re.search('M\. ?D\. Louisiana', str):
                return 'lamd'
            elif re.search('W\. ?D\. Louisiana', str):
                return 'lawd'
            elif 'D. Maine' in str:
                return 'med'
            elif re.search('D(\.|(istrict))? ?(of )?Maryland', str) or \
                            ', Maryland' in str or \
                            'Maryland Admiralty' in str:
                return 'mdd'
            elif re.search('D?\.? ?(of )?Mass(achusetts)?', str):
                return 'mad'
            elif re.search('E\.? ?D\.? ?(of )?Michigan', str):
                return 'mied'
            elif re.search('W\. ?D\. ?Michigan', str):
                return 'miwd'
            elif re.search('D\.? Minnesota', str):
                return 'mnd'
            elif re.search('N\. ?D\. Mississippi', str):
                return 'msnd'
            elif re.search('S\. ?D\. Mississippi', str):
                return 'mssd'
            elif re.search('C\. ?D\. Missouri', str):
                return 'mocd'
            elif re.search('E\.? ?D(\.|(istrict))? ?(of )?(the )?Missouri', str):
                return 'moed'
            elif re.search('W\. ?D\. Missouri', str):
                return 'mowd'
            elif 'D. Montana' in str:
                return 'mtd'
            elif re.search('D(\.|(istrict))? ?(of )?Nebraska', str):
                return 'ned'
            elif 'D. Nevada' in str:
                return 'nvd'
            elif re.search('D\. ?New Hampshire', str):
                return 'nhd'
            elif 'New Jersey' in str:
                return 'njd'
            elif 'D. New Mexico' in str:
                return 'nmd'
            elif re.search('E(\.|(astern)) ?D(\.|(istrict)) (of )?New\.? York', str):
                return 'nyed'
            elif re.search('N\. ?D\. New York', str):
                return 'nynd'
            elif re.search('S(\.|(outhern)) ?D(\.|(istrict))? ?(of )?New York', str) or \
                    re.search('S\. ?D\. ?N\. ?Y', str):
                return 'nysd'
            elif re.search('W\. ?D\. New York', str) or \
                    re.search('W\. ?D\. ?N\. ?Y', str):
                return 'nywd'
            elif re.search('E\. ?D\. North Carolina', str):
                return 'nced'
            elif re.search('M\. ?D\. North Carolina', str) or \
                    'Greensboro Division' in str:
                return 'ncmd'
            elif re.search('W\. ?D\. North Carolina', str):
                return 'ncwd'
            elif 'North Dakota' in str:
                return 'ndd'
            elif re.search('N\. ?D\. Ohio', str):
                return 'ohnd'
            elif re.search('S\. ?D\.,? (of )?Ohio', str):
                return 'ohsd'
            # Abolished. 1803-02-19 to 1855-02-10
            elif 'D. Ohio' in str:  # Must be the last court!
                return 'ohiod'
            elif re.search('E\. ?D\. Oklahoma', str):
                return 'oked'
            elif re.search('N\. ?D\. Oklahoma', str):
                return 'oknd'
            elif re.search('W\. ?D\. Oklahoma', str):
                return 'okwd'
            elif 'D. Oregon' in str:
                return 'ord'
            elif re.search('E\.? ?D\. ?P(a|(ennsylvania))', str):
                return 'paed'
            elif re.search('M(\.|(iddle))? ?D(\.|(ist\.))? ?P(a|(ennsylvania))', str):
                return 'pamd'
            elif re.search('W\.? ?D\. P(a|(ennsylvania))', str):
                return 'pawd'
            # Abolished. 1789-09-24 to 1818-04-20
            elif re.search('D\. P(a|(ennsylvania))', str):  # Must go last
                return 'pennsylvaniad'
            elif 'D. Rhode Island' in str:
                return 'rid'
            # Abolished. 1823-02-21 to 1965-10-07
            elif re.search('E\. ?D\. South Carolina', str):
                return 'southcarolinaed'
            # Abolished. 1823-02-21 to 1965-10-07
            elif re.search('W\. ?D\. South Carolina', str):
                return 'southcarolinawd'
            elif 'D. South Carolina' in str:  # Must go last!
                return 'scd'
            elif 'D. South Dakota' in str:
                return 'sdd'
            elif re.search('E\. ?D\. Tennessee', str):
                return 'tned'
            elif re.search('M(\.|(iddle))? ?D(\.|(istrict))? (of )?Tennessee', str):
                return 'tnmd'
            elif re.search('W\. ?D\. Tennessee', str):
                return 'tnwd'
            # Abolished. 1797-01-31 to 1839-06-18
            elif 'D. Tennessee' in str:  # Must be the last court!
                return 'tennessed'
            elif re.search('E\. ?D\. Texas', str):
                return 'txed'
            elif re.search('N\. ?D\.,? (of )?Texas', str):
                return 'txnd'
            elif re.search('S(\.|(outhern)) ?D(\.|(istrict)) ?(of )?Texas', str):
                return 'txsd'
            elif re.search('W\.? ?D\.? Texas', str):
                return 'txwd'
            elif 'Utah' in str:
                return 'utd'
            elif 'D. Vermont' in str:
                return 'vtd'
            elif re.search('E\.? ?D\.? ?(of )?Virginia', str, re.I):
                return 'vaed'
            elif re.search('W\. ?D\. Virginia', str):
                return 'vawd'
            elif re.search('E\. ?D\. Washington', str):
                return 'waed'
            elif re.search('W\. ?D\. Washington', str):
                return 'wawd'
            elif re.search('N\. ?D\. West Virginia', str):
                return 'wvnd'
            elif re.search('S\. ?D\. (of )?West Virginia', str) or \
                    'West Virginia, at Charleston' in str:
                return 'wvsd'
            elif re.search('E\. ?D\. Wisconsin', str):
                return 'wied'
            elif re.search('W\. ?D\. Wisconsin', str):
                return 'wiwd'
            elif 'Wyoming' in str:
                return 'wyd'
            # Abolished. 1937-07-26 to 1982-03-31
            elif 'Canal Zone' in str:
                return 'canalzoned'
            elif 'Guam' in str:
                return 'gud'
            elif 'Northern Mariana' in str:
                return 'nmid'
            elif re.search('Puerto Rico', str):
                return 'prd'
            elif 'Virgin Islands' in str:
                return 'vid'
        elif 'D. Virgin Islands' in str:
            return 'vid'

        # Federal special
        elif 'United States Judicial Conference Committee' in str or \
                'U.S. Judicial Conference Committee' in str:
            return 'usjc'
        elif re.search('Judicial Panel ((on)|(of)) Multidistrict Litigation', str, re.I):
            return 'jpml'
        elif 'Court of Customs and Patent Appeals' in str:
            return 'ccpa'
        elif 'Court of Claims' in str:
            return 'cc'  # Cannot change
        elif 'United States Foreign Intelligence Surveillance Court' in str:
            return 'fiscr'  # Cannot change
        elif re.search('Court,? of,? International ?Trade', str):
            return 'cit'
        elif 'United States Customs Court' in str:
            return 'cusc'  # Cannot change?
        elif re.search('Special Court(\.|,)? Regional Rail Reorganization Act', str):
            return 'reglrailreorgct'

        # Bankruptcy Courts
        elif re.search('bankrup?tcy', str, re.I):
            # Bankruptcy Appellate Panels
            if re.search('Appellan?te Panel', str, re.I):
                if 'First Circuit' in str:
                    return 'bap1'
                elif 'Second Circuit' in str:
                    return 'bap2'
                elif 'Sixth Circuit' in str:
                    return 'bap6'
                elif 'Eighth Circuit' in str:
                    return 'bap8'
                elif 'Ninth Circuit' in str:
                    return 'bap9'
                elif 'Tenth Circuit' in str:
                    return 'bap10'
                elif 'Maine' in str:
                    return 'bapme'
                elif 'Massachusetts' in str:
                    return 'bapma'

            # Bankruptcy District Courts
            else:
                if 'District of Columbia' in str or \
                        'D. Columbia' in str:
                    return 'dcb'
                elif re.search('M\.? ?D(\.|(istrict))? (of )?Alabama', str):
                    return 'almb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?Alabama', str):
                    return 'alnb'
                elif re.search('S\.? ?D(\.|(istrict))? (of )?Alabama', str):
                    return 'alsb'
                elif 'D. Alaska' in str:
                    return 'akb'
                elif re.search('D(\.|(istrict))? ?Arizona', str):
                    return 'arb'
                elif re.search('E\.? ?D(\.|(istrict))? ?(of )?Arkansas', str):
                    return 'areb'
                elif re.search('W\.? ?D(\.|(istrict))? ?(of )?Arkansas', str):
                    return 'arwb'
                elif re.search('C\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', str):
                    return 'cacb'
                elif re.search('E\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', str):
                    return 'caeb'
                elif re.search('N\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', str):
                    return 'canb'
                elif re.search('S\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', str):
                    return 'casb'
                elif re.search('D(\.|(istrict)) ?(of )?Colorado', str):
                    return 'cob'
                elif 'Connecticut' in str:
                    return 'ctb'
                elif re.search('D(\.|(istrict))? (of )?Delaware', str):
                    return 'deb'
                elif re.search('M\.? ?D(\.|(istrict))? ?(of )?Florida', str) or \
                        re.search('Middle District (of )?Florida', str) or \
                        'M .D. Florida' in str or \
                        'Florida, Tampa Division' in str or \
                        'Florida, Jacksonville Division' in str:
                    return 'flmb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?Florida', str):
                    return 'flnb'
                elif re.search('S\. ?D(\.|(istrict))? (of )?Florida', str):
                    return 'flsb'
                elif re.search('M\.? ?D(\.|(istrict))? (of )?Georgia', str):
                    return 'gamb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?Georgia', str) or \
                        'Atlanta Division' in str:
                    return 'ganb'
                elif re.search('S\. ?D(\.|(istrict))? Georgia', str):
                    return 'gasb'
                elif re.search('D(\.|(istrict))? ?Hawai', str):
                    return 'hib'
                elif 'D. Idaho' in str:
                    return 'idb'
                elif re.search('C\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', str):
                    return 'ilcb'
                elif re.search('N\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', str):
                    return 'ilnb'
                elif re.search('S\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', str):
                    return 'ilsb'
                elif re.search('N\.? ?D(\.|(istrict))? ?(of )?Indiana', str):
                    return 'innb'
                elif re.search('S.D. (of )?Indiana', str):
                    return 'insb'
                elif re.search('N\. ?D(\.|(istrict))? Iowa', str):
                    return 'ianb'
                elif re.search('S\. ?D(\.|(istrict))? (of )?Iowa', str):
                    return 'iasb'
                elif 'D. Kansas' in str or \
                        'M. Kansas' in str or \
                        'District of Kansas' in str or \
                        'D. Kan' in str:
                    return 'ksb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Kentucky', str):
                    return 'kyeb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?Kentucky', str):
                    return 'kywb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Loui?siana', str) or \
                        'Eastern District, Louisiana' in str:
                    return 'laeb'
                elif re.search('M\.? ?D(\.|(istrict))? (of )?Loui?siana', str):
                    return 'lamb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?Loui?siana', str):
                    return 'lawb'
                elif 'D. Maine' in str:
                    return 'meb'
                elif 'Maryland' in str:
                    return 'mdb'
                elif re.search('D(\.|(istrict))? ?(of )?Mass', str) or \
                        ', Massachusetts' in str:
                    return 'mab'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Michigan', str):
                    return 'mieb'
                elif re.search('W\.D(\.|(istrict))? (of )?Michigan', str):
                    return 'miwb'
                elif re.search('D(\.|(istrict))? ?Minnesota', str):
                    return 'mnb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?Mississippi', str):
                    return 'msnb'
                elif re.search('S\.? ?D(\.|(istrict))? (of )?Mississippi', str):
                    return 'mssb'
                elif re.search('E\.? ?D(\.|(istrict))? ?(of )?Missouri', str):
                    return 'moeb'
                elif re.search('W\.? ?D(\.|(istrict))? ?(of )?Missouri', str):
                    return 'mowb'
                elif 'D. Montana' in str:
                    return 'mtb'
                # Here we avoid a conflict with state abbreviations
                elif re.search('D(\.|(istrict))? (of )?Neb(raska)?', str):
                    return 'nebraskab'
                elif 'Nevada' in str:
                    return 'nvb'
                elif 'New Hampshire' in str or \
                        'D.N.H' in str:
                    return 'nhb'
                elif re.search('D(\.|(istrict))? ?New Jersey', str) or \
                        ', New Jersey' in str:
                    return 'njb'
                elif 'New Mexico' in str or \
                        'State of New Mexico' in str:
                    return 'nmb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?New York', str) or \
                        'E.D.N.Y' in str:
                    return 'nyeb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?New York', str):
                    return 'nynb'
                elif re.search('S\. ?D(\.|(istrict))? (of )?New York', str) or \
                        'Southern District of New York' in str or \
                        'S.D.N.Y' in str:
                    return 'nysb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?New York', str):
                    return 'nywb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?North Carolina', str):
                    return 'nceb'
                elif re.search('M\.? ?D(\.|(istrict))? (of )?North Carolina', str):
                    return 'ncmb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?North Carolina', str):
                    return 'ncwb'
                elif 'North Dakota' in str:
                    return 'ndb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?Ohio', str) or \
                        'Northern District of Ohio' in str:
                    return 'ohnb'
                elif re.search('S\. ?D(\.|(istrict))? (of )?Ohio', str):
                    return 'ohsb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Oklahoma', str):
                    return 'okeb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?Oklahoma', str):
                    return 'oknb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?Oklahoma', str):
                    return 'okwb'
                elif 'Oregon' in str:
                    return 'orb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Pennsylvania', str):
                    return 'paeb'
                elif re.search('M\.? ?D(\.|(istrict))? (of )?Pennsylvania', str):
                    return 'pamb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?Pennsylvania', str):
                    return 'pawb'
                elif ', Rhode Island' in str or \
                        re.search('D(\.|(istrict))? ?Rhode Island', str) or \
                        ', D.R.I' in str:
                    return 'rib'
                elif 'D.S.C' in str or \
                        re.search('D(\.|(istrict))? ?(of )?South Carolina', str):
                    return 'scb'
                elif 'D. South Dakota' in str or \
                        ', South Dakota' in str:
                    return 'sdb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Te(r|n)n(essee)?', str):
                    return 'tneb'
                elif re.search('M\.? ?D(\.|(istrict))? (of )?Tenn(essee)?', str) or \
                        'Middle District of Tennessee' in str or \
                        'M.D.S. Tennessee' in str or \
                        'Nashville' in str:
                    return 'tnmb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?Tennessee', str):
                    return 'tnwb'
                elif 'D. Tennessee' in str:
                    return 'tennesseeb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Texas', str):
                    return 'txeb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?Texas', str):
                    return 'txnb'
                elif re.search('S\.? ?D(\.|(istrict))? (of )?Texas', str):
                    return 'txsb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?Texas', str):
                    return 'txwb'
                elif 'Utah' in str:
                    return 'utb'
                elif re.search('D(\.|(istrict))? ?(of )?Vermont', str):
                    return 'vtb'
                elif re.search('E\.? ?D(\.|(istrict))? ?(of )?Virginia', str):
                    return 'vaeb'
                elif re.search('W\.? ?D(\.|(istrict))? ?(of )?Virginia', str):
                    return 'vawb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Washington', str):
                    return 'waeb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?Washington', str):
                    return 'wawb'
                elif re.search('N\.? ?D(\.|(istrict))? (of )?W(\.|(est)) Virginia', str):
                    return 'wvnb'
                elif re.search('S\.? ?D(\.|(istrict))? (of )?W(\.|(est)) Virginia', str):
                    return 'wvsb'
                elif re.search('E\.? ?D(\.|(istrict))? (of )?Wis(consin)?', str):
                    return 'wieb'
                elif re.search('W\.? ?D(\.|(istrict))? (of )?Wis(consin)?', str) or \
                        'Western District of Wisconsin' in str:
                    return 'wiwb'
                elif 'D. Wyoming' in str:
                    return 'wyb'
                elif 'Guam' in str:
                    return 'gub'
                elif 'Northern Mariana' in str:
                    return 'nmib'
                elif 'Puerto Rico' in str:
                    return 'prb'
                elif 'Virgin Islands' in str:
                    return 'vib'
        else:
            return False

    court = None
    for t in text_elements:
        t = clean_string(t).strip('.')
        court = string_to_key(t)
        if court:
            break

    # Round two: try the text elements joined together
    t = clean_string(' '.join(text_elements)).strip('.')
    court = string_to_key(t)

    if not court:
        try:
            court = fixes[case_path]['court']
        except KeyError:
            if DEBUG >= 3:
                subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
                input_court = raw_input("No court identified! What should be here? ")
                add_fix(case_path, {'court': input_court})
            elif DEBUG == 2:
                # Write the failed case out to file.
                court = 'test'
                with open('missing_courts.txt', 'a') as out:
                    out.write('%s\n' % case_path)

    if DEBUG >= 2:
        print '  Court: %s' % court

    return court


def get_html_from_raw_text(raw_text):
    """Using the raw_text, creates four useful variables:
        1. complete_html_tree: A tree of the complete HTML from the file, including <head> tags and whatever else.
        2. clean_html_tree: A tree of the HTML after stripping bad stuff.
        3. clean_html_str: A str of the HTML after stripping bad stuff.
        4. body_text: A str of the text of the body of the document.

    We require all of these because sometimes we need the complete HTML tree, other times we don't. We create them all
    up front for performance reasons.
    """
    complete_html_tree = html.fromstring(raw_text)
    cleaner = Cleaner(style=True,
                      remove_tags=['a', 'body', 'font', 'noscript'])
    clean_html_str = cleaner.clean_html(raw_text)
    clean_html_tree = html.fromstring(clean_html_str)
    body_text = tostring(clean_html_tree, method='text', encoding='unicode')

    return clean_html_tree, complete_html_tree, clean_html_str, body_text


def import_law_box_case(case_path):
    """Open the file, get its contents, convert to XML and extract the meta data.

    Return a document object for saving in the database
    """
    raw_text = open(case_path).read()
    clean_html_tree, complete_html_tree, clean_html_str, body_text = get_html_from_raw_text(raw_text)

    sha1 = hashlib.sha1(clean_html_str).hexdigest()
    citations = get_citations_from_tree(complete_html_tree)
    court = get_court_object(clean_html_tree, case_path)

    doc = Document(
        source='LB',
        sha1=sha1,
        court_id=court,
        html=clean_html_str,
        date_filed=get_date_filed(clean_html_tree, citations=citations, case_path=case_path, court=court),
        precedential_status=get_precedential_status(clean_html_tree)
    )

    cite = Citation(
        case_name=get_case_name(complete_html_tree),
        docket_number=get_docket_number(clean_html_tree, case_path=case_path, court=court)
    )

    # Add the dict of citations to the object as its attributes.
    citations_as_dict = map_citations_to_models(citations)
    for k, v in citations_as_dict.iteritems():
        setattr(cite, k, v)

    # TODO: I'm baffled why this isn't working right now.
    #doc.citation = cite

    return doc


def readable_dir(prospective_dir):
    if not os.path.isdir(prospective_dir):
        raise argparse.ArgumentTypeError("readable_dir:{0} is not a valid path".format(prospective_dir))
    if os.access(prospective_dir, os.R_OK):
        return prospective_dir
    else:
        raise argparse.ArgumentTypeError("readable_dir:{0} is not a readable dir".format(prospective_dir))


def check_duplicate(doc):
    """Return true if it should be saved, else False"""
    return True


def main():
    parser = argparse.ArgumentParser(description='Import the corpus provided by lawbox')
    parser.add_argument('-s', '--simulate', default=False, required=False, action='store_true',
                        help='Run the code in simulate mode, making no permanent changes.')
    parser.add_argument('-d', '--dir', type=readable_dir,
                        help='The directory where the lawbox dump can be found.')
    parser.add_argument('-l', '--line', type=int, default=1, required=False,
                        help='If provided, this will be the line number in the index file where we resume processing.')
    parser.add_argument('-r', '--resume', default=False, required=False, action='store_true',
                        help='Use the saved marker to resume operation where it last failed.')
    args = parser.parse_args()

    if args.dir:
        def case_generator(dir_root):
            """Yield cases, one by one to the importer by recursing and iterating the import directory"""
            for root, dirnames, filenames in os.walk(dir_root):
                for filename in fnmatch.filter(filenames, '*'):
                    yield os.path.join(root, filename)

        cases = case_generator(args.root)
        i = 0
    else:
        def case_generator(line_number):
            """Yield cases from the index file."""
            #index_file = open('index.txt')
            index_file = open('missing_courts.txt')
            for i, line in enumerate(index_file):
                if i > line_number:
                    yield line.strip()

        if args.resume:
            with open('lawbox_progress_marker.txt') as marker:
                resume_point = int(marker.read().strip())
            cases = case_generator(resume_point)
            i = resume_point
        else:
            cases = case_generator(args.line)
            i = args.line

    for case_path in cases:
        if DEBUG >= 2:  #and i % 1000 == 0:
            print "\n%s: Doing case (%s): file://%s" % (datetime.datetime.now(), i, case_path)
        try:
            doc = import_law_box_case(case_path)
            i += 1
        finally:
            traceback.format_exc()
            with open('lawbox_progress_marker.txt', 'w') as marker:
                marker.write(str(i))
            with open('lawbox_fix_file.pkl', 'wb') as fix_file:
                pickle.dump(fixes, fix_file)

        save_it = check_duplicate(doc)  # Need to write this method?
        if save_it and not args.simulate:
            # Not a dup, save to disk, Solr, etc.
            doc.cite.save()  # I think this is the save routine?
            doc.save()  # Do we index it here, or does that happen automatically?


if __name__ == '__main__':
    main()
