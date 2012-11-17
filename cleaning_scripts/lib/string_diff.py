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

import difflib
import string
import re


def remove_words(phrase):
    # Removes words and punctuation that don't help the diff comparison.
    stop_words = 'a|an|and|as|at|but|by|en|etc|for|if|in|is|of|on|or|the|to|v\.?|via' + \
        '|vs\.?|united|states?|et|al|appellants?|defendants?|administrator|plaintiffs?|error' + \
        '|others|against|ex|parte|complainants?|original|claimants?|devisee' + \
        '|executrix|executor'
    stop_words_reg = re.compile(r'^(%s)$' % stop_words, re.IGNORECASE)

    # strips punctuation
    exclude = set(string.punctuation)
    phrase = ''.join(ch for ch in phrase if ch not in exclude)

    words = re.split('[\t ]', phrase)
    result = []
    for word in words:
        word = stop_words_reg.sub('', word)
        result.append(word)
    return ''.join(result)


def gen_diff_ratio(left, right):
    '''
    Genrates a difference between two strings
    Returns a value between 0 and 1. 0 means the strings are totally different.
    1 means they are identical.
    '''
    # Remove common strings from all case names /before/ comparison.
    # Doing so lowers the opportunity for false positives.
    left = remove_words(left)
    right = remove_words(right)

    # compute the difference value
    diff = difflib.SequenceMatcher(None, left.strip(), right.strip()).ratio()

    return diff


def find_best_match(results, case_name):
    '''Returns the closest match to within a Solr result set to a known
    string.
    '''
    diff_ratios = []
    for result in results:
        # Calculate its diff_ratio, and add it to an array
        diff = gen_diff_ratio(result['caseName'], case_name)
        diff_ratios.append(diff)

    # Find the max ratio, and grab the corresponding result
    max_ratio = max(diff_ratios)
    i = diff_ratios.index(max_ratio)
    return results[i], max_ratio


def find_confidences(results, case_name):
    '''Returns all matches above a threshold.

    This is nearly identical to find_best_match, but returns any good matches
    in an array, and returns their confidence thresholds in a second array.
    '''
    diff_ratios = []
    for result in results:
        # Calculate its diff_ratio, and add it to an array
        candidate_case_name = result['caseName']
        diff = gen_diff_ratio(candidate_case_name, case_name)
        diff_ratios.append(diff)

    return diff_ratios
