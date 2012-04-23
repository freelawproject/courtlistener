#!/usr/bin/env python
# encoding: utf-8

import os
import re
import sys

from juriscraper.lib.html_utils import get_visible_text
import reporter_tokenizer

FORWARD_SEEK = 20

BACKWARD_SEEK = 70 # Average case name length in the db is 67

STOP_TOKENS = ['v', 're', 'parte', 'denied', 'citing', "aff'd", "affirmed",
               "remanded", "see", "granted", "dismissed"]

class Citation(object):
    '''Convenience class which represents a single citation found in a document.
    
    '''
    def __init__(self, reporter, page, volume):
        self.reporter = reporter
        self.volume = volume
        self.page = page
        self.extra = None
        self.defendant = None
        self.plaintiff = None
        self.court = None
        self.year = None
        self.match_url = "#"

    def base_citation(self):
        return u"%d %s %d" % (self.volume, self.reporter, self.page)

    def as_regex(self):
        return r"%d\s+%s\s+%d" % (self.volume, self.reporter, self.page)

    def as_html(self):
        template = u'<span class="volume">%(volume)d</span> ' \
            u'<span class="reporter">%(reporter)s</span> ' \
            u'<span class="page">%(page)d</span>'
        inner_html = template % self.__dict__
        link = u'<a href="%s">' % self.match_url + inner_html + u'</a>'
        return u'<span class="citation">' + link + '</span>'

    def __repr__(self):
        print_string = self.base_citation()
        if self.defendant:
            print_string = u' '.join([self.defendant, print_string])
            if self.plaintiff:
                print_string = u' '.join([self.plaintiff, 'v.', print_string])
        if self.extra:
            print_string = u' '.join([print_string, self.extra])
        if self.court and self.year:
            paren = u"(%s %d)" % (self.court, self.year)
        elif self.year:
            paren = u'(%d)' % self.year
        elif self.court:
            paren = u"(%s)" % self.court
        else:
            paren = ''
        print_string = u' '.join([print_string, paren])
        return print_string.encode("utf-8")

# Adapted from nltk Penn Treebank tokenizer
def strip_punct(text):
    #starting quotes
    text = re.sub(r'^\"', r'', text)
    text = re.sub(r'(``)', r'', text)
    text = re.sub(r'([ (\[{<])"', r'', text)

    #punctuation
    text = re.sub(r'\.\.\.', r'', text)
    text = re.sub(r'[,;:@#$%&]', r'', text)
    text = re.sub(r'([^\.])(\.)([\]\)}>"\']*)\s*$', r'\1', text)
    text = re.sub(r'[?!]', r'', text)

    text = re.sub(r"([^'])' ", r"", text)

    #parens, brackets, etc.
    text = re.sub(r'[\]\[\(\)\{\}\<\>]', r'', text)
    text = re.sub(r'--', r'', text)

    #ending quotes
    text = re.sub(r'"', "", text)
    text = re.sub(r'(\S)(\'\')', r'', text)

    return text.strip()

def get_court(paren_string, year):
    if year is None:
        return strip_punct(paren_string)
    year_index = paren_string.find(str(year))
    return strip_punct(paren_string[:year_index])

def get_year(token):
    '''Given a string token, look for a valid 4-digit number at the start and 
    return its value.
    '''
    token = strip_punct(token)
    if not token.isdigit():
        # Sometimes funny stuff happens?
        token = re.sub(r'(\d{4}).*', r'\1', token)
        if not token.isdigit():
            return None
    if len(token) != 4:
        return None
    year = int(token)
    if year < 1754: # Earliest case in the database
        return None
    return year

