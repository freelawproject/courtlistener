#!/usr/bin/env python
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


"""
Original Perl version by: John Gruber http://daringfireball.net/ 10 May 2008
Python version by Stuart Colville http://muffinresearch.co.uk
License: http://www.opensource.org/licenses/mit-license.php
"""

import re

__all__ = ['titlecase']
__version__ = '0.5.1'

BIG = 'USA|FCC|FTC|DOJ|USC|WTO|EFF|CDT|RSS|LLP|USPS|LLC|CDC|CNMI'
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
                hyphenated.append(CAPFIRST.sub(lambda m: m.group(0).upper(), item))
            tc_line.append("-".join(hyphenated))
        

        result = " ".join(tc_line)

        result = SMALL_FIRST.sub(lambda m: '%s%s' % (
            m.group(1),
            m.group(2).capitalize()
        ), result)

        result = SMALL_LAST.sub(lambda m: m.group(0).capitalize(), result)

        result = SUBPHRASE.sub(lambda m: '%s%s' % (
            m.group(1),
            m.group(2).capitalize()
        ), result)
        
        processed.append(result)

    return "\n".join(processed)
