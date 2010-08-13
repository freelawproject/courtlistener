# -*- coding: utf-8 -*-

"""
Original Perl version by: John Gruber http://daringfireball.net/ 10 May 2008
Python version by Stuart Colville http://muffinresearch.co.uk
License: http://www.opensource.org/licenses/mit-license.php
"""

import re
from django.utils.encoding import smart_str


# For use in titlecase
BIG = 'USA|FCC|FTC|DOJ|USC|WTO|EFF|CDT|RSS|LLP|USPS|LLC|CDC|CNMI|DVA|MSPB'
SMALL = 'a|an|and|as|at|but|by|en|for|if|in|of|on|or|the|to|v\.?|via|vs\.?'
PUNCT = r"""!"#$%&'‘()*+,\-./:;?@[\\\]_`{|}~"""
BIG_WORDS = re.compile(r'^(%s)$' % BIG, re.I)
SMALL_WORDS = re.compile(r'^(%s)$' % SMALL, re.I)
INLINE_PERIOD = re.compile(r'[a-z][.][a-z]', re.I)
UC_ELSEWHERE = re.compile(r'[%s]*?[a-zA-Z]+[A-Z]+?' % PUNCT)
CAPFIRST = re.compile(r"^[%s]*?([A-Za-z])" % PUNCT)
SMALL_FIRST = re.compile(r'^([%s]*)(%s)\b' % (PUNCT, SMALL), re.I)
SMALL_LAST = re.compile(r'\b(%s)[%s]?$' % (SMALL, PUNCT), re.I)
SUBPHRASE = re.compile(r'([:.;?!][ ])(%s)' % SMALL)
APOS_SECOND = re.compile(r"^[dol]{1}['‘]{1}[a-z]+$", re.I)
ALL_CAPS = re.compile(r'^[A-Z\s%s]+$' % PUNCT)
UC_INITIALS = re.compile(r"^(?:[A-Z]{1}\.{1}|[A-Z]{1}\.{1}[A-Z]{1})+$")
MAC_MC = re.compile(r"^([Mm]a?c)(\w+)")

# For use in harmonize function
US = 'USA|U\.S\.A\.|U\.S\.|United States of America'
UNITED_STATES = re.compile(r'^(%s)$' % US, re.I)
ET_AL = re.compile(',?\set\.?\sal\.?', re.IGNORECASE)

# For use in anonymize function
SSN_AND_ITIN = re.compile('(\s|^)(\d{3}-\d{2}-\d{4})(\s|$)')
EIN = re.compile('(\s|^)(\d{2}-\d{7})(\s|$)')


def titlecase(text):
    """
    Titlecases input text

    This filter changes all words to Title Caps, and attempts to be clever
    about *un*capitalizing SMALL words like a/an/the in the input.

    The list of "SMALL words" which are not capped comes from
    the New York Times Manual of Style, plus 'vs' and 'v'.

    """

    lines = re.split('[\r\n]+', text)
    processed = []
    for line in lines:
        all_caps = ALL_CAPS.match(line)
        words = re.split('[\t ]', line)
        tc_line = []
        for word in words:
            if all_caps:
                if UC_INITIALS.match(word):
                    tc_line.append(word)
                    continue
                else:
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
            if match:
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

        return "\n".join(processed)


def harmonize(text):
    """This function fixes case names so they're cleaner. It fixes various
    ways of writing United States, gets rid of et al, and changes vs. to v.
    Lots of tests are in tests.py.
    """

    result = ''
    # replace vs. with v.
    text = re.sub(re.compile(r'\Wvs\.\W'), ' v. ', text)

    # split on all ' v. '
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

    result = re.sub(ET_AL, '', result)

    return result


def clean_string(string):
    ''' replace evil characters with better ones, get rid of white space on
    the ends, and get rid of semicolons on the ends.'''
    string = string.replace('&rsquo;', '\'').replace('&rdquo;', "\"")\
        .replace('&ldquo;', "\"").replace('&nbsp;', ' ')\
        .replace('&amp;', '&').replace('%20', ' ').replace('&#160;', ' ')\
        .strip().strip(';')

    # get rid of '\t\n\x0b\x0c\r ', and replace them with a single space.
    string = " ".join(string.split())

    # get rid of bad character encodings
    string = smart_str(string)

    # return something vaguely sane
    return string


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
