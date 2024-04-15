import difflib
import math
import re
import string
from collections import Counter


def remove_words(phrase):
    # Removes words and punctuation that don't help the diff comparison.
    stop_words = (
        r"a|an|and|as|at|but|by|en|etc|for|if|in|is|of|on|or|the|to|v\.?|via"
        + r"|vs\.?|united|states?|et|al|appellants?|defendants?|administrator|plaintiffs?|error"
        + r"|others|against|ex|parte|complainants?|original|claimants?|devisee"
        + r"|executrix|executor"
    )
    stop_words_reg = re.compile(rf"^({stop_words})$", re.IGNORECASE)

    # strips punctuation
    exclude = set(string.punctuation)
    phrase = "".join(ch for ch in phrase if ch not in exclude)

    words = re.split("[\t ]", phrase)
    result = []
    for word in words:
        word = stop_words_reg.sub("", word)
        result.append(word)
    return "".join(result)


def gen_diff_ratio(left, right):
    """
    Generates a difference between two strings.
    Returns a value between 0 and 1. 0 means the strings are totally different.
    1 means they are identical.

    This is a case sensitive comparison. If you want case-insensitive, ensure
    that you run lower() on your strings before passing them in.
    """
    # Remove common strings from all case names /before/ comparison.
    # Doing so lowers the opportunity for false positives.
    left = remove_words(left)
    right = remove_words(right)

    # compute the difference value
    diff = difflib.SequenceMatcher(None, left.strip(), right.strip()).ratio()

    return diff


def find_best_match(items, s, case_sensitive=True):
    """Find the string in the list that is the closest match to the string

    :param items: The list to search within
    :param s: The string to attempt to match
    :param case_sensitive: Whether comparisons should honor case
    :return dict with the index of the best matching value, its value, and its
    match ratio.
    """
    diff_ratios = []
    if not case_sensitive:
        s = s.lower()

    for item in items:
        # Calculate its diff_ratio, and add it to an array
        if not case_sensitive:
            item = item.lower()
        diff = gen_diff_ratio(item, s)
        diff_ratios.append(diff)

    # Find the max ratio, and grab the corresponding result
    max_ratio = max(diff_ratios)
    i = diff_ratios.index(max_ratio)
    return {
        "match_index": i,
        "match_str": items[i],
        "ratio": max_ratio,
    }


def find_confidences(results, case_name):
    """Returns all matches above a threshold.

    This is nearly identical to find_best_match, but returns any good matches
    in an array, and returns their confidence thresholds in a second array.
    """
    diff_ratios = []
    for result in results:
        # Calculate its diff_ratio, and add it to an array
        candidate_case_name = result["caseName"]
        diff = gen_diff_ratio(candidate_case_name, case_name)
        diff_ratios.append(diff)

    return diff_ratios


def string_to_vector(text: str) -> Counter:
    """Convert strings to counter dict.

    :param text: Text to vectorize
    :return: A dictionary of words by count
    """
    WORD = re.compile(r"\w+")
    words = WORD.findall(text)
    return Counter(words)


def get_cosine_similarity(left_str: str, right_str: str) -> float:
    """Calculate the cosine similarity of two strings.

    This can be useful in circumstances when the counts of the words in the
    strings have more meaning that the order of the characters or the edit
    distances of individual words.

    Better for long strings with sentence-length differences, where diff_lib's
    ratio() can fall down.
    """
    left, right = string_to_vector(left_str), string_to_vector(right_str)
    intersection = set(left.keys()) & set(right.keys())
    numerator = sum([left[x] * right[x] for x in intersection])

    sum1 = sum([left[x] ** 2 for x in left.keys()])
    sum2 = sum([right[x] ** 2 for x in right.keys()])
    denominator = math.sqrt(sum1) * math.sqrt(sum2)

    if not denominator:
        return 0.0
    else:
        return float(numerator) / denominator
