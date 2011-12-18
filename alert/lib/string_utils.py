# -*- coding: utf-8 -*-
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


import re
from django.utils.encoding import smart_str
from django.utils.encoding import smart_unicode

# For use in titlecase
BIG = 'AFL|AKA|A/K/A|BMG|CDC|CDT|CEO|CIO|CNMI|D/B/A|DOJ|DVA|EFF|FCC|FTC|IBM|II|III|IV|LLC|LLP|MCI|MJL|MSPB|UPS|RSS|SEC|USA|USC|USPS|WTO'
SMALL = 'a|an|and|as|at|but|by|en|for|if|in|is|of|on|or|the|to|v\.?|via|vs\.?'
NUMS = '0|1|2|3|4|5|6|7|8|9'
PUNCT = r"""!"#$¢%&'‘()*+,\-./:;?@[\\\]_—`{|}~"""
WEIRD_CHARS = r"""¼½¾§ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜßàáâãäåæçèéêëìíîïñòóôœõöøùúûüÿ"""
BIG_WORDS = re.compile(r'^(%s)$' % BIG, re.I)
SMALL_WORDS = re.compile(r'^(%s)$' % SMALL, re.I)
INLINE_PERIOD = re.compile(r'[a-z][.][a-z]', re.I)
UC_ELSEWHERE = re.compile(r'[%s]*?[a-zA-Z]+[A-Z]+?' % PUNCT)
CAPFIRST = re.compile(r"^[%s]*?([A-Za-z])" % PUNCT)
SMALL_FIRST = re.compile(r'^([%s]*)(%s)\b' % (PUNCT, SMALL), re.I)
SMALL_LAST = re.compile(r'\b(%s)[%s]?$' % (SMALL, PUNCT), re.I)
SUBPHRASE = re.compile(r'([:.;?!][ ])(%s)' % SMALL)
APOS_SECOND = re.compile(r"^[dol]{1}['‘]{1}[a-z]+$", re.I)
ALL_CAPS = re.compile(r'^[A-Z\s%s%s%s]+$' % (PUNCT, WEIRD_CHARS, NUMS))
UC_INITIALS = re.compile(r"^(?:[A-Z]{1}\.{1}|[A-Z]{1}\.{1}[A-Z]{1})+,?$")
MAC_MC = re.compile(r"^([Mm]a?c)(\w+)")

def titlecase(text, DEBUG = False):
    '''
    Titlecases input text

    This filter changes all words to Title Caps, and attempts to be clever
    about *un*capitalizing SMALL words like a/an/the in the input.

    The list of "SMALL words" which are not capped comes from
    the New York Times Manual of Style, plus 'vs' and 'v'.
    '''

    # make all input uppercase.
    text = text.upper()

    lines = re.split('[\r\n]+', text)
    processed = []
    for line in lines:
        all_caps = ALL_CAPS.match(line)
        words = re.split('[\t ]', line)
        tc_line = []
        for word in words:
            if DEBUG:
                print "Word: " + word
            if all_caps:
                if UC_INITIALS.match(word):
                    if DEBUG:
                        print "UC_INITIALS match for: " + word
                    tc_line.append(word)
                    continue
                else:
                    if DEBUG:
                        print "Not initials. Lowercasing: " + word
                    word = word.lower()

            if APOS_SECOND.match(word):
                word = word.replace(word[0], word[0].upper())
                word = word.replace(word[2], word[2].upper())
                tc_line.append(word)
                continue

            if INLINE_PERIOD.search(word) or UC_ELSEWHERE.match(word):
                tc_line.append(word)
                continue

            if SMALL_WORDS.match(word):
                tc_line.append(word.lower())
                continue

            if BIG_WORDS.match(word):
                tc_line.append(word.upper())
                continue

            match = MAC_MC.match(word)
            if match and (word != 'mack'):
                tc_line.append("%s%s" % (match.group(1).capitalize(),
                                      match.group(2).capitalize()))
                continue

            hyphenated = []
            for item in word.split('-'):
                hyphenated.append(CAPFIRST.sub(lambda m: m.group(0).upper(),
                    item))
            tc_line.append("-".join(hyphenated))


        result = " ".join(tc_line)

        result = SMALL_FIRST.sub(lambda m: '%s%s' % (
            m.group(1),
            m.group(2).capitalize()), result)

        result = SMALL_LAST.sub(lambda m: m.group(0).capitalize(), result)

        result = SUBPHRASE.sub(lambda m: '%s%s' % (
            m.group(1),
            m.group(2).capitalize()), result)


        processed.append(result)

        text = "\n".join(processed)

    # replace V. with v.
    text = re.sub(re.compile(r'\WV\.\W'), ' v. ', text)

    # replace Llc. with LLC
    text = text.replace('Llc.', 'LLC')

    return text


