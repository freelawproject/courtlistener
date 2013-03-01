# -*- coding: utf-8 -*-

import re

# three digits dash two digits dash four digits, not proceeded or followed 
# by digits. Proceeding start of line (^) or following end of line ($) OK.   
SSN_AND_ITIN = re.compile('([^0-9A-Za-z-]|^)(\d{3}-\d{2}-\d{4})([^0-9A-Za-z-]|$)')
EIN = re.compile('([^0-9A-Za-z-]|^)(\d{2}-\d{7})([^0-9A-Za-z-]|$)')
def anonymize(string):
    '''Anonymizes private information.

    Converts SSNs, EIN and alienIDs to X's. Reports whether a modification was
    made, as a boolean.
    '''
    string, ssn_replacements = re.subn(SSN_AND_ITIN, r"\1XXX-XX-XXXX\3", string)
    string, ien_replacements = re.subn(EIN, r"\1XX-XXXXXXX\3", string)
    modified = bool(ssn_replacements + ien_replacements)
    return string, modified


def trunc(s, length):
    '''Truncates a string at a good length.

    Finds the rightmost space in a string, and truncates there. Lacking such
    a space, truncates at length.
    '''
    if len(s) <= length:
        return s
    else:
        # find the rightmost space
        end = s.rfind(' ', 0, length)
        if end == -1:
            # no spaces found, just use max position
            end = length
        return s[0:end]


def removeLeftMargin(s):
    '''Gets rid of left hand margin.

    Given a block of text, calculates the mode of the number of spaces before
    text in the doc, and then removes that number of spaces from the text. This
    should not be used in the general case, but can be used in cases where a
    left-hand margin is known to exist.
    '''
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
    '''Remove duplicate lines next to each other.'''
    lines = s.split('\n')
    lines_out = []
    previous_line = ''
    for line in lines:
        if line != previous_line:
            lines_out.append(line)
            previous_line = line

    return '\n'.join(lines_out)
