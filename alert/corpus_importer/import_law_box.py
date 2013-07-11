from juriscraper.lib.string_utils import clean_string, harmonize, titlecase
import os
import re
from lxml import html

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import argparse
import fnmatch
import hashlib
from lxml.etree import XMLSyntaxError
from lxml.html.clean import Cleaner
import os
from lxml.html import tostring

from alert.search.models import Document, Citation


def get_west_cite(html_tree):
    return None


def get_case_name(complete_html_tree):
    path = '//head/title/text()'
    # Text looks like: 'In re 221A Holding Corp., Inc, 1 BR 506 - Dist. Court, ED Pennsylvania 1979'
    s = complete_html_tree.xpath(path)[0].rsplit('-', 1)[0].rsplit(',', 1)[0]
    # returns 'In re 221A Holding Corp., Inc.'
    s = harmonize(clean_string(titlecase(s)))
    return s


def get_date_filed(html_tree):
    return None


def get_precedential_status(html_tree):
    return None


def get_docket_number(html_tree):
    return None


def get_court_object(html_tree):
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
        west_cite=get_west_cite(case_path),
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


def case_generator(dir_root):
    """Yield cases, one by one to the importer by recursing and iterating the import directory"""
    for root, dirnames, filenames in os.walk(dir_root):
        for filename in fnmatch.filter(filenames, '*'):
            yield os.path.join(root, filename)


def check_duplicate(doc):
    """Return true if it should be saved, else False"""
    return True


def main():
    parser = argparse.ArgumentParser(description='Import the corpus provided by lawbox')
    parser.add_argument('-s', '--simulate', default=False, required=False, action='store_true',
                        help='Run the code in simulate mode, making no permanent changes.')
    parser.add_argument('-r', '--root', type=readable_dir, default='/sata/lawbox/dump/',
                        help='The directory where the lawbox dump can be found.')
    args = parser.parse_args()

    for case_path in case_generator(args.root):
        doc = import_law_box_case(case_path)
        save_it = check_duplicate(doc)  # Need to write this method?
        #exit()
        if save_it and not args.simulate:
            # Not a dup, save to disk, Solr, etc.
            doc.cite.save()  # I think this is the save routine?
            doc.save()  # Do we index it here, or does that happen automatically?


if __name__ == '__main__':
    main()
