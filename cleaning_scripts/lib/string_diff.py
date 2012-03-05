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
    Returns a value between 0 and 1. 0 means the strings are totally diffferent.
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
    '''Returns the best match within a SphinxQuerySet.

    Given a SphinxQuerySet, make a decision about whether any of the
    documents within the queryset are a good match with a provided case
    name.

    This is done by testing the size of the result set. If it's only one
    item, it's assumed that the calling code has already weaned down the
    results to a very likely candidate result, and a low-threshold test
    is performed to ensure that the single result is somewhat similar to
    the case name.

    If multiple cases are in the SphinxQuerySet, then it's assumed that
    our calling code wasn't able to wean the result set down very much,
    and that there's a high degree of risk in picking the correct case.
    Thus, a high-threshold test is applied to the best-matching candidate.

    In the case that a good result is found, returns the candidate result
    and the confidence threshold. If no good result is found, returns None
    and a confidence threshold of zero.
    '''
    if results.count() == 0:
        # No good candidates.
        return None, 0

    elif results.count() == 1:
        # One hit returned make sure it's above THRESHOLD.
        HIGH_THRESHOLD = 0.3
        candidate_case_name = results[0].citation.caseNameFull
        diff = gen_diff_ratio(candidate_case_name, case_name)
        if diff >= HIGH_THRESHOLD:
            return results[0], diff
        else:
            return None, diff

    elif results.count() > 1:
        # More than one hit. Find the best one using diff_lib
        THRESHOLD = 0.65

        diff_ratios = []
        for result in results:
            # Calculate its diff_ratio, and add it to an array
            candidate_case_name = result.citation.caseNameFull
            diff = gen_diff_ratio(candidate_case_name, case_name)
            diff_ratios.append(diff)

        # Find the max ratio, and grab the corresponding result
        max_ratio = max(diff_ratios)
        i = diff_ratios.index(max_ratio)
        if max_ratio >= THRESHOLD:
            # Update the date in the DB
            return results[i], max_ratio

        else:
            # Below the threshold. Punt!
            return None, 0


def find_good_matches(results, case_name):
    '''Returns all matches above a threshold.

    This is nearly identical to find_best_match, but returns any good matches
    in an array, and returns their confidence thresholds in a second array.
    '''
    if len(results) == 0:
        # No good candidates.
        return [], [0]

    elif len(results) == 1:
        # One hit returned make sure it's above THRESHOLD.
        HIGH_THRESHOLD = 0.3
        candidate_case_name = results[0]['caseName']
        diff = gen_diff_ratio(candidate_case_name, case_name)
        if diff >= HIGH_THRESHOLD:
            return [results[0]], [diff]
        else:
            return [], [diff]

    elif len(results) > 1:
        # More than one hit. Find the best one using diff_lib
        THRESHOLD = 0.6

        diff_ratios = []
        for result in results:
            # Calculate its diff_ratio, and add it to an array
            candidate_case_name = result['caseName']
            diff = gen_diff_ratio(candidate_case_name, case_name)
            diff_ratios.append(diff)

        confidences = []
        good_results = []
        i = 0
        while i < len(diff_ratios):
            if diff_ratios[i] >= THRESHOLD:
                confidences.append(diff_ratios[i])
                good_results.append(results[i])

            i += 1

        if len(good_results) > 0:
            return good_results, confidences

        else:
            # No good hits.
            return [], [0]
