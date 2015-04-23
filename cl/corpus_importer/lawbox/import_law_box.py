import argparse
import datetime
import fnmatch
import hashlib
import pickle
import os
import random
import re
import subprocess
import sys
import traceback

from cl.corpus_importer.court_regexes import (
    fd_pairs, state_pairs, disambiguate_by_judge, fb_pairs
)
from cl.citations.find_citations import get_citations
from cl.corpus_importer.dup_helpers import get_html_from_raw_text
from cl.corpus_importer.lawbox.judge_extractor import get_judge_from_str
from cl.corpus_importer import dup_finder, dup_helpers
from cl.lib.argparse_types import readable_dir
from cl.lib.string_utils import anonymize
from cl.lib.import_lib import map_citations_to_models
from cl.search.models import Document, Court, Docket
from datetime import timedelta
from django.utils.timezone import now
from django import db
from juriscraper.lib.string_utils import clean_string, harmonize, titlecase
from juriscraper.lib.date_utils import parse_dates
from lxml.html import tostring
from reporters_db import EDITIONS, REPORTERS


DEBUG = [
    'judge',
    'citations',
    'case_name',
    # 'date',
    'docket_number',
    'court',
    # 'input_citations',
    # 'input_dates',
    # 'input_docket_number',
    'input_court',
    'input_case_names',
    # 'log_bad_citations',
    # 'log_bad_courts',
    # 'log_judge_disambiguations',
    # 'log_bad_dates',
    # 'log_bad_docket_numbers',
    # 'log_bad_judges',
    'log_multimerge',
    'counter',
]

try:
    with open('lawbox_fix_file.pkl', 'rb') as fix_file:
        fixes = pickle.load(fix_file)
except (IOError, EOFError):
    fixes = {}

try:
    # Load up SCOTUS dates
    scotus_dates = {}
    with open(os.path.join(INSTALL_ROOT, 'alert', 'corpus_importer',
                           'scotus_dates.csv'), 'r') as scotus_date_file:
        for line in scotus_date_file:
            citation, date_filed = [line.strip() for line in line.split('|')]
            date_filed = datetime.datetime.strptime(date_filed, '%Y-%m-%d')
            try:
                # If we get fail to get a KeyError, we append to the list we
                # got back, else, we create such a list.
                scotus_dates[citation].append(date_filed)
            except KeyError:
                scotus_dates[citation] = [date_filed]
except IOError:
    print "Unable to load scotus data! Exiting."
    sys.exit(1)

all_courts = Court.objects.all()


def add_fix(case_path, fix_dict):
    """Adds a fix to the fix dictionary. This dictionary looks like:

    fixes = {
        'path/to/some/case.html': {
          'docket_number': None,
          'date_filed': date(1982, 6, 9)
        },
    }
    """
    if case_path in fixes:
        fixes[case_path].update(fix_dict)
    else:
        fixes[case_path] = fix_dict


def log_print(msg):
    print msg
    log_location = '/sata/lawbox/import_log.txt'
    try:
        with open(log_location, 'a') as log:
            log.write(msg.encode('utf-8') + '\n')
    except IOError:
        # If the log doesn't exist
        print "WARNING: Unable to find log at %s" % log_location


def get_citations_from_tree(complete_html_tree, case_path):
    path = ('//center[descendant::text()[not('
            'starts-with(normalize-space(.), "No.") or '
            'starts-with(normalize-space(.), "Case No.") or '
            'starts-with(normalize-space(.), "Record No.")'
            ')]]')
    citations = []
    for e in complete_html_tree.xpath(path):
        text = tostring(e, method='text', encoding='unicode')
        citations.extend(get_citations(text, html=False, do_defendant=False))
    if not citations:
        path = '//title/text()'
        text = complete_html_tree.xpath(path)[0]
        citations = get_citations(text, html=False, do_post_citation=False,
                                  do_defendant=False)

    if not citations:
        try:
            citations = fixes[case_path]['citations']
        except KeyError:
            if 'input_citations' in DEBUG:
                subprocess.Popen(
                    ['firefox', 'file://%s' % case_path],
                    shell=False
                ).communicate()
                input_citation = raw_input(
                    '  No citations found. What should be here? ')
                citation_objects = get_citations(
                    input_citation,
                    html=False,
                    do_post_citation=False,
                    do_defendant=False
                )
                add_fix(case_path, {'citations': citation_objects})
                citations = citation_objects

    if 'citations' in DEBUG and len(citations):
        cite_strs = [str(cite.__dict__) for cite in citations]
        log_print(
            "  Citations found: %s" % ',\n                   '.join(cite_strs))
    elif 'citations' in DEBUG:
        log_print("  No citations found!")
    return citations