# For use in harmonize function
US = 'USA|U\.S\.A\.|U\.S\.?|U\. S\.?|(The )?United States of America|The United States'
UNITED_STATES = re.compile(r'^(%s)(,|\.)?$' % US, re.I)
ET_AL = re.compile(',?\set\.?\sal\.?', re.I)
BW = 'appell(ee|ant)s?|claimants?|complainants?|defendants?|defendants?(--?|/)appell(ee|ant)s?' + \
     '|devisee|executor|executrix|petitioners?|petitioners?(--?|/)appell(ee|ant)s?' + \
     '|petitioners?(--?|/)defendants?|plaintiffs?|plaintiffs?(--?|/)appell(ee|ant)s?|respond(e|a)nts?' + \
     '|respond(e|a)nts?(--?|/)appell(ee|ant)s?|cross(--?|/)respondents?|crosss?(--?|/)petitioners?'
BAD_WORDS = re.compile(r'^(%s)(,|\.)?$' % BW, re.I)
def harmonize(text):
    '''Fixes case names so they are cleaner.

    Using a bunch of regex's, this function cleans up common data problems in
    case names. The following are currently fixed:
     - various forms of United States --> United States
     - vs. --> v.
     - et al --> Removed.
     - plaintiff, appellee, defendant and the like --> Removed.

    Lots of tests are in tests.py.
    '''

    result = ''
    # replace vs. with v.
    text = re.sub(re.compile(r'\Wvs\.\W'), ' v. ', text)

    # replace V. with v.
    text = re.sub(re.compile(r'\WV\.\W'), ' v. ', text)

    # Remove the BAD_WORDS.
    text = text.split()
    cleaned_text = []
    for word in text:
        word = re.sub(BAD_WORDS, '', word)
        cleaned_text.append(word)
    text = ' '.join(cleaned_text)

    # split on all ' v. ' and then deal with United States variations.
    text = text.split(' v. ')
    i = 1
    for frag in text:
        frag = frag.strip()
        if UNITED_STATES.match(frag):
            if i == len(text):
                # it's the last iteration don't append v.
                result = result + "United States"
            else:
                result = result + "United States v. "
        else:
            #needed here, because case sensitive
            frag = re.sub(re.compile(r'^US$'), 'United States', frag)
            # no match
            if i == len(text):
                result = result + frag
            else:
                result = result + frag + " v. "
        i += 1

    # Remove the ET_AL words.
    result = re.sub(ET_AL, '', result)

    return clean_string(result)


