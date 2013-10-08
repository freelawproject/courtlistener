import os
import sys
import time

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alert.settings")

from juriscraper.lib.string_utils import clean_string, harmonize, titlecase
from juriscraper.lib import parse_dates
import pickle
import random
import re
import subprocess
import traceback
from django.utils.timezone import now
from lxml import html
from alert.citations.constants import EDITIONS, REPORTERS
from alert.citations.find_citations import get_citations
from datetime import date, timedelta
from alert.corpus_importer.court_regexes import fd_pairs, state_pairs, disambiguate_by_judge, fb_pairs
from alert.corpus_importer.judge_extractor import get_judge_from_str
from alert.lib.import_lib import map_citations_to_models

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import argparse
import datetime
import fnmatch
import hashlib
from lxml.html.clean import Cleaner
from lxml.html import tostring

from alert.search.models import Document, Citation, Court


DEBUG = [
    'judge',
    'citations',
    'case_name',
    'date',
    'docket_number',
    'court',
    #'input_citations',
    'input_dates',
    #'input_docket_number',
    'input_court',
    #'log_bad_citations',
    #'log_bad_courts',
    #'log_judge_disambiguations',
    #'log_bad_dates',
    #'log_bad_docket_numbers',
    #'log_bad_judges',
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
    with open('scotus_dates.csv') as scotus_date_file:
        for line in scotus_date_file:
            citation, date_filed = [line.strip() for line in line.split('|')]
            date_filed = datetime.datetime.strptime(date_filed, '%Y-%m-%d').date()
            try:
                # If we get fail to get a KeyError, we append to the list we got back, else, we create such a list.
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
        'path/to/some/case.html': {'docket_number': None, 'date_filed': date(1982, 6, 9)},
    }
    """
    if case_path in fixes:
        fixes[case_path].update(fix_dict)
    else:
        fixes[case_path] = fix_dict


def get_citations_from_tree(complete_html_tree, case_path):
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
        try:
            citations = fixes[case_path]['citations']
        except KeyError:
            if 'input_citations' in DEBUG:
                subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
                input_citation = raw_input('  No citations found. What should be here? ')
                citation_objects = get_citations(input_citation, html=False, do_post_citation=False, do_defendant=False)
                add_fix(case_path, {'citations': citation_objects})
                citations = citation_objects

    if 'citations' in DEBUG and len(citations):
        cite_strs = [str(cite.__dict__) for cite in citations]
        print "  Citations found: %s" % ',\n                   '.join(cite_strs)
    elif 'citations' in DEBUG:
        print "  No citations found!"
    return citations


def get_case_name(complete_html_tree):
    path = '//head/title/text()'
    # Text looks like: 'In re 221A Holding Corp., Inc, 1 BR 506 - Dist. Court, ED Pennsylvania 1979'
    s = complete_html_tree.xpath(path)[0].rsplit('-', 1)[0].rsplit(',', 1)[0]
    # returns 'In re 221A Holding Corp., Inc.'
    s = harmonize(clean_string(titlecase(s)))
    if 'case_name' in DEBUG:
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
        start, end = min(range_dates) - timedelta(weeks=(20 * 52)), max(range_dates) + timedelta(weeks=20 * 52)
        if end > now():
            end = now()

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
                found = parse_dates.parse_dates(text, sane_end=now())
            if found:
                dates.extend(found)
        except UnicodeEncodeError:
            # If it has unicode is crashes dateutil's parser, but is unlikely to be the date.
            pass

    # Get the date from our SCOTUS date table
    if not dates and court == 'scotus':
        for citation in citations:
            try:
                dates.append(scotus_dates["%s %s %s" % (citation.volume, citation.reporter, citation.page)])
            except KeyError:
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
            if 'input_dates' in DEBUG:
                subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
                input_date = raw_input('  No date found. What should be here (YYYY-MM-DD)? ')
                add_fix(case_path, {'dates': [datetime.datetime.strptime(input_date, '%Y-%m-%d').date()]})
                dates = [input_date]
            if 'log_bad_dates' in DEBUG:
                # Write the failed case out to file.
                with open('missing_dates.txt', 'a') as out:
                    out.write('%s\n' % case_path)

    if dates:
        if 'date' in DEBUG:
            print "  Using date: %s of dates found: %s" % (max(dates), dates)
        return max(dates)
    else:
        if 'date' in DEBUG:
            print "  No dates found"
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
            if 'northeastern' not in case_path and \
                    'federal_reporter/2d' not in case_path and \
                    court not in ['or', 'orctapp', 'cal'] and \
                    ('unsorted' not in case_path and court not in ['ind']) and \
                    ('pacific_reporter/2d' not in case_path and court not in ['calctapp']):
                # Lots of missing docket numbers here.
                if 'input_docket_number' in DEBUG:
                    subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
                    docket_number = raw_input('  No docket number found. What should be here? ')
                    add_fix(case_path, {'docket_number': docket_number})
                if 'log_bad_docket_numbers' in DEBUG:
                    with open('missing_docket_numbers.txt', 'a') as out:
                        out.write('%s\n' % case_path)

    if 'docket_number' in DEBUG:
        print '  Docket Number: %s' % docket_number
    return docket_number


def get_court_object(html, citations=None, case_path=None, judge=None):
    """
       Parse out the court string, somehow, and then map it back to our internal ids
    """
    path = '//center/p/b/text()'
    text_elements = html.xpath(path)

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
            elif 'Court of Appeals of Columbia' in str:
                return 'cadc'
        elif 'Judicial Council of the Eighth Circuit' in str:
            return 'ca8'
        elif 'Judicial Council of the Ninth Circuit' in str or \
                re.search('Ninth (Judicial )?Circuit', str):
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
        elif re.search('Judicial Panel ((on)|(of)) Multidistrict Litigation', str, re.I):
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
        elif re.search('Special Court(\.|,)? Regional Rail Reorganization Act', str):
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

    court = None
    for t in text_elements:
        t = clean_string(t).strip('.')
        court = string_to_key(t)
        if court:
            break

    # Round two: try the text elements joined together
    t = clean_string(' '.join(text_elements)).strip('.')
    court = string_to_key(t)

    if not court and citations:
        # Round three: try using the citations as a clue
        reporter_keys = [citation.canonical_reporter for citation in citations]
        if 'Cal. Rptr.' in reporter_keys:
            # It's a california court.
            for t in text_elements:
                t = clean_string(t).strip('.')
                if re.search('court of appeal', t, re.I):
                    court = 'calctapp'

    if not court and judge:
        court = disambiguate_by_judge(judge)
        if court and 'log_judge_disambiguations' in DEBUG:
            with open('disambiguated_by_judge.txt', 'a') as f:
                f.write('%s\t%s\t%s\n' % (case_path, court, judge.encode('ISO-8859-1')))

    if not court:
        # Fine, give up!
        try:
            court = fixes[case_path]['court']
        except KeyError:
            if 'input_court' in DEBUG:
                subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
                input_court = raw_input("No court identified! What should be here? ")
                add_fix(case_path, {'court': input_court})
            if 'log_bad_courts' in DEBUG:
                # Write the failed case out to file.
                court = 'test'
                with open('missing_courts.txt', 'a') as out:
                    out.write('%s\n' % case_path)

    if 'court' in DEBUG:
        print '  Court: %s' % court

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
                subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
                judge = raw_input("No judge identified! What should be here? ")
                add_fix(case_path, {'judge': judge})
            if 'log_bad_judges' in DEBUG:
                with open('missing_judges.txt', 'a') as out:
                    out.write('%s\n' % case_path)

    if 'judge' in DEBUG:
        print '  Judge: %s' % judge

    return judge


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
                      remove_tags=('a', 'body', 'font', 'noscript',),
                      kill_tags=('title',),)
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
    citations = get_citations_from_tree(complete_html_tree, case_path)
    judges = get_judge(clean_html_tree, case_path)
    court = get_court_object(clean_html_tree, citations, case_path, judges)

    doc = Document(
        source='LB',
        sha1=sha1,
        court_id=court,
        html=clean_html_str,
        date_filed=get_date_filed(clean_html_tree, citations=citations, case_path=case_path, court=court),
        precedential_status=get_precedential_status(),
        judges=judges,
    )

    cite = Citation(
        case_name=get_case_name(complete_html_tree),
        docket_number=get_docket_number(clean_html_tree, case_path=case_path, court=court)
    )

    # Add the dict of citations to the object as its attributes.
    citations_as_dict = map_citations_to_models(citations)
    for k, v in citations_as_dict.iteritems():
        setattr(cite, k, v)

    doc.citation = cite

    return doc, cite


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
    parser.add_argument('-f', '--file', type=str, default="index.txt", required=False, dest="file_name",
                        help="The file that has all the URLs to import, one per line.")
    parser.add_argument('-l', '--line', type=int, default=1, required=False,
                        help='If provided, this will be the line number in the index file where we resume processing.')
    parser.add_argument('-r', '--resume', default=False, required=False, action='store_true',
                        help='Use the saved marker to resume operation where it last failed.')
    parser.add_argument('-x', '--random', default=False, required=False, action='store_true',
                        help='Pick cases randomly rather than serially.')
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
                random_point = random.randint( 0, total_bytes )
                f = open(file_name)
                f.seek(random_point)
                f.readline()  # skip this line to clear the partial line
                yield f.readline().strip()

        def case_generator(line_number):
            """Yield cases from the index file."""
            index_file = open(args.file_name)
            for i, line in enumerate(index_file):
                if i > line_number:
                    yield line.strip()

        if args.random:
            cases = generate_random_line(args.file_name)
            i = 0
        elif args.resume:
            with open('lawbox_progress_marker.txt') as marker:
                resume_point = int(marker.read().strip())
            cases = case_generator(resume_point)
            i = resume_point
        else:
            cases = case_generator(args.line)
            i = args.line

    for case_path in cases:
        if 'counter' in DEBUG:  #and i % 1000 == 0:
            print "\n%s: Doing case (%s): file://%s" % (datetime.datetime.now(), i, case_path)
        try:
            doc, cite = import_law_box_case(case_path)
            with open('lawbox_progress_marker.txt', 'w') as marker:
                marker.write(str(i))
            with open('lawbox_fix_file.pkl', 'wb') as fix_file:
                pickle.dump(fixes, fix_file)
            i += 1
        except Exception, err:
            print traceback.format_exc()
            exit(1)

        save_it = check_duplicate(doc)  # Need to write this method?
        if save_it and not args.simulate:
            # Not a dup, save to disk, Solr, etc.
            cite.save()
            doc.citation = cite
            doc.save()  # Do we index it here, or does that happen automatically?
            print 'Saved as: %s' % doc


if __name__ == '__main__':
    main()
