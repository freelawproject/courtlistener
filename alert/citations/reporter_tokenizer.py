#!/usr/bin/env python
# encoding: utf-8

# Loosely adapted from the Natural Language Toolkit: Tokenizers
# URL: <http://nltk.sourceforge.net>

import re
from alert.citations.constants import REPORTERS, VARIATIONS

REGEX_REPORTERS = "|".join(map(re.escape, REPORTERS))
REGEX_VARIATIONS = '|'.join(map(re.escape, VARIATIONS.keys()))

# Note that VARIATIONS must come first so it has the first opportunity to match.
REPORTER_RE = re.compile("(%s|%s)" % (REGEX_VARIATIONS, REGEX_REPORTERS))


def tokenize(text):
    """Tokenize text using regular expressions in the following steps:
         -Split the text by the occurrences of patterns which match a federal
          reporter, including the reporter strings as part of the resulting list.
         -Perform simple tokenization (whitespace split) on each of the non-reporter
          strings in the list.

       Example:
       >>>tokenize('See Roe v. Wade, 410 U. S. 113 (1973)')
       ['See', 'Roe', 'v.', 'Wade,', '410', 'U. S.', '113', '(1973)']
    """
    strings = REPORTER_RE.split(text)
    words = []
    for string in strings:
        # Normalize spaces up front
        if string in VARIATIONS.keys():
            string = VARIATIONS[string]
        if string in REPORTERS:
            words.append(string)
        else:
            words.extend(_tokenize(string))
    return words


def _tokenize(text):
    #add extra space to make things easier
    text = " " + text + " "

    #get rid of all the annoying underscores in text from pdfs
    text = re.sub(r"__+", "", text)

    #reduce excess whitespace
    text = re.sub(" +", " ", text)
    text = text.strip()

    return text.split()


if __name__ == "__main__":
    exit(0)