def get_case_name(complete_html_tree, case_path):
    path = '//head/title/text()'
    # Text looks like: 'In re 221A Holding Corp., Inc, 1 BR 506 - Dist.
    # Court, ED Pennsylvania 1979'
    s = complete_html_tree.xpath(path)[0].rsplit('-', 1)[0].rsplit(',', 1)[0]
    # returns 'In re 221A Holding Corp., Inc.'
    case_name = harmonize(clean_string(titlecase(s)))
    if not s:
        try:
            case_name = fixes[case_path]['case_name']
        except KeyError:
            if 'input_case_names' in DEBUG:
                if 'firefox' in DEBUG:
                    subprocess.Popen(['firefox', 'file://%s' % case_path],
                                     shell=False).communicate()
                input_case_name = raw_input(
                    '  No case name found. What should be here? ')
                input_case_name = unicode(input_case_name)
                add_fix(case_path, {'case_name': input_case_name})
                case_name = input_case_name

    if 'case_name' in DEBUG:
        log_print("  Case name: %s" % case_name)
    return case_name


def get_date_filed(clean_html_tree, citations, case_path=None, court=None):
    path = ('//center[descendant::text()[not('
              'starts-with(normalize-space(.), "No.") or '
              'starts-with(normalize-space(.), "Case No.") or '
              'starts-with(normalize-space(.), "Record No.")'
            ')]]')

    # Get a reasonable date range based on reporters in the citations.
    reporter_keys = [citation.reporter for citation in citations]
    range_dates = []
    for reporter_key in reporter_keys:
        for reporter in REPORTERS.get(EDITIONS.get(reporter_key)):
            try:
                range_dates.extend(reporter['editions'][reporter_key])
            except KeyError:
                # Fails when a reporter_key points to more than one reporter,
                # one of which doesn't have the edition queried. For example,
                # Wash. 2d isn't in REPORTERS['Wash.']['editions'][0].
                pass
    if range_dates:
        start, end = min(range_dates) - timedelta(weeks=(20 * 52)), max(
            range_dates) + timedelta(weeks=20 * 52)
        if end > now():
            end = now()

    dates = []
    for e in clean_html_tree.xpath(path):
        text = tostring(e, method='text', encoding='unicode')
        # Items like "February 4, 1991, at 9:05 A.M." stump the lexer in the
        # date parser. Consequently, we purge the word at, and anything after
        # it.
        text = re.sub(' at .*', '', text)

        # The parser recognizes numbers like 121118 as a date. This corpus
        # does not have dates in that format.
        text = re.sub('\d{5,}', '', text)

        # The parser can't handle 'Sept.' so we tweak it.
        text = text.replace('Sept.', 'Sep.')

        # The parser recognizes dates like December 3, 4, 1908 as
        # 2004-12-3 19:08.
        re_match = re.search('\d{1,2}, \d{1,2}, \d{4}', text)
        if re_match:
            # These are always date argued, thus continue.
            continue

        # The parser recognizes dates like October 12-13, 1948 as 2013-10-12,
        # not as 1948-10-12
        # See: https://www.courtlistener.com/scotus/9ANY/x/
        re_match = re.search('\d{1,2}-\d{1,2}, \d{4}', text)
        if re_match:
            # These are always date argued, thus continue.
            continue

        # Sometimes there's a string like: "Review Denied July 26, 2006.
        # Skip this.
        if 'denied' in text.lower():
            continue

        try:
            if range_dates:
                found = parse_dates.parse_dates(text, sane_start=start,
                                                sane_end=end)
            else:
                found = parse_dates.parse_dates(text, sane_end=now())
            if found:
                dates.extend(found)
        except UnicodeEncodeError:
            # If it has unicode is crashes dateutil's parser, but is unlikely
            # to be the date.
            pass

    # Get the date from our SCOTUS date table
    scotus_dates_found = []
    if not dates and court == 'scotus':
        for citation in citations:
            try:
                # Scotus dates are in the form of a list, since a single
                # citation can refer to several dates.
                found = scotus_dates["%s %s %s" % (
                    citation.volume, citation.reporter, citation.page)]
                if len(found) == 1:
                    scotus_dates_found.extend(found)
            except KeyError:
                pass
        if len(scotus_dates_found) == 1:
            dates = scotus_dates_found

    if not dates:
        # Try to grab the year from the citations, if it's the same in all of
        # them.
        years = set([citation.year for citation in citations if citation.year])
        if len(years) == 1:
            dates.append(datetime.datetime(list(years)[0], 1, 1))

    if not dates:
        try:
            dates = fixes[case_path]['dates']
        except KeyError:
            if 'input_dates' in DEBUG:
                # subprocess.Popen(
                #     ['firefox', 'file://%s' % case_path],
                #     shell=False
                # ).communicate()
                print '  No date found for: file://%s' % case_path
                input_date = raw_input('  What should be here (YYYY-MM-DD)? ')
                add_fix(case_path, {
                    'dates': [datetime.datetime.strptime(input_date, '%Y-%m-%d')]})
                dates = [datetime.datetime.strptime(input_date, '%Y-%m-%d')]
            if 'log_bad_dates' in DEBUG:
                # Write the failed case out to file.
                with open('missing_dates.txt', 'a') as out:
                    out.write('%s\n' % case_path)

    if dates:
        if 'date' in DEBUG:
            log_print(
                "  Using date: %s of dates found: %s" % (max(dates), dates))
        return max(dates)
    else:
        if 'date' in DEBUG:
            log_print("  No dates found")
        return []


