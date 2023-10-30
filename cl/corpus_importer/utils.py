import re
from datetime import date
from typing import Any, Iterator, Optional

import bs4
from django.utils.timezone import now

from cl.lib.string_diff import get_cosine_similarity
from cl.search.models import Docket


class OpinionMatchingException(Exception):
    """An exception for wrong matching opinions"""

    def __init__(self, message: str) -> None:
        self.message = message


class AuthorException(Exception):
    """Error found in author merger."""

    def __init__(self, message: str) -> None:
        self.message = message


class JudgeException(Exception):
    """An exception for wrong judges"""

    def __init__(self, message: str) -> None:
        self.message = message


class OpinionTypeException(Exception):
    """An exception for incorrect opinion types"""

    def __init__(self, message: str) -> None:
        self.message = message


class DocketSourceException(Exception):
    """An exception for wrong docket source"""

    def __init__(self, message: str) -> None:
        self.message = message


class ClusterSourceException(Exception):
    """An exception for wrong cluster source"""

    def __init__(self, message: str) -> None:
        self.message = message


class DateException(Exception):
    """Error found in date merger."""

    def __init__(self, message: str) -> None:
        self.message = message


class EmptyOpinionException(Exception):
    """An exception for opinions that raise a ZeroDivisionError Exception due empty
    opinion tag"""

    def __init__(self, message: str) -> None:
        self.message = message


async def mark_ia_upload_needed(d: Docket, save_docket: bool) -> None:
    """Mark the docket as needing upload if it's not already marked.

    The point here is that we need to know the first time an item was updated,
    not the *most recent* time it was updated. This way, we know how long it
    has been since it was last uploaded to Internet Archive, and whether it's
    time for us to do so.

    :param d: The docket to mark
    :param save_docket: Whether to save the docket or just modify it in place
    :return: None
    """
    if not d.ia_needs_upload:
        d.ia_needs_upload = True
        d.ia_date_first_change = now()
    if save_docket:
        await d.asave()


def get_start_of_quarter(d: Optional[date] = None) -> date:
    """Get the start date of the  calendar quarter requested

    :param d: The date to get the start date for. If None, then use current
    date/time.
    """
    if d is None:
        d = now().date()

    d_year = d.year
    quarter_dates = [
        date(d_year, 1, 1),
        date(d_year, 4, 1),
        date(d_year, 7, 1),
        date(d_year, 10, 1),
    ]
    return max([q for q in quarter_dates if q <= d])


def make_subset_range(cl_characters: str, max_string: str) -> list[int]:
    """Find indices for matching max_string in CL opinion

    :param cl_characters: The stripped down CL characters
    :param max_string: The current largest identified substring
    :return: Range of indices of match to CL as list
    """
    string_index_start = cl_characters.find(max_string)
    string_index_end = string_index_start + len(max_string)
    return list(range(string_index_start, string_index_end))


def filter_subsets(lists: list[list[int]]) -> Iterator[list[int]]:
    """Filter subsets from matches

    Given list of lists, return new list of lists without subsets

    :param lists: List of matched lists ranges
    :return: Reduced list of matches
    """

    for match in lists:
        if not any(
            is_subset(match, other_matches)
            for other_matches in lists
            if match is not other_matches
        ):
            yield match


def is_subset(match: list[int], other_match: list[int]) -> bool:
    """Check if match is a subset of other matches

    Check if needle is ordered subset of haystack in O(n)
    :param match: Matching range of text as the indices
    :param other_match: Other matching range of text as indices
    :return: Is match a subset of other match
    """

    if len(other_match) < len(match):
        return False
    index = 0
    for element in match:
        try:
            index = other_match.index(element, index) + 1
        except ValueError:
            return False
    else:
        return True


