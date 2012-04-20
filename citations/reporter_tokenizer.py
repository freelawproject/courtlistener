#!/usr/bin/env python
# encoding: utf-8

# Adapted from the Natural Language Toolkit: Tokenizers (nltk.tokenize.api)
# URL: <http://nltk.sourceforge.net>

"""
This tokenizer uses regular expressions to tokenize text [WRITE ME]
"""

import re

class FederalReporterTokenizer(object):
    """
    The Treebank tokenizer uses regular expressions to tokenize text as in Penn Treebank.
    This is the method that is invoked by ``word_tokenize()``.  It assumes that the
    text has already been segmented into sentences, e.g. using ``sent_tokenize()``.

    This tokenizer performs the following steps:

    - treat most punctuation characters as separate tokens
    - split off commas and single quotes, when followed by whitespace
    - separate periods that appear at the end of line

        >>> from nltk.tokenize import TreebankWordTokenizer
        >>> s = '''Good muffins cost $3.88\\nin New York.  Please buy me\\ntwo of them.\\n\\nThanks.'''
        >>> TreebankWordTokenizer().tokenize(s)
        ['Good', 'muffins', 'cost', '$', '3.88', 'in', 'New', 'York.',
        'Please', 'buy', 'me', 'two', 'of', 'them', '.', 'Thanks', '.']
        >>> s = "They'll save and invest more."
        >>> TreebankWordTokenizer().tokenize(s)
        ['They', "'ll", 'save', 'and', 'invest', 'more', '.']

    NB. this tokenizer assumes that the text is presented as one sentence per line,
    where each line is delimited with a newline character.
    The only periods to be treated as separate tokens are those appearing
    at the end of a line.
    """

    # List of Federal Reporters
    REPORTERS = ["U.S.",
                 "U. S.",
                 "S. Ct.",
                 "L. Ed. 2d",
                 "L. Ed.",
                 "F.3d",
                 "F.2d",
                 "F. Supp. 2d",
                 "F. Supp.",
                 "F.",
                 "F.R.D.",
                 "B.R.",
                 "Vet. App.",
                 "M.J.",
                 "Fed. Cl.",
                 "Ct. Int'l Trade",
                 "T.C."]

    REGEX = "|".join(map(re.escape, REPORTERS))

    REPORTER_RE = re.compile("(%s)" % REGEX)

    def tokenize(self, text):
        strings = self.REPORTER_RE.split(text)
        words = []
        for string in strings:
            if string in self.REPORTERS:
                words.append(string)
            else:
                words.extend(self._tokenize(string))
        return words

    def _tokenize(self, text):
        #add extra space to make things easier
        text = " " + text + " "

        #get rid of all those annoying underscores!
        text = re.sub(r"__+", "", text)

        #reduce excess whitespace
        text = re.sub(" +", " ", text)
        text = text.strip()

        #add space at end to match up with MacIntyre's output (for debugging)
        if text != "":
            text += " "

        return text.split()

if __name__ == "__main__":
    exit(0)
