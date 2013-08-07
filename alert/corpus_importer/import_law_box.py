from juriscraper.lib.string_utils import clean_string, harmonize, titlecase
from juriscraper.lib import parse_dates
import os
import re
import subprocess
import traceback
from lxml import html
from alert.citations.constants import EDITIONS, REPORTERS
from alert.citations.find_citations import get_citations
from datetime import date, timedelta

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import argparse
import fnmatch
import hashlib
from lxml.etree import XMLSyntaxError
from lxml.html.clean import Cleaner
import os
from lxml.html import tostring

from alert.search.models import Document, Citation


DEBUG = 2


def get_west_cite(complete_html_tree):
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
    if DEBUG >= 1:
        cite_strs = [str(cite.__dict__) for cite in citations]
        print "  Citations found: %s" % ',\n                   '.join(cite_strs)

    return citations


def get_case_name(complete_html_tree):
    path = '//head/title/text()'
    # Text looks like: 'In re 221A Holding Corp., Inc, 1 BR 506 - Dist. Court, ED Pennsylvania 1979'
    s = complete_html_tree.xpath(path)[0].rsplit('-', 1)[0].rsplit(',', 1)[0]
    # returns 'In re 221A Holding Corp., Inc.'
    s = harmonize(clean_string(titlecase(s)))
    if DEBUG >= 1:
        print "  Case name: %s" % s
    return s


def get_date_filed(clean_html_tree, citations, case_path=None):
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
    if not dates:
        # Try to grab the year from the citations, if it's the same in all of them.
        years = set([citation.year for citation in citations if citation.year])
        if len(years) == 1:
            dates.append(date(list(years)[0], 1, 1))
    if not dates:
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
    if not dates:
        # Still no luck?
        if DEBUG >= 2:
            subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
        raise

    if DEBUG >= 1:
        print "  Using date: %s of dates found: %s" % (max(dates), dates)
    return max(dates)


def get_precedential_status(html_tree):

    return None


def get_docket_number(html, case_path=None):
    try:
        path = '//center/text()'
        text_elements = html.xpath(path)
    except AttributeError:
        # Not an HTML element, instead it's a string
        text_elements = [html]
    docket_no_formats = ['Bankruptcy', 'Docket No.', 'Record No.', 'Case No.', 'Nos.', 'No.', 'NO.', ',']
    docket_regex = re.compile('(%s)' % "|".join(map(re.escape, docket_no_formats)), re.IGNORECASE)

    docket_number = None

    for t in text_elements:
        t = clean_string(t).strip('.')
        strings = docket_regex.split(t)
        for format in docket_no_formats:
            if format in strings:
                docket_number = '%s%s' % (format, strings[strings.index(format) + 1])

    if not docket_number:
        for t in text_elements:
            t = clean_string(t).strip('.')
            # Sometimes it's just a number on a line all alone
            clean_t = re.sub('-|\.', '', t)
            if clean_t.isdigit():
                # Only digits remain after purging a few punctuation marks.
                docket_number = t

    if not docket_number:
        # sometimes it's more like 88 C 4330, but we must distinguish from dates
        for t in text_elements:
            t = clean_string(t).strip('.')
            if t[0].isdigit() and t[-1].isdigit():
                # If it starts and ends with a digit, it's probably a docket number.
                docket_number = t

    if not docket_number:
        if DEBUG >= 2:
            subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
        raw_input('  No docket number. Press <enter> to continue.')
    if DEBUG >= 1:
        print '  Docket Number: %s' % docket_number
    return docket_number


def get_court_object(html_tree):
    """
       1. Commonwealth Court of Pennsylvania: https://en.wikipedia.org/wiki/Commonwealth_Court_of_Pennsylvania
    """
    return None


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
    citations = get_west_cite(complete_html_tree)

    doc = Document(
        source='LB',
        sha1=sha1,
        #court=get_court_object(html_tree),
        html=clean_html_str,
        date_filed=get_date_filed(clean_html_tree, citations, case_path),
        precedential_status=get_precedential_status(clean_html_tree)
    )

    cite = Citation(
        federal_cite_one=citations,
        case_name=get_case_name(complete_html_tree),
        docket_number=get_docket_number(clean_html_tree, case_path=case_path)
    )

    doc.cite = cite

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
            index_file = open('index.txt')
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
        if DEBUG >= 1:
            print "\nDoing case (%s): file://%s" % (i, case_path)
        try:
            doc = import_law_box_case(case_path)
            i += 1
        finally:
            traceback.format_exc()
            with open('lawbox_progress_marker.txt', 'w') as marker:
                marker.write(str(i))

        save_it = check_duplicate(doc)  # Need to write this method?
        if save_it and not args.simulate:
            # Not a dup, save to disk, Solr, etc.
            doc.cite.save()  # I think this is the save routine?
            doc.save()  # Do we index it here, or does that happen automatically?


if __name__ == '__main__':
    main()
