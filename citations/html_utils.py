#!/usr/bin/env python
# encoding: utf-8

from BeautifulSoup import BeautifulSoup
from HTMLParser import HTMLParser
import re

# TODO(rowyn): Change this to use lxml

#
# Filter to keep only visible terms on the page
# Returns an array where every element is a visible phrase (one or more words) in the html document.
#
def html_filter(term):
    # Filter out contents of script and style tags
    if term.parent.name in ['style', 'link', 'head', '[document]', 'script']:
        return False
    # Filter out comments, newlines, and standalone special characters (e.g. &para;)
    if re.match('<!--', str(term)):
        return False
    return True

#
# Get visible text content from the html
#
def get_visible_text(html_content):
    soup = BeautifulSoup(html_content)
    strings = soup.findAll(text=True)
    visible_strings = filter(html_filter, strings)
    return HTMLParser().unescape(''.join(visible_strings))