def get_precedential_status():
    return 'Published'


def get_docket_number(html, case_path=None, court=None):
    try:
        path = '//center/text()'
        text_elements = html.xpath(path)
    except AttributeError:
        # Not an HTML element, instead it's a string
        text_elements = [html]
    docket_no_formats = ['Bankruptcy', 'C.A.', 'Case', 'Civ', 'Civil',
                         'Civil Action', 'Crim', 'Criminal Action',
                         'Docket', 'Misc', 'Record']
    regexes = [
        re.compile('((%s)( Nos?\.)?)|(Nos?(\.| )?)' % "|".join(
            map(re.escape, docket_no_formats)), re.IGNORECASE),
        re.compile('\d{2}-\d{2,5}'),  # WY-03-071, 01-21574
        re.compile('[A-Z]{2}-[A-Z]{2}'),  # CA-CR 5158
        re.compile('[A-Z]\d{2} \d{4}[A-Z]'),  # C86 1392M
        re.compile('\d{2} [A-Z] \d{4}'),  # 88 C 4330
        re.compile('[A-Z]-\d{2,4}'),  # M-47B (VLB), S-5408
        re.compile('[A-Z]\d{3,}', ),
        re.compile('[A-Z]{4,}'),  # SCBD #4983
        re.compile('\d{5,}'),  # 95816
        re.compile('\d{2},\d{3}'),  # 86,782
        re.compile('([A-Z]\.){4}'),  # S.C.B.D. 3020
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
        # False positive. Happens when there's no docket number and the date is incorrectly interpreted.
        docket_number = None
    elif docket_number == 'Not in Source':
        docket_number = None

    if not docket_number:
        try:
            docket_number = fixes[case_path]['docket_number']
        except KeyError:
            if 'northeastern' not in case_path and \
                            'federal_reporter/2d' not in case_path and \
                            court not in ['or', 'orctapp', 'cal'] and \
                    ('unsorted' not in case_path and court not in ['ind']) and \
                    ('pacific_reporter/2d' not in case_path and court not in [
                        'calctapp']):
                # Lots of missing docket numbers here.
                if 'input_docket_number' in DEBUG:
                    subprocess.Popen(['firefox', 'file://%s' % case_path],
                                     shell=False).communicate()
                    docket_number = raw_input(
                        '  No docket number found. What should be here? ')
                    add_fix(case_path, {'docket_number': docket_number})
                if 'log_bad_docket_numbers' in DEBUG:
                    with open('missing_docket_numbers.txt', 'a') as out:
                        out.write('%s\n' % case_path)

    if 'docket_number' in DEBUG:
        log_print('  Docket Number: %s' % docket_number)
    return docket_number


def get_court_object(html, citations=None, case_path=None, judge=None):
    """
       Parse out the court string, somehow, and then map it back to our internal ids
    """

    def string_to_key(str):
        """Given a string, tries to map it to a court key."""
        # State
        for regex, value in state_pairs:
            if re.search(regex, str):
                return value

        # Supreme Court
        if re.search('Supreme Court of (the )?United States', str) or \
                re.search('United States Supreme Court', str):
            return 'scotus'

        # Federal appeals
        if re.search('Court,? of Appeal', str) or \
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
            elif re.search('Ninth (Judicial )?Circuit', str):
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
            elif 'Columbia' in str:
                return 'cadc'
        elif 'Judicial Council of the Eighth Circuit' in str:
            return 'ca8'
        elif 'Judicial Council of the Ninth Circuit' in str or \
                re.search('Ninth Judicial Circuit', str):
            return 'ca9'

        # Federal district
        elif re.search('(^| )Distr?in?ct', str, re.I):
            for regex, value in fd_pairs:
                if re.search(regex, str):
                    return value
        elif 'D. Virgin Islands' in str:
            return 'vid'
        elif 'Territorial Court' in str:
            if 'Virgin Islands' in str:
                return 'vid'

        # Federal special
        elif 'United States Judicial Conference Committee' in str or \
                        'U.S. Judicial Conference Committee' in str:
            return 'usjc'
        elif re.search('Judicial Panel ((on)|(of)) Multidistrict Litigation',
                       str, re.I):
            return 'jpml'
        elif 'Court of Customs and Patent Appeals' in str:
            return 'ccpa'
        elif 'Court of Claims' in str or \
                        'Claims Court' in str:
            return 'cc'  # Cannot change
        elif 'United States Foreign Intelligence Surveillance Court' in str:
            return 'fiscr'  # Cannot change
        elif re.search('Court,? of,? International ?Trade', str):
            return 'cit'
        elif 'United States Customs Court' in str:
            return 'cusc'  # Cannot change?
        elif re.search('Special Court(\.|,)? Regional Rail Reorganization Act',
                       str):
            return 'reglrailreorgct'
        elif re.search('Military Commission Review', str):
            return 'mc'

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
                for regex, value in fb_pairs:
                    if re.search(regex, str):
                        return value
        else:
            return False

    path = '//center/p/b/text()'
    text_elements = html.xpath(path)
    court = None

    # 1: try using the citations as a clue (necessary first because calctapp calls itself simply, "Court of Appeal,
    # Second District")
    if citations:
        reporter_keys = [citation.canonical_reporter for citation in citations]
        if 'Cal. Rptr.' in reporter_keys or 'Cal. App.' in reporter_keys:
            # It's a california court, but which?
            for text_element in text_elements:
                text_element = clean_string(text_element).strip('.')
                if re.search('court of appeal', text_element, re.I):
                    court = 'calctapp'
                else:
                    court = 'cal'
        elif 'U.S.' in reporter_keys:
            court = 'scotus'

    # 2: Try using a bunch of regular expressions (this catches 95% of items)
    if not court:
        for text_element in text_elements:
            text_element = clean_string(text_element).strip('.')
            court = string_to_key(text_element)
            if court:
                break

    # 3: try the text elements joined together (works if there were line break problems)
    if not court:
        t = clean_string(' '.join(text_elements)).strip('.')
        court = string_to_key(t)

    # 4: Disambiguate by judge
    if not court and judge:
        court = disambiguate_by_judge(judge)
        if court and 'log_judge_disambiguations' in DEBUG:
            with open('disambiguated_by_judge.txt', 'a') as f:
                f.write('%s\t%s\t%s\n' % (
                    case_path, court, judge.encode('ISO-8859-1')))

    # 5: give up.
    if not court:
        try:
            court = fixes[case_path]['court']
        except KeyError:
            if 'input_court' in DEBUG:
                if 'firefox' in DEBUG:
                    subprocess.Popen(['firefox', 'file://%s' % case_path],
                                     shell=False).communicate()
                court = raw_input("No court identified! What should be here? ")
                add_fix(case_path, {'court': input})
            if 'log_bad_courts' in DEBUG:
                # Write the failed case out to file.
                court = 'test'
                with open('missing_courts.txt', 'a') as out:
                    out.write('%s\n' % case_path)

    if 'court' in DEBUG:
        log_print('  Court: %s' % court)

    return court


def get_judge(html, case_path=None):
    path = '//p[position() <= 60]//text()[not(parent::span)][not(ancestor::center)][not(ancestor::i)]'
    text_elements = html.xpath(path)

    # Get the first paragraph that starts with two uppercase letters after we've stripped out any star pagination.
    judge = None
    for t in text_elements:
        t = clean_string(t)
        judge, reason = get_judge_from_str(t)
        if judge:
            break
        if reason == 'TOO_LONG':
            # We've begun doing paragraphs...
            break

    if not judge:
        try:
            judge = fixes[case_path]['judge']
        except KeyError:
            if 'input_judge' in DEBUG:
                subprocess.Popen(['firefox', 'file://%s' % case_path],
                                 shell=False).communicate()
                judge = raw_input("No judge identified! What should be here? ")
                add_fix(case_path, {'judge': judge})
            if 'log_bad_judges' in DEBUG:
                with open('missing_judges.txt', 'a') as out:
                    out.write('%s\n' % case_path)

    if 'judge' in DEBUG:
        log_print('  Judge: %s' % judge)

    return judge


def import_law_box_case(case_path):
    """Open the file, get its contents, convert to XML and extract the meta data.

    Return a document object for saving in the database
    """
    raw_text = open(case_path).read()
    clean_html_tree, complete_html_tree, clean_html_str, body_text = get_html_from_raw_text(
        raw_text)

    sha1 = hashlib.sha1(clean_html_str).hexdigest()
    citations = get_citations_from_tree(complete_html_tree, case_path)
    judges = get_judge(clean_html_tree, case_path)
    court = get_court_object(clean_html_tree, citations, case_path, judges)

    doc = Document(
        source='L',
        sha1=sha1,
        html=clean_html_str,
        # we clear this field later, putting the value into html_lawbox.
        date_filed=get_date_filed(clean_html_tree, citations=citations,
                                  case_path=case_path, court=court),
        precedential_status=get_precedential_status(),
        judges=judges,
        download_url=case_path,
    )

    docket = Docket(
        docket_number=get_docket_number(
            clean_html_tree,
            case_path=case_path,
            court=court
        ),
        case_name=get_case_name(complete_html_tree, case_path),
        court=court,
    )

    # Necessary for dup_finder.
    path = '//p/text()'
    doc.body_text = ' '.join(clean_html_tree.xpath(path))

    # Add the dict of citations to the object as its attributes.
    citations_as_dict = map_citations_to_models(citations)
    for k, v in citations_as_dict.items():
        setattr(doc, k, v)

    doc.docket = docket

    return doc


def needs_dup_check(doc):
    """Checks the document to see whether we need to run our duplicate checking code.

    Based on minimum dates found in the CL database on 2013-10-10 using:
    courtlistener=> select "court_id", min(date_filed) from "Document" group by court_id order by min(date_filed);
    """
    start_dates = {'scotus': '1754-09-01', 'ca5': '1901-07-15',
                   'ca2': '1904-06-22', 'ca1': '1940-01-23',
                   'cafc': '1944-09-13', 'ca3': '1947-03-24',
                   'ca4': '1949-01-15', 'cadc': '1949-05-16',
                   'ca9': '1949-06-30', 'ca10': '1949-10-31',
                   'ca8': '1949-11-16', 'ca7': '1949-11-17',
                   'ca6': '1949-11-17', 'ccpa': '1949-12-12',
                   'eca': '1949-12-16', 'uscfc': '1960-01-20',
                   'mont': '1972-01-03', 'ca11': '1981-10-20',
                   'miss': '1982-02-04', 'tenncrimapp': '1988-12-08',
                   'tennctapp': '1993-01-28', 'vactapp': '1995-05-02',
                   'va': '1995-06-09', 'tenn': '1995-10-09',
                   'sd': '1996-01-10', 'nd': '1996-09-03', 'ind': '1997-12-31',
                   'or': '1998-01-08',
                   'ndctapp': '1998-07-07', 'cit': '1999-01-05',
                   'cavc': '2000-01-12', 'mich': '2000-12-18',
                   'tex': '2001-10-02', 'ariz': '2002-01-09',
                   'fiscr': '2002-11-18', 'armfor': '2003-11-18',
                   'idahoctapp': '2006-06-15', 'vt': '2006-08-04',
                   'idaho': '2006-11-28', 'nmctapp': '2007-08-31',
                   'nm': '2008-12-01', 'hawapp': '2010-01-04',
                   'haw': '2010-01-07', 'cal': '2011-04-22',
                   'washctapp': '2011-11-08', 'ri': '2012-10-05',
                   'bap9': '2012-10-10', 'wyo': '2012-12-28',
                   'alaska': '2013-01-09', 'wva': '2013-01-14',
                   'utah': '2013-01-15', 'tax': '2013-01-30',
                   'ill': '2013-02-04', 'wis': '2013-02-13',
                   'calctapp': '2013-02-25', 'wash': '2013-02-28',
                   'nev': '2013-03-13', 'nebctapp': '2013-04-02',
                   'neb': '2013-04-05', 'njsuperctappdiv': '2013-07-30',
                   'nj': '2013-07-30', 'ark': '2013-08-02',
                   'arkctapp': '2013-08-28', 'illappct': '2013-09-19', }
    try:
        if doc.date_filed >= datetime.datetime.strptime(
                start_dates[doc.court_id], '%Y-%m-%d'):
            return True
    except KeyError:
        pass
    return False


def find_duplicates(doc, case_path):
    """Return True if it should be saved, else False"""
    log_print("Running duplicate checks...")

    # 1. Is the item completely outside of the current corpus?
    if not needs_dup_check(doc):
        log_print(
            "  - Not a duplicate: Outside of date range for selected court.")
        return []
    else:
        log_print(
            "  - Could be a duplicate: Inside of date range for selected court.")

    # 2. Can we find any duplicates and information about them?
    stats, candidates = dup_finder.get_dup_stats(doc)
    if len(candidates) == 0:
        log_print("  - Not a duplicate: No candidate matches found.")
        return []
    elif len(candidates) == 1:

        if doc.docket.docket_number and candidates[0].get(
                'docketNumber') is not None:
            # One in the other or vice versa
            if (re.sub("(\D|0)", "", candidates[0]['docketNumber']) in
                    re.sub("(\D|0)", "", doc.docket.docket_number)) or \
                    (re.sub("(\D|0)", "", doc.docket.docket_number) in
                         re.sub("(\D|0)", "", candidates[0]['docketNumber'])):
                log_print(
                    "  - Duplicate found: Only one candidate returned and docket number matches.")
                return [candidates[0]['id']]
            else:
                if doc.docket.court_id == 'cit':
                    # CIT documents have neutral citations in the database. Look that up and compare against that.
                    candidate_doc = Document.objects.get(
                        pk=candidates[0]['id'])
                    if doc.citation.neutral_cite and candidate_doc.citation.neutral_cite:
                        if candidate_doc.neutral_cite in doc.docket.docket_number:
                            log_print(
                                '  - Duplicate found: One candidate from CIT and its neutral citation matches the new document\'s docket number.')
                            return [candidates[0]['id']]
                else:
                    log_print(
                        "  - Not a duplicate: Only one candidate but docket number differs.")
                return []
        else:
            log_print("  - Skipping docket_number dup check.")

        if doc.case_name == candidates[0].get('caseName'):
            log_print(
                "  - Duplicate found: Only one candidate and case name is a perfect match.")
            return [candidates[0]['id']]

        if dup_helpers.case_name_in_candidate(doc.case_name,
                                              candidates[0].get('caseName')):
            log_print(
                "  - Duplicate found: All words in new document's case name are in the candidate's case name (%s)" %
                candidates[0].get('caseName'))
            return [candidates[0]['id']]

    else:
        # More than one candidate.
        if doc.docket.docket_number:
            dups_by_docket_number = dup_helpers.find_same_docket_numbers(doc,
                                                                         candidates)
            if len(dups_by_docket_number) > 1:
                log_print(
                    "  - Duplicates found: %s candidates matched by docket number." % len(
                        dups_by_docket_number))
                return [can['id'] for can in dups_by_docket_number]
            elif len(dups_by_docket_number) == 1:
                log_print(
                    "  - Duplicate found: Multiple candidates returned, but one matched by docket number.")
                return [dups_by_docket_number[0]['id']]
            else:
                log_print(
                    "  - Could be a duplicate: Unable to find good match via docket number.")
        else:
            log_print("  - Skipping docket_number dup check.")

    # 3. Filter out obviously bad cases and then pass remainder forward for manual review.

    filtered_candidates, filtered_stats = dup_helpers.filter_by_stats(
        candidates, stats)
    log_print("  - %s candidates before filtering. With stats: %s" % (
        stats['candidate_count'], stats['cos_sims']))
    log_print("  - %s candidates after filtering. Using filtered stats: %s" % (
        filtered_stats['candidate_count'],
        filtered_stats['cos_sims']))
    if len(filtered_candidates) == 0:
        log_print(
            "  - Not a duplicate: After filtering no good candidates remained.")
        return []
    elif len(filtered_candidates) == 1 and filtered_stats['cos_sims'][
        0] > 0.93:
        log_print(
            "  - Duplicate found: One candidate after filtering and cosine similarity is high (%s)" %
            filtered_stats['cos_sims'][0])
        return [filtered_candidates[0]['id']]
    else:
        duplicates = []
        high_sims_count = len(
            [sim for sim in filtered_stats['cos_sims'] if sim > 0.98])
        low_sims_count = len(
            [sim for sim in filtered_stats['cos_sims'] if sim < 0.95])
        for k in range(0, len(filtered_candidates)):
            if all([(high_sims_count == 1),  # Only one high score
                    (low_sims_count == filtered_stats['candidate_count'] - 1)
                    # All but one have low scores
                    ]):
                # If only one of the items is very high, then we can ignore the others and assume it's right
                if filtered_stats['cos_sims'][k] > 0.98:
                    duplicates.append(filtered_candidates[k]['id'])
                    break
                else:
                    # ignore the others
                    continue
            else:
                # Have to determine by "hand"
                log_print("  %s) Case name: %s" % (k + 1, doc.case_name))
                log_print(
                    "                 %s" % filtered_candidates[k]['caseName'])
                log_print("      Docket nums: %s" % doc.docket.docket_number)
                log_print("                   %s" % filtered_candidates[k].get(
                    'docketNumber', 'None'))
                log_print(
                    "      Cosine Similarity: %s" % filtered_stats['cos_sims'][
                        k])
                log_print("      Candidate URL: file://%s" % case_path)
                log_print("      Match URL: https://www.courtlistener.com%s" %
                          (filtered_candidates[k]['absolute_url']))

                choice = raw_input("Is this a duplicate? [Y/n]: ")
                choice = choice or "y"
                if choice == 'y':
                    duplicates.append(filtered_candidates[k]['id'])

        if len(duplicates) == 0:
            log_print(
                "  - Not a duplicate: Manual determination found no matches.")
            return []
        elif len(duplicates) == 1:
            log_print(
                "  - Duplicate found: Manual determination found one match.")
            return [duplicates[0]]
        elif len(duplicates) > 1:
            log_print(
                "  - Duplicates found: Manual determination found %s matches." % len(
                    duplicates))
            return duplicates


def main():
    parser = argparse.ArgumentParser(
        description='Import the corpus provided by lawbox')
    parser.add_argument('-s', '--simulate', default=False, required=False,
                        action='store_true',
                        help='Run the code in simulate mode, making no permanent changes.')
    parser.add_argument('-d', '--dir', type=readable_dir,
                        help='The directory where the lawbox bulk data can be found.')
    parser.add_argument('-f', '--file', type=str, default="index.txt",
                        required=False, dest="file_name",
                        help="The file that has all the URLs to import, one per line.")
    parser.add_argument('-l', '--line', type=int, default=1, required=False,
                        help='If provided, this will be the line number in the index file where we resume processing.')
    parser.add_argument('-r', '--resume', default=False, required=False,
                        action='store_true',
                        help='Use the saved marker to resume operation where it last failed.')
    parser.add_argument('-x', '--random', default=False, required=False,
                        action='store_true',
                        help='Pick cases randomly rather than serially.')
    parser.add_argument('-m', '--marker', type=str,
                        default='lawbox_progress_marker.txt', required=False,
                        help="The name of the file that tracks the progress (useful if multiple versions run at same time)")
    parser.add_argument('-e', '--end', type=int, required=False,
                        default=2000000,
                        help="An optional endpoint for an importer.")
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
        def generate_random_line(file_name):
            while True:
                total_bytes = os.stat(file_name).st_size
                random_point = random.randint(0, total_bytes)
                f = open(file_name)
                f.seek(random_point)
                f.readline()  # skip this line to clear the partial line
                yield f.readline().strip()

        def case_generator(line_number):
            """Yield cases from the index file."""
            enumerated_line_number = line_number - 1  # The enumeration is zero-index, but files are one-index.
            index_file = open(args.file_name)
            for i, line in enumerate(index_file):
                if i >= enumerated_line_number:
                    yield line.strip()

        if args.random:
            cases = generate_random_line(args.file_name)
            i = 0
        elif args.resume:
            with open(args.marker) as marker:
                resume_point = int(marker.read().strip())
            cases = case_generator(resume_point)
            i = resume_point
        else:
            cases = case_generator(args.line)
            i = args.line

    for case_path in cases:
        if i % 1000 == 0:
            db.reset_queries()  # Else we leak memory when DEBUG is True

        if 'counter' in DEBUG:  # and i % 1000 == 0:
            log_print("\n%s: Doing case (%s): file://%s" % (
                datetime.datetime.now(), i, case_path))
        try:
            doc = import_law_box_case(case_path)
            duplicates = find_duplicates(doc, case_path)
            if not args.simulate:
                if len(duplicates) == 0:
                    doc.html_lawbox, blocked = anonymize(doc.html)
                    doc.html = ''
                    if blocked:
                        doc.blocked = True
                        doc.date_blocked = now()
                        # Save nothing to the index for now (it'll get done
                        # when we find citations)
                    doc.save(index=False)
                if len(duplicates) == 1:
                    dup_helpers.merge_cases_simple(doc, duplicates[0])
                if len(duplicates) > 1:
                    # complex_merge
                    if 'log_multimerge' in DEBUG:
                        with open('index_multimerge.txt', 'a') as log:
                            log.write('%s\n' % case_path)
            if args.resume:
                # Don't change the progress marker unless you're in resume mode
                with open(args.marker, 'w') as marker:
                    marker.write(
                        str(i + 1))  # Files are one-index, not zero-index
            with open('lawbox_fix_file.pkl', 'wb') as fix_file:
                pickle.dump(fixes, fix_file)
            i += 1
            if i == args.end:
                log_print(
                    "Hit the endpoint after importing number %s. Breaking." % i)
                break
        except Exception, err:
            log_print(traceback.format_exc())
            exit(1)


if __name__ == '__main__':
    main()