def add_post_citation(citation, words, reporter_index):
    '''Add to a citation object any additional information found after the base
    citation, including court, year, and possibly page range.

    Examples:
        Full citation: 123 U.S. 345 (1894)
        Post-citation info: year=1894

        Full citation: 123 F.2d 345, 347-348 (4th Cir. 1990)
        Post-citation info: year=1990, court="4th Cir.", extra (page range)="347-348"
    '''
    end_position = reporter_index + 2
    # Start looking 2 tokens after the reporter (1 after page)
    for start in xrange(reporter_index + 2, min(reporter_index + FORWARD_SEEK, len(words))):
        if words[start].startswith('('):
            for end in xrange(start, start + FORWARD_SEEK):
                if words[end].find(')') > -1:
                    # Sometimes the paren gets split from the preceding content
                    if words[end].startswith(')'):
                        citation.year = get_year(words[end - 1])
                    else:
                        citation.year = get_year(words[end])
                    citation.court = get_court(u' '.join(words[start:end + 1]), citation.year)
                    end_position = end
                    break
            if start > reporter_index + 2:
                # Then there's content between page and (), starting with a comma, which we skip
                citation.extra = u' '.join(words[reporter_index + 3:start])
            break
    return end_position

def add_defendant(citation, words, reporter_index):
    '''Scan backwards from 2 tokens before reporter until you find v., in re, etc.
    If no known stop-token is found, no defendant name is stored.  In the future, 
    this could be improved.'''
    start_index = None
    for index in xrange(reporter_index - 1, max(reporter_index - BACKWARD_SEEK, 0), -1):
        word = words[index]
        if word == ',':
            # Skip it
            continue
        if strip_punct(word).lower() in STOP_TOKENS:
            if word == 'v.':
                citation.plaintiff = words[index - 1]
            start_index = index + 1
            break
        if word.endswith(';'):
            # String citation
            break
    if start_index:
        citation.defendant = u' '.join(words[start_index:reporter_index - 1])

def extract_base_citation(words, reporter_index):
    '''Given a list of words and the index of a federal reporter, look before and after
    for volume and page number.  If found, construct and return a Citation object.'''
    reporter = words[reporter_index]
    # Get rid of extra space so that we only have one version to check
    if reporter == 'U. S.':
        reporter = 'U.S.'
    if words[reporter_index - 1].isdigit():
        volume = int(words[reporter_index - 1])
    else: # No volume, therefore not a valid citation
        return None
    page_str = words[reporter_index + 1]
    if page_str.find(',') == len(page_str) - 1:
        # Strip off ending comma, which occurs when there is a page range next
        page_str = page_str[:-1]
    if page_str.isdigit():
        page = int(page_str)
    else: # No page, therefore not a valid citation
        return None

    return Citation(reporter, page, volume)

def get_citations(text, html=True):
    if html:
        text = get_visible_text(text)
    words = reporter_tokenizer.tokenize(text)
    citations = []
    previous_end_position = 0
    for i in xrange(len(words)):
        # Find reporter
        if words[i] in reporter_tokenizer.REPORTERS:
            citation = extract_base_citation(words, i)
            if citation is None:
                # Not a valid citation; continue looking
                continue
            end_position = add_post_citation(citation, words, i)
            add_defendant(citation, words, i)
            citations.append(citation)

            # Advance the counter; no need to re-check tokens in this citation
            i = end_position
            previous_end_position = end_position + 1

    return citations

def getFileContents(filename):
    f = open(filename, "r")
    text = f.read()
    f.close()
    return text

def getCitationsFromFile(filename):
    contents = getFileContents(filename)
    return get_citations(contents)

def getCitationsFromFiles(filenames):
    citations = []
    for filename in filenames:
        citations.extend(getCitationsFromFile(filename))
    return citations

def main():
    citations = []
    if len(sys.argv) > 1:
        path = sys.argv[1]
        filenames = []
        for filename in os.listdir(path):
            if len(filenames) > 100: break
            if not (filename.endswith("xml") or filename.endswith("pdf")):
                filenames.append(path + "/" + filename)
        citations = getCitationsFromFiles(filenames)

if __name__ == "__main__":
    main()