def clean_string(string):
    '''Clean up strings.

    Accomplishes the following:
     - replaces HTML encoded characters with ASCII versions.
     - removes -, ' ', #, *, ; and ',' from the end of lines
     - converts to unicode.
     - removes weird white space and replaces with spaces.
    '''
    # Get rid of HTML encoded chars
    string = string.replace('&rsquo;', '\'').replace('&rdquo;', "\"")\
        .replace('&ldquo;', "\"").replace('&nbsp;', ' ')\
        .replace('&amp;', '&').replace('%20', ' ').replace('&#160;', ' ')

    # Get rid of weird punctuation
    string = string.replace('*', '').replace('#', '').replace(';', '')

    # Strip bad stuff from the end of lines. Python's strip fails here because
    # we don't know the order of the various punctuation items to be stripped.
    # We split on the v., and handle fixes at either end of plaintiff or
    # appellant.
    bad_punctuation = r'(-|;|,|\s)*'
    bad_endings = re.compile(r'%s$' % bad_punctuation)
    bad_beginnings = re.compile(r'^%s' % bad_punctuation)

    string = string.split(' v. ')
    cleaned_string = []
    for frag in string:
        frag = re.sub(bad_endings, '', frag)
        frag = re.sub(bad_beginnings, '', frag)
        cleaned_string.append(frag)
    string = ' v. '.join(cleaned_string)

    # if not already unicode, make it unicode, dropping invalid characters
    # if not isinstance(string, unicode):
    string = smart_unicode(string, encoding = 'utf-8', errors = 'ignore')

    # get rid of '\t\n\x0b\x0c\r ', and replace them with a single space.
    string = " ".join(string.split())

    # get rid of bad character encodings
    string = smart_str(string, errors = 'ignore')

    # return something vaguely sane
    return string



# For use in anonymize function
SSN_AND_ITIN = re.compile('(\s|^)(\d{3}-\d{2}-\d{4})(\s|$)')
EIN = re.compile('(\s|^)(\d{2}-\d{7})(\s|$)')

def anonymize(string):
    """Convert SSNs, EIN and alienIDs to X's."""

    '''
    # For testing
    test_strings = [
        ("444-44-4444", "XXX-XX-XXXX"),
        ("   444-44-4444", "   XXX-XX-XXXX"),
        ("   444-44-4444   ", "   XXX-XX-XXXX   "),
        ("4444-44-4444", "4444-44-4444"),
        (" 4444-44-4444", " 4444-44-4444"),
        (" 4444-44-4444 ", " 4444-44-4444 "),
        ("444-44-44444", "444-44-44444"),
        ("444-444-4444", "444-444-4444")]

    for test, goal in test_strings:
        result = re.sub(SSN_AND_ITIN, r"\1XXX-XX-XXXX\3", test)
        result = re.sub(EIN, r'\1XX-XXXXXXX\3', result)
        if result != goal:
            print "\"" + test + "\"" + " --> " + "\"" + result + "\""
    '''

    string = re.sub(SSN_AND_ITIN, r"\1XXX-XX-XXXX\3", string)
    string = re.sub(EIN, r"\1XX-XXXXXXX\3", string)

    return string


def trunc(s, length):
    """finds the rightmost space in a string, and truncates there. Lacking such
    a space, truncates at length"""

    if len(s) <= length:
        return s
    else:
        # find the rightmost space
        end = s.rfind(' ', 0 , length)
        if end == -1:
            # no spaces found, just use max position
            end = length
        return s[0:end]


def removeLeftMargin(s):
    # Gets rid of left hand margin using the mode of
    # the number of spaces before text in the doc.
    lines = s.split('\n')
    marginSizes = []
    for line in lines:
        if len(line) > 0:
            if line[0] == ' ':
                # if the line has length and starts with a space
                newlength = len(line.lstrip())
                oldlength = len(line)
                diff = oldlength - newlength
                if diff != 0:
                    marginSizes.append(oldlength - newlength)

    mode = max([marginSizes.count(y), y] for y in marginSizes)[1]

    lines_out = []
    for line in lines:
        numLSpaces = len(line) - len(line.lstrip())
        if numLSpaces < mode:
            # Strip only that number of spaces
            line_out = line[numLSpaces:]
        elif numLSpaces >= mode:
            # Strip off the mode number of spaces
            line_out = line[mode:]

        lines_out.append(line_out)

    return '\n'.join(lines_out)


def removeDuplicateLines(s):
    # Remove duplciate lines next to each other.
    lines = s.split('\n')
    lines_out = []
    previous_line = ''
    for line in lines:
        if line != previous_line:
            lines_out.append(line)
            previous_line = line

    return '\n'.join(lines_out)