def compare_documents(harvard_characters: str, cl_characters: str) -> int:
    """Compare Harvard text to CL opinion text

    This code iterates over two opinions logging similar stretches and then
    returns a percentage of the total overlapping characters

    :param harvard_characters: The stripped down opinion text from Harvard
    :param cl_characters: The stripped down opinion text on Courtlistener
    :return: Percentage (as integer) overlapping content
    """

    start, stop, count = 0, 0, 0
    matched_substring = ""
    found_overlaps = []
    while stop < len(harvard_characters):
        stop += 1
        harvard_substring = harvard_characters[start:stop]
        if harvard_substring in cl_characters:
            matched_substring = harvard_substring
        else:
            if len(matched_substring) > 5:
                subset = make_subset_range(cl_characters, matched_substring)
                found_overlaps.append(subset)
            matched_substring = ""
            start = stop - 1
    if len(matched_substring) > 5:
        subset = make_subset_range(cl_characters, matched_substring)
        found_overlaps.append(subset)

    # If we checked our subsets as we parsed-we wouldn't need to do this
    # filtering here. This is a good candidate for refactoring.
    filtered_subset = list(filter_subsets(found_overlaps))
    for overlap in filtered_subset:
        count += len(overlap)

    percent_match = int(
        100 * (count / min([len(harvard_characters), len(cl_characters)]))
    )
    return percent_match


def wrap_text(length, text):
    """Wrap text to specified length without cutting words
    :param length: max length to wrap
    :param text: text to wrap
    :return: text wrapped
    """
    words = text.split(" ")
    if words:
        lines = [words[0]]
        for word in words[1:]:
            if len(lines[-1]) + len(word) < length:
                lines[-1] += f" {word}"
            else:
                lines.append(word)
                break
        return " ".join(lines)
    return ""


def similarity_scores(
    texts_to_compare_1: list[str], texts_to_compare_2: list[str]
) -> list[list[float]]:
    """Get similarity scores between two sets of lists

    Using TF-IDF/Term Frequency-Inverse Document Frequency
    we use word frequency to generate a similarity score between the corpora

    :param texts_to_compare_1: List of text to compare
    :param texts_to_compare_2: List of text to compare
    :return: Return similarity scores
    """

    # We import the library inside the function to avoid loading it if it is
    # not required
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    # Weights the word counts by a measure of how often they appear in the
    # documents, and it returns a sparse matrix
    X = TfidfVectorizer().fit_transform(
        texts_to_compare_1 + texts_to_compare_2
    )

    # Calculate cosine similarity between weight of words for each text in list
    scores = cosine_similarity(
        X[: len(texts_to_compare_1)], X[len(texts_to_compare_1) :]
    )
    return scores


def match_lists(
    harvard_opinions_list: list[bs4.element.Tag], cl_opinions_list: list[str]
) -> dict[int, Any]:
    """Generate matching lists above threshold

    :param harvard_opinions_list: Harvard Opinions
    :param cl_opinions_list: CL opinions
    :return: Matches if found or False
    """

    # Convert harvard HTML to Text to compare
    harvard_opinions_list = [h.getText() for h in harvard_opinions_list]
    scores = similarity_scores(harvard_opinions_list, cl_opinions_list)

    matches = {}
    for i, row in enumerate(scores):
        j = row.argmax()  # type: ignore
        # Lower threshold for small opinions.
        # Remove non-alphanumeric and non-whitespace characters from lowercased text,
        # this tries to make both texts in equal conditions to prove if both are
        # similar or equal
        h_opinion = re.sub(
            r"[^a-zA-Z0-9 ]", "", harvard_opinions_list[i].lower()
        )
        cl_opinion = re.sub(r"[^a-zA-Z0-9 ]", "", cl_opinions_list[j].lower())

        cosine_sim = get_cosine_similarity(h_opinion, cl_opinion)
        percent_match = compare_documents(h_opinion, cl_opinion)

        # Sometimes cosine similarity fails when there are small variations in text,
        # such as parties, attorneys, case name, or court that are included in the
        # content of the opinion, compare_documents() checks the percentage of the
        # harvard opinion text that it is in courtlistener opinion, having a large
        # percentage means that almost all the harvard opinion is in courtlistener
        # opinion, but there is a possibility that the courtlistener opinion contains
        # some additional data in que opinion content (such as case name, parties, etc.)
        if cosine_sim < 0.60 and percent_match < 60:
            continue

        matches[i] = j

    return matches
