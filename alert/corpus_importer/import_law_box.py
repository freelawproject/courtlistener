from juriscraper.lib.string_utils import clean_string, harmonize, titlecase
import os
import re
import traceback
from lxml import html
from alert.citations.find_citations import get_citations

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import argparse
import fnmatch
import hashlib
from lxml.etree import XMLSyntaxError
from lxml.html.clean import Cleaner
import os
from lxml.html import tostring

from alert.search.models import Document, Citation

DEBUG = 1


def get_west_cite(complete_html_tree):
    path = '//center//text()'
    text = ' '.join(complete_html_tree.xpath(path))
    citations = get_citations(text, html=False, do_post_citation=False, do_defendant=False)
    if not citations:
        path = '//title/text()'
        text = complete_html_tree.xpath(path)[0]
        citations = get_citations(text, html=False, do_post_citation=False, do_defendant=False)
        if not citations:
            raise
    if DEBUG >= 1:
        cite_strs = [str(cite) for cite in citations]
        print "Citations found: %s" % ', '.join(cite_strs)

    return citations


def get_case_name(complete_html_tree):
    path = '//head/title/text()'
    # Text looks like: 'In re 221A Holding Corp., Inc, 1 BR 506 - Dist. Court, ED Pennsylvania 1979'
    s = complete_html_tree.xpath(path)[0].rsplit('-', 1)[0].rsplit(',', 1)[0]
    # returns 'In re 221A Holding Corp., Inc.'
    s = harmonize(clean_string(titlecase(s)))
    if DEBUG >= 1:
        print "Case name: %s" % s
    return s


def get_date_filed(html_tree):
    return None


def get_precedential_status(html_tree):
    return None


def get_docket_number(html_tree):
    return None


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

    doc = Document(
        source='LB',
        sha1=sha1,
        #court=get_court_object(html_tree),
        html=clean_html_str,
        # date_filed=get_date_filed(html_tree),
        precedential_status=get_precedential_status(clean_html_tree)
    )
    cite = Citation(
        west_cite=get_west_cite(complete_html_tree),
        case_name=get_case_name(complete_html_tree),
        docket_number=get_docket_number(clean_html_tree)
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
            print "Doing case (%s): file://%s" % (i, case_path)
        try:
            doc = import_law_box_case(case_path)
            i += 1
        finally:
            traceback.format_exc()
            with open('lawbox_progress_marker.txt', 'w') as marker:
                marker.write(str(i))

        save_it = check_duplicate(doc)  # Need to write this method?
        #exit()
        if save_it and not args.simulate:
            # Not a dup, save to disk, Solr, etc.
            doc.cite.save()  # I think this is the save routine?
            doc.save()  # Do we index it here, or does that happen automatically?


if __name__ == '__main__':
    main()
