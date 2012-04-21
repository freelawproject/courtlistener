#!/usr/bin/env python
# encoding: utf-8

# Loosely adapted from the Natural Language Toolkit: Tokenizers
# URL: <http://nltk.sourceforge.net>

import re

# List of Federal Reporters
REPORTERS = ["U.S.", "U. S.", "S. Ct.", "L. Ed. 2d", "L. Ed.", "F.3d",
             "F.2d", "F. Supp. 2d", "F. Supp.", "F.", "F.R.D.", "B.R.",
             "Vet. App.", "M.J.", "Fed. Cl.", "Ct. Int'l Trade", "T.C."]

REGEX = "|".join(map(re.escape, REPORTERS))

REPORTER_RE = re.compile("(%s)" % REGEX)


def tokenize(text):
    '''Tokenize text using regular expressions in the following steps:
         -Split the text by the occurences of patterns which match a federal
          reporter, including the reporter strings as part of the resulting list.
         -Perform simple tokenization (whitespace split) on each of the non-reporter
          strings in the list.

       Example:
       >>>tokenize('See Roe v. Wade, 410 U. S. 113 (1973)')
       ['See', 'Roe', 'v.', 'Wade,', '410', 'U. S.', '113', '(1973)']
'''


    strings = REPORTER_RE.split(text)
    words = []
    for string in strings:
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
