# -*- coding: utf-8 -*-

import re


def anonymize(s):
    """Anonymizes private information.

    Converts SSNs, EINs, and A-Numbers to X's. Reports whether a modification
    was made, as a boolean.

    For more information about A-Numbers, see:
      https://www.uscis.gov/tools/glossary/number

    SSNs can be much more complicated than the implementation here. For
    details, see:
      http://rion.io/2013/09/10/validating-social-security-numbers-through-regular-expressions-2/
    """
    ssn_re = re.compile(r'\b(\d{3}-\d{2}-\d{4})\b', flags=re.VERBOSE)
    ein_re = re.compile(r'\b(\d{2}-\d{7})\b')
    a_number_re = re.compile(r'\b(A\d{8,9})\b')
    s, ssn_count = re.subn(ssn_re, r"XXX-XX-XXXX", s)
    s, ien_count = re.subn(ein_re, r"XX-XXXXXXX", s)
    s, a_number_count = re.subn(a_number_re, r"AXXXXXXXX", s)
    modified = bool(ssn_count + ien_count + a_number_count)
    return s, modified


def trunc(s, length, ellipsis=None):
    """Truncates a string at a good length.

    Finds the rightmost space in a string, and truncates there. Lacking such
    a space, truncates at length.

    If an ellipsis is provided, the right most space is used that allows the
    addition of the ellipsis without being longer than length.
    """
    if ellipsis:
        ellipsis_length = len(ellipsis)
    else:
        ellipsis_length = 0

    if len(s) <= length:
        # Do not ellipsize if the item is not truncated.
        return s
    else:
        # find the rightmost space using a zero-indexed (+1) length minus the
        # length of the ellipsis.
        rightmost_space_index = length - ellipsis_length + 1
        end = s.rfind(' ', 0, rightmost_space_index)
        if end == -1:
            # no spaces found, just use max position
            end = length - ellipsis_length
        s = s[0:end]
        if ellipsis:
            s = '%s%s' % (s, ellipsis)
        return s


def filter_invalid_XML_chars(input):
    """XML allows:

       Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]

    This strips out everything else.

    See: http://stackoverflow.com/a/25920392/64911
    """
    if isinstance(input, basestring):
        # Only do str, unicode, etc.
        return re.sub(u'[^\u0020-\uD7FF\u0009\u000A\u000D\uE000-\uFFFD'
                      u'\U00010000-\U0010FFFF]+', u'', input)
    else:
        return input


def removeLeftMargin(s):
    """Gets rid of left hand margin.

    Given a block of text, calculates the mode of the number of spaces before
    text in the doc, and then removes that number of spaces from the text. This
    should not be used in the general case, but can be used in cases where a
    left-hand margin is known to exist.
    """
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
    """Remove duplicate lines next to each other."""
    lines = s.split('\n')
    lines_out = []
    previous_line = ''
    for line in lines:
        if line != previous_line:
            lines_out.append(line)
            previous_line = line

    return '\n'.join(lines_out)
