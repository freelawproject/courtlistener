import difflib
import math
import string
import re

from collections import Counter


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
    """
    Generates a difference between two strings
    Returns a value between 0 and 1. 0 means the strings are totally different.
    1 means they are identical.
    """
    # Remove common strings from all case names /before/ comparison.
    # Doing so lowers the opportunity for false positives.
    left = remove_words(left)
    right = remove_words(right)

    # compute the difference value
    diff = difflib.SequenceMatcher(None, left.strip(), right.strip()).ratio()

    return diff


def find_best_match(results, case_name):
    """Returns the closest match to within a Solr result set to a known
    string.
    """
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
    """Returns all matches above a threshold.

    This is nearly identical to find_best_match, but returns any good matches
    in an array, and returns their confidence thresholds in a second array.
    """
    diff_ratios = []
    for result in results:
        # Calculate its diff_ratio, and add it to an array
        candidate_case_name = result['caseName']
        diff = gen_diff_ratio(candidate_case_name, case_name)
        diff_ratios.append(diff)

    return diff_ratios


def string_to_vector(text):
    WORD = re.compile(r'\w+')
    words = WORD.findall(text)
    return Counter(words)


def get_cosine_similarity(left, right):
    """Calculate the cosine similarity of two strings.

    This can be useful in circumstances when the counts of the words in the
    strings have more meaning that the order of the characters or the edit
    distances of individual words.

    Better for long strings with sentence-length differences, where diff_lib's
    ratio() can fall down.
    """
    left, right = string_to_vector(left), string_to_vector(right)
    intersection = set(left.keys()) & set(right.keys())
    numerator = sum([left[x] * right[x] for x in intersection])

    sum1 = sum([left[x] ** 2 for x in left.keys()])
    sum2 = sum([right[x] ** 2 for x in right.keys()])
    denominator = math.sqrt(sum1) * math.sqrt(sum2)

    if not denominator:
        return 0.0
    else:
        return float(numerator) / denominator
