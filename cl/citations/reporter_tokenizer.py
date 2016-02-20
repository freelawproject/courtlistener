#!/usr/bin/env python
# encoding: utf-8

# Loosely adapted from the Natural Language Toolkit: Tokenizers
# URL: <http://nltk.sourceforge.net>

import re
from reporters_db import EDITIONS, VARIATIONS_ONLY


# We need to build a REGEX that has all the variations and the reporters in
# order from longest to shortest.
REGEX_LIST = EDITIONS.keys() + VARIATIONS_ONLY.keys()
REGEX_LIST.sort(key=len, reverse=True)
REGEX_STR = '|'.join(map(re.escape, REGEX_LIST))
REPORTER_RE = re.compile("(%s)" % REGEX_STR)


def normalize_variation(string):
    """Gets the best possible canonicalization of a variant spelling of a
    reporter.

    Variations map to lists of one or more result, and we need to figure out
    which is best. Usually, this can be accomplished using the year of the
    item.
    """
    if string in VARIATIONS_ONLY.keys():
        if len(VARIATIONS_ONLY[string]) == 1:
            # Simple case
            return VARIATIONS_ONLY[string][0]
        else:
            # Hard case, resolve the variation or return as is.
            # TODO: This must be fixed or else all resolutionsn are resolved
            # the same way --> BAD! Once fixed, it will probably need to be
            # removed from the tokenizer, and moved down the pipeline.
            return VARIATIONS_ONLY[string][0]
    else:
        # Not a variant
        return string


def tokenize(text):
    """Tokenize text using regular expressions in the following steps:
        - Split the text by the occurrences of patterns which match a federal
          reporter, including the reporter strings as part of the resulting
          list.
        - Perform simple tokenization (whitespace split) on each of the
          non-reporter strings in the list.

       Example:
       >>>tokenize('See Roe v. Wade, 410 U. S. 113 (1973)')
       ['See', 'Roe', 'v.', 'Wade,', '410', 'U.S.', '113', '(1973)']
    """
    strings = REPORTER_RE.split(text)
    words = []
    for string in strings:
        if string in EDITIONS.keys() + VARIATIONS_ONLY.keys():
            words.append(string)
        else:
            # Normalize spaces
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
